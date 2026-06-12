"""# Hlasový dispečer pro chytrou domácnost — s live state vizualizací

Rozšíření příkladu 06cs_smart_home_assistant.py o **Live State Viewer**:
stav domácnosti je modelován jako Pydantic třída s anotacemi `icon()` a `room()`,
díky nimž se v záložce *Chat* GUI zobrazuje živá vizualizace místností
— žárovky, sporák a teplota se mění v reálném čase při každém příkazu.

## Pipeline

1. **IntentParser** — rozpozná kategorii požadavku
2. **DeviceWorker** — zkontroluje stav místností nástroji, navrhne akce:
   - `get_current_status` — teplota, světla, obsazenost místnosti
   - `set_temperature`    — nastaví cílovou teplotu v °C
   - `toggle_device`      — zapne/vypne světla nebo sporák
3. **SafetyJudge** — ověří plán vůči bezpečnostním pravidlům; zamítne při porušení
4. **VoiceFormatter** — vytvoří stručnou odpověď připravenou pro TTS

## Klíčová novinka — Live State

```python
class KitchenState(BaseModel):
    temperature: Annotated[float, icon("thermometer", unit="°C")] = Field(20.0, title="Teplota")
    lights: Annotated[bool, icon("bulb", on_color="#fbbf24")] = Field(False, title="Světla")
    stove:  Annotated[bool, icon("flame", on_color="#ef4444")] = Field(False, title="Sporák")
    persons: Annotated[int, icon("person")] = Field(1, title="Osoby")

class HouseState(BaseModel):
    kuchyne: Annotated[KitchenState, room("Kuchyně", col_span=2)] = ...
    loznice: Annotated[BedroomState, room("Ložnice")] = ...
    obyvak:  Annotated[LivingState,  room("Obývák")] = ...
```

`AgentApp(live_state=_HOUSE, ...)` — GUI automaticky zobrazí vizualizaci.

## Spuštění

```bash
uv run python examples/agents/06cs_live_smart_home.py run
uv run python examples/agents/06cs_live_smart_home.py gui
uv run python examples/agents/06cs_live_smart_home.py graph --browser
```
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from agentflow import AgentApp
from agentflow.gui.state_viewer import icon, room
from agentflow.llm.cache import LlmFileCache
from agentflow.llm.LlmPool import LlmPool
from agentflow.statemachine import (
    UNSET,
    Context,
    LlmStateVertex,
    Signal,
    StateGraph,
    StdEnd,
    Transition,
)
from agentflow.tools.Tool import ToolBase, param_desc
from agentflow.tools.ToolRegistry import ToolRegistry

# ---------------------------------------------------------------------------
# Konstanty
# ---------------------------------------------------------------------------

_DEFAULT_QUESTION = "Rozsviť světlo v kuchyni a nastav teplotu na 22 stupňů."

_SYSTEM_PROMPT = (
    "Jsi asistent pro chytrou domácnost. "
    "Před navrhováním změn vždy zkontroluj aktuální stav místností pomocí nástrojů. "
    "Bezpečnost je na prvním místě. "
    "Odpovídej vždy česky."
)

# ---------------------------------------------------------------------------
# Live state modely — Pydantic BaseModel s display anotacemi
# ---------------------------------------------------------------------------


class KitchenState(BaseModel):
    """Stav kuchyně — zobrazuje se v GUI jako místnost se čtyřmi indikátory."""

    model_config = ConfigDict(frozen=False)

    temperature: Annotated[float, icon("thermometer", unit="°C")] = Field(20.0, title="Teplota")
    lights: Annotated[bool, icon("bulb", on_color="#fbbf24")] = Field(False, title="Světla")
    stove: Annotated[bool, icon("flame", on_color="#ef4444")] = Field(False, title="Sporák")
    persons: Annotated[int, icon("person")] = Field(1, title="Osoby")


class BedroomState(BaseModel):
    """Stav ložnice."""

    model_config = ConfigDict(frozen=False)

    temperature: Annotated[float, icon("thermometer", unit="°C")] = Field(18.5, title="Teplota")
    lights: Annotated[bool, icon("bulb", on_color="#fbbf24")] = Field(True, title="Světla")
    persons: Annotated[int, icon("person")] = Field(0, title="Osoby")


class LivingRoomState(BaseModel):
    """Stav obývacího pokoje."""

    model_config = ConfigDict(frozen=False)

    temperature: Annotated[float, icon("thermometer", unit="°C")] = Field(21.0, title="Teplota")
    lights: Annotated[bool, icon("bulb", on_color="#fbbf24")] = Field(True, title="Světla")
    persons: Annotated[int, icon("person")] = Field(2, title="Osoby")


class HouseState(BaseModel):
    """Kompletní stav chytré domácnosti — základ Live State vizualizace v GUI.

    Každé pole s `room(...)` anotací se zobrazí jako místnost v panelu Live State.
    """

    model_config = ConfigDict(frozen=False)

    kuchyne: Annotated[KitchenState, room("Kuchyně", col_span=2)] = Field(
        default_factory=KitchenState
    )
    loznice: Annotated[BedroomState, room("Ložnice")] = Field(default_factory=BedroomState)
    obyvak: Annotated[LivingRoomState, room("Obývák")] = Field(default_factory=LivingRoomState)


# Sdílená instance — modifikována nástroji, sledována GUI live state viewerem
_HOUSE = HouseState()

# ---------------------------------------------------------------------------
# Stav, patch a signály agenta
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SmartHomeState:
    """Neměnný snímek pracovního stavu agenta předávaný mezi vrcholy."""

    messages: Annotated[tuple[dict, ...], operator.add] = field(default_factory=tuple)
    intent: str = ""
    action_plan: str = ""
    rejection_reason: str = ""
    revisions: int = 0
    final_response: str = ""


@dataclass(frozen=True)
class SmartHomePatch:
    """Částečná aktualizace vrácená každým vrcholem; runner ji sloučí do SmartHomeState."""

    messages: tuple[dict, ...] | object = UNSET
    intent: str | object = UNSET
    action_plan: str | object = UNSET
    rejection_reason: str | object = UNSET
    revisions: int | object = UNSET
    final_response: str | object = UNSET


class SmartHomeSignal(Signal):
    """Rozhodnutí o směrování vrácená každým vrcholem."""

    parsed = "parsed"
    proposed = "proposed"
    approved = "approved"
    rejected = "rejected"
    done = "done"


# ---------------------------------------------------------------------------
# Nástroje — modifikují _HOUSE přímo (GUI okamžitě vidí změny)
# ---------------------------------------------------------------------------


class GetCurrentStatus(ToolBase):
    """Vrátí teplotu, stav osvětlení a obsazenost místnosti."""

    name = "get_current_status"
    description = "Vrátí aktuální stav místnosti (teplota, světla, osoby)."

    @param_desc(room_id="Název místnosti: 'kuchyne', 'loznice' nebo 'obyvak'.")
    def execute(self, room_id: str) -> str:
        room_state = getattr(_HOUSE, room_id, None)
        if room_state is None:
            return f"Neznámá místnost '{room_id}'. Dostupné: kuchyne, loznice, obyvak."
        stove_part = ""
        if isinstance(room_state, KitchenState):
            stove_part = f", sporák={'zapnut' if room_state.stove else 'vypnut'}"
        return (
            f"Místnost '{room_id}': teplota={room_state.temperature}°C, "
            f"světla={'zapnuta' if room_state.lights else 'vypnuta'}, "
            f"osoby={room_state.persons}{stove_part}."
        )


class SetTemperature(ToolBase):
    """Nastaví cílovou teplotu v místnosti."""

    name = "set_temperature"
    description = "Nastaví cílovou teplotu (°C) v dané místnosti."

    @param_desc(
        room_id="Název místnosti: 'kuchyne', 'loznice' nebo 'obyvak'.",
        celsius="Cílová teplota jako číslo, např. '22' nebo '22.5'.",
    )
    def execute(self, room_id: str, celsius: str) -> str:
        room_state = getattr(_HOUSE, room_id, None)
        if room_state is None:
            return f"Neznámá místnost '{room_id}'."
        temp = float(celsius)
        room_state.temperature = temp  # Pydantic model_config frozen=False
        return f"Teplota v '{room_id}' nastavena na {temp}°C."


class ToggleDevice(ToolBase):
    """Zapne nebo vypne zařízení nebo světlo."""

    name = "toggle_device"
    description = "Zapne nebo vypne zařízení. Formát device_id: 'místnost.zařízení'."

    @param_desc(
        device_id="Zařízení k ovládání, např. 'kuchyne.lights' nebo 'kuchyne.stove'.",
        state="Požadovaný stav: 'on' (zapnout) nebo 'off' (vypnout).",
    )
    def execute(self, device_id: str, state: str) -> str:
        parts = device_id.split(".", 1)
        if len(parts) != 2:
            return "Neplatný device_id. Použij formát 'místnost.zařízení'."
        room_key, device = parts
        room_state = getattr(_HOUSE, room_key, None)
        if room_state is None:
            return f"Neznámá místnost '{room_key}'."
        if not hasattr(room_state, device):
            return f"Neznámé zařízení '{device}' v místnosti '{room_key}'."
        setattr(room_state, device, state.lower() == "on")
        status = "zapnuto" if state.lower() == "on" else "vypnuto"
        return f"'{device_id}' {status}."


# ---------------------------------------------------------------------------
# Vrcholy
# ---------------------------------------------------------------------------


class IntentParserVertex(LlmStateVertex):
    """Rozpozná kategorii uživatelského požadavku."""

    model: Annotated[str, Field(
        description="Název LLM modelu (např. 'gpt-4o-mini'). Prázdný = pool default.",
        json_schema_extra={"x-model-select": True},
    )] = "gpt-4o-mini"

    system_prompt: Annotated[str, Field(
        description="Instrukce pro klasifikaci záměru uživatele.",
        json_schema_extra={"x-textarea": True},
    )] = (
        "Klasifikuj požadavek uživatele pro chytrou domácnost. "
        "Odpověz: 'KATEGORIE: <OSVĚTLENÍ|TEPLOTA|SPOTŘEBIČ|DOTAZ_NA_STAV|NEZNÁMÉ>' "
        "Odpovídej česky."
    )

    async def run(
        self, state: SmartHomeState, ctx: Context
    ) -> tuple[SmartHomeSignal, SmartHomePatch]:
        response = await ctx.llm_for_model(self.model).achat([
            {"role": "system", "content": self.system_prompt},
            *list(state.messages),
        ], temperature=self.temperature)
        return SmartHomeSignal.parsed, SmartHomePatch(intent=response.text.strip())


class DeviceWorkerVertex(LlmStateVertex):
    """Kontroluje stav zařízení a navrhuje akce; smí volat nástroje."""

    model: Annotated[str, Field(
        description="Název LLM modelu (např. 'gpt-4o-mini'). Prázdný = pool default.",
        json_schema_extra={"x-model-select": True},
    )] = "gpt-4o-mini"

    system_prompt: Annotated[str, Field(
        description="Instrukce pro plánování akcí se zařízeními.",
        json_schema_extra={"x-textarea": True},
    )] = _SYSTEM_PROMPT

    max_rounds: Annotated[int, Field(ge=1, le=10, description="Maximální počet kol nástrojů.")] = 4

    async def run(
        self, state: SmartHomeState, ctx: Context
    ) -> tuple[SmartHomeSignal, SmartHomePatch]:
        messages: list[dict] = [{"role": "system", "content": self.system_prompt}]
        messages.extend(state.messages)
        if state.rejection_reason:
            messages.append({
                "role": "user",
                "content": (
                    f"Tvůj předchozí plán byl zamítnut: {state.rejection_reason}. "
                    "Navrhni opravenou verzi."
                ),
            })
        response = await ctx.llm_for_model(self.model).achat_with_tools(
            messages=messages,
            registry=ctx.get_tools(),
            max_rounds=self.max_rounds,
        )
        return SmartHomeSignal.proposed, SmartHomePatch(action_plan=response.text.strip())


class SafetyJudgeVertex(LlmStateVertex):
    """Ověří navržený plán vůči bezpečnostním pravidlům."""

    model: Annotated[str, Field(
        description="Název LLM modelu (např. 'gpt-4o-mini'). Prázdný = pool default.",
        json_schema_extra={"x-model-select": True},
    )] = "gemini-3.5-flash"

    system_prompt: Annotated[str, Field(
        description="Bezpečnostní pravidla pro validaci akčního plánu.",
        json_schema_extra={"x-textarea": True},
    )] = (
        "Ověř, zda akční plán splňuje bezpečnostní pravidla chytré domácnosti:\n"
        "1. Teplota místnosti nesmí klesnout pod 10 °C ani přesáhnout 30 °C.\n"
        "2. Sporák nesmí být zapnut, pokud v kuchyni nejsou přítomny osoby.\n"
        "3. Světla nesmí být rozsvícena v neobsazené místnosti (osoby=0).\n"
        "Pokud plán vyhovuje, odpověz 'SCHVÁLENO'.\n"
        "Jinak začni 'ZAMÍTNUTO: <důvod>'.\n"
        "Odpovídej česky."
    )

    max_revisions: Annotated[int, Field(ge=1, le=5, description="Max. kol oprav Worker→Judge.")] = 2

    async def run(
        self, state: SmartHomeState, ctx: Context
    ) -> tuple[SmartHomeSignal, SmartHomePatch]:
        if state.revisions >= self.max_revisions:
            return SmartHomeSignal.approved, SmartHomePatch(revisions=state.revisions + 1)

        response = await ctx.llm_for_model(self.model).achat([
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": state.action_plan},
        ], temperature=self.temperature)
        text = response.text.strip()

        if text.upper().startswith("SCHVÁLENO") or text.upper().startswith("APPROVED"):
            return SmartHomeSignal.approved, SmartHomePatch(revisions=state.revisions + 1)

        reason = text[text.index(":") + 1:].strip() if ":" in text else text
        return SmartHomeSignal.rejected, SmartHomePatch(
            rejection_reason=reason, revisions=state.revisions + 1
        )


class VoiceFormatterVertex(LlmStateVertex):
    """Převede schválený plán na krátkou, přirozenou odpověď připravenou pro TTS."""

    model: Annotated[str, Field(
        description="Název LLM modelu (např. 'gpt-4o-mini'). Prázdný = pool default.",
        json_schema_extra={"x-model-select": True},
    )] = "gpt-4o-mini"

    system_prompt: Annotated[str, Field(
        description="Instrukce pro formátování plánu jako hlasové odpovědi.",
        json_schema_extra={"x-textarea": True},
    )] = (
        "Převeď akční plán chytré domácnosti na krátkou hlasovou odpověď "
        "pro chytrý reproduktor. Bez formátování, max 2 věty, potvrď co bylo provedeno. "
        "Odpovídej česky."
    )

    async def run(
        self, state: SmartHomeState, ctx: Context
    ) -> tuple[SmartHomeSignal, SmartHomePatch]:
        response = await ctx.llm_for_model(self.model).achat([
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": state.action_plan},
        ], temperature=self.temperature)
        return SmartHomeSignal.done, SmartHomePatch(final_response=response.text.strip())


# ---------------------------------------------------------------------------
# Sestavení aplikace
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _app = AgentApp(
        doc=__doc__,
        system_prompt=_SYSTEM_PROMPT,
        default_question=_DEFAULT_QUESTION,
        sample_prompts=[
            "Rozsviť světlo v kuchyni a nastav teplotu na 22 stupňů.",
            "Zhasni světlo v ložnici.",
            "Jaká je aktuální teplota v obývacím pokoji?",
            "Nastav teplotu v ložnici na 4 stupně.",
            "Zapni sporák v kuchyni.",
        ],
        # Live state — HouseState se automaticky zobrazí v GUI panelu
        live_state=_HOUSE,
        initial_state_factory=lambda q: SmartHomeState(
            messages=(
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": q},
            ),
        ),
        context=Context(
            pool=LlmPool(cache=LlmFileCache(__file__)),
            tool_registries={
                "default": ToolRegistry([
                    GetCurrentStatus(), SetTemperature(), ToggleDevice(),
                ]),
            },
        ),
        state_graph=StateGraph(
            start=IntentParserVertex,
            initialized_vertexes=[
                SafetyJudgeVertex(max_revisions=2),
                DeviceWorkerVertex(max_rounds=4),
                IntentParserVertex(),
                VoiceFormatterVertex(),
            ],
            transitions=[
                Transition(IntentParserVertex,  SmartHomeSignal.parsed,   DeviceWorkerVertex),
                Transition(DeviceWorkerVertex,  SmartHomeSignal.proposed, SafetyJudgeVertex),
                Transition(SafetyJudgeVertex,   SmartHomeSignal.rejected, DeviceWorkerVertex),
                Transition(SafetyJudgeVertex,   SmartHomeSignal.approved, VoiceFormatterVertex),
                Transition(VoiceFormatterVertex, SmartHomeSignal.done,    StdEnd),
            ],
        ),
    )

    _app.cli(__doc__, name=__name__)
