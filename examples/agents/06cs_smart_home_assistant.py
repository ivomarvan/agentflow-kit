"""# Hlasový dispečer pro chytrou domácnost

Vzor Worker/Judge s bezpečnostní validací.

## Pipeline

1. **IntentParser** — rozpozná kategorii požadavku
2. **DeviceWorker** — zkontroluje stav místností nástroji, navrhne akce:
   - `get_current_status` — teplota, světla, obsazenost místnosti
   - `set_temperature`    — nastaví cílovou teplotu v °C
   - `toggle_device`      — zapne/vypne světla nebo sporák
3. **SafetyJudge** — ověří plán vůči bezpečnostním pravidlům; zamítne při porušení
4. **VoiceFormatter** — vytvoří stručnou odpověď připravenou pro TTS

Pokud Judge plán zamítne, Worker ho opraví (max 2 pokusy).

## Demonstruje

- Smyčku Worker/Judge s LLM a voláním nástrojů
- `StateVertex` jako Pydantic BaseModel s poli editovatelnými v Inspektoru
- Dvě úrovně LLM konektorů (ekonomická vs. kvalitní)
- Typovaný stav bez `cast()`, `ctx.stats` po dokončení
- Deklarativní `AgentApp` s příkazy `run` / `graph` / `gui`
"""

# Spuštění:
#     uv run python examples/agents/06cs_smart_home_assistant.py run
#     uv run python examples/agents/06cs_smart_home_assistant.py graph --browser
#     uv run python examples/agents/06cs_smart_home_assistant.py -h

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated

from pydantic import Field

from agentflow import AgentApp
from agentflow.llm.cache import LlmFileCache
from agentflow.llm.LlmPool import LlmPool
from agentflow.statemachine import (
    Context,
    Signal,
    StateGraph,
    LlmStateVertex,
    StateVertex,
    StdEnd,
    Transition,
    UNSET,
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
# Stav, patch a signály
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SmartHomeState:
    """Neměnný snímek stavu předávaný mezi vrcholy.

    Atributy:
        messages:         Historie konverzace (systém + uživatel + asistent).
        intent:           Kategorie z IntentParseru (OSVĚTLENÍ, TEPLOTA, …).
        action_plan:      Navržené akce od DeviceWorkeru.
        rejection_reason: Poslední důvod zamítnutí od SafetyJudge; prázdný, pokud žádný.
        revisions:        Počet dokončených smyček Worker→Judge.
        final_response:   TTS-ready odpověď od VoiceFormatteru.
    """

    messages:         Annotated[tuple[dict, ...], operator.add] = field(default_factory=tuple)
    intent:           str = ""
    action_plan:      str = ""
    rejection_reason: str = ""
    revisions:        int = 0
    final_response:   str = ""


@dataclass(frozen=True)
class SmartHomePatch:
    """Částečná aktualizace vrácená každým vrcholem; runner ji sloučí do SmartHomeState.

    Nastav pouze pole, která vrchol skutečně mění; ostatní nech jako UNSET.
    Prázdný řetězec předej explicitně, když je třeba pole vymazat.
    """

    messages:         tuple[dict, ...] | object = UNSET
    intent:           str | object = UNSET
    action_plan:      str | object = UNSET
    rejection_reason: str | object = UNSET
    revisions:        int | object = UNSET
    final_response:   str | object = UNSET


class SmartHomeSignal(Signal):
    """Rozhodnutí o směrování vrácená každým vrcholem."""

    parsed   = "parsed"    # IntentParser  → DeviceWorker
    proposed = "proposed"  # DeviceWorker  → SafetyJudge
    approved = "approved"  # SafetyJudge   → VoiceFormatter
    rejected = "rejected"  # SafetyJudge   → DeviceWorker (opakování)
    done     = "done"      # VoiceFormatter → StdEnd


# ---------------------------------------------------------------------------
# Nástroje (stubové implementace — nahraď skutečným API chytré domácnosti)
# ---------------------------------------------------------------------------

_HOUSE_STATE: dict[str, dict] = {
    "kuchyne": {"temperature": 20.0, "lights": False, "persons": 1, "stove": False},
    "loznice": {"temperature": 18.5, "lights": True,  "persons": 0},
    "obyvak":  {"temperature": 21.0, "lights": True,  "persons": 2},
}


class GetCurrentStatus(ToolBase):
    """Vrátí teplotu, stav osvětlení a obsazenost místnosti."""

    name = "get_current_status"
    description = "Vrátí aktuální stav místnosti (teplota, světla, osoby)."

    @param_desc(room_id="Název místnosti: 'kuchyne', 'loznice' nebo 'obyvak'.")
    def execute(self, room_id: str) -> str:
        room = _HOUSE_STATE.get(room_id)
        if room is None:
            return f"Neznámá místnost '{room_id}'. Dostupné: {', '.join(_HOUSE_STATE)}."
        return (
            f"Místnost '{room_id}': teplota={room['temperature']}°C, "
            f"světla={'zapnuta' if room['lights'] else 'vypnuta'}, "
            f"osoby={room['persons']}"
            + (f", sporák={'zapnut' if room.get('stove') else 'vypnut'}" if "stove" in room else "")
            + "."
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
        if room_id not in _HOUSE_STATE:
            return f"Neznámá místnost '{room_id}'."
        temp = float(celsius)
        _HOUSE_STATE[room_id]["temperature"] = temp
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
            return "Neplatný device_id. Použij formát 'místnost.zařízení', např. 'kuchyne.lights'."
        room, device = parts
        if room not in _HOUSE_STATE:
            return f"Neznámá místnost '{room}'."
        if device not in _HOUSE_STATE[room]:
            return f"Neznámé zařízení '{device}' v místnosti '{room}'."
        _HOUSE_STATE[room][device] = state.lower() == "on"
        return f"'{device_id}' {'zapnuto' if state.lower() == 'on' else 'vypnuto'}."


# ---------------------------------------------------------------------------
# Vrcholy
#
# Každý vrchol je Pydantic BaseModel (přes LlmStateVertex/StateVertex).
# Pole deklarovaná jako Annotated[T, Field(...)] jsou editovatelná v GUI Inspektoru.
# json_schema_extra={"x-textarea": True} způsobí víceřádkový editor v Inspektoru;
# runtime hodnota zůstává prostý řetězec str.
# ---------------------------------------------------------------------------


class IntentParserVertex(LlmStateVertex):
    """Rozpozná kategorii uživatelského požadavku před předáním DeviceWorkeru."""

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
        """Zavolá LLM pro klasifikaci záměru; extrahuje řádek KATEGORIE: z odpovědi."""
        response = await ctx.llm_for_model(self.model).achat([
            {"role": "system", "content": self.system_prompt},
            *state.messages,
        ], temperature=self.temperature)
        intent = "NEZNÁMÉ"
        for line in response.text.splitlines():
            if line.startswith("KATEGORIE:"):
                intent = line.split(":", 1)[1].strip()
                break
        return SmartHomeSignal.parsed, SmartHomePatch(intent=intent)


class DeviceWorkerVertex(LlmStateVertex):
    """Zkontroluje stav místností nástroji, pak navrhne akce se zařízeními.

    Při opakování po zamítnutí se rejection_reason přidá do systémového promptu,
    aby LLM mohl plán opravit.
    """

    model: Annotated[str, Field(
        description="Název LLM modelu (např. 'gpt-4o-mini'). Prázdný = pool default.",
        json_schema_extra={"x-model-select": True},
    )] = "gpt-4o-mini"

    tools:      Annotated[str, Field(description="Klíč registru nástrojů z Contextu.")] = "default"
    max_rounds: Annotated[int, Field(ge=1, le=10, description="Max kol volání nástrojů.")] = 4
    system_prompt: Annotated[str, Field(
        description="Instrukce pro navrhování akcí se zařízeními pomocí nástrojů.",
        json_schema_extra={"x-textarea": True},
    )] = (
        "Ovládáš chytrou domácnost. Pomocí nástrojů zkontroluj aktuální stav místností, "
        "pak navrhni konkrétní akce přehledně seřazené po řádcích. "
        "Odpovídej česky."
    )

    async def run(
        self, state: SmartHomeState, ctx: Context
    ) -> tuple[SmartHomeSignal, SmartHomePatch]:
        """Spustí smyčku LLM+nástroje; při opakování přidá nápovědou k opravě."""
        correction = (
            f"\n\nTvůj předchozí plán byl ZAMÍTNUT: {state.rejection_reason}\n"
            "Oprav plán tak, aby byl bezpečný."
            if state.rejection_reason else ""
        )
        response = await ctx.llm_for_model(self.model).achat_with_tools(
            messages=[
                {"role": "system", "content": self.system_prompt + correction},
                *state.messages,
            ],
            registry=ctx.get_tools(self.tools),
            max_rounds=self.max_rounds,
            temperature=self.temperature,
        )
        return SmartHomeSignal.proposed, SmartHomePatch(
            action_plan=response.text, rejection_reason=""
        )


class SafetyJudgeVertex(LlmStateVertex):
    """Ověří plán vůči bezpečnostním pravidlům; schválí nebo zamítne s důvodem.

    Po dosažení max_revisions vynucuje schválení, aby se předešlo nekonečné smyčce.
    """

    model: Annotated[str, Field(
        description="Název LLM modelu (např. 'gpt-4o-mini'). Prázdný = pool default.",
        json_schema_extra={"x-model-select": True},
    )] = "gemini-3.5-flash"

    max_revisions: Annotated[int, Field(ge=1, le=3,
                       description="Max smyček Worker→Judge před vynuceným schválením.")] = 2
    system_prompt: Annotated[str, Field(
        description="Bezpečnostní pravidla pro ověření navrženého plánu.",
        json_schema_extra={"x-textarea": True},
    )] = """\
Jsi bezpečnostní inspektor systému chytré domácnosti. Posouď navržený akční plán.

BEZPEČNOSTNÍ PRAVIDLA:
1. Teplota musí být v rozsahu 10 °C až 28 °C v každé místnosti.
2. Nikdy nezapínej sporák ani troubu, pokud v místnosti není přítomna žádná osoba.
3. Nikdy nenastavuj teplotu pod 15 °C v místnosti, kde je osoba přítomna.
4. Bezpečnostní kamery nesmí být vypnuty vzdáleně.

Pokud je plán BEZPEČNÝ:  odpověz přesně "SCHVÁLENO: <jednořádkové potvrzení>"
Pokud je plán NEBEZPEČNÝ: odpověz přesně "ZAMÍTNUTO: <porušené pravidlo a jak ho opravit>"
Odpovídej česky.
"""

    async def run(
        self, state: SmartHomeState, ctx: Context
    ) -> tuple[SmartHomeSignal, SmartHomePatch]:
        """Požádá kvalitní LLM o revizi plánu; rozpozná SCHVÁLENO/ZAMÍTNUTO v odpovědi."""
        if state.revisions >= self.max_revisions:
            ctx.logger.warning(
                "max_revisions=%d dosaženo; vynucuji schválení", self.max_revisions
            )
            return SmartHomeSignal.approved, SmartHomePatch(revisions=state.revisions + 1)

        response = await ctx.llm_for_model(self.model).achat([
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Akční plán k posouzení:\n{state.action_plan}"},
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
        "Převeď následující akční plán chytré domácnosti na krátkou, přirozenou hlasovou odpověď "
        "pro chytrý reproduktor. Pravidla: bez formátování, bez odrážek, "
        "max 2 věty, teplý a přátelský tón, potvrď co bylo provedeno. "
        "Odpovídej česky."
    )

    async def run(
        self, state: SmartHomeState, ctx: Context
    ) -> tuple[SmartHomeSignal, SmartHomePatch]:
        """Zformátuje schválený plán do final_response."""
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
            "Nastav teplotu v ložnici na 4 stupně.",    # Bezpečnost: pod limitem → zamítne
            "Zapni sporák v kuchyni.",                  # Bezpečnost: nikdo v kuchyni → zamítne
        ],
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
