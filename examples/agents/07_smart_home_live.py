"""# Smart Home Voice Dispatcher — with Live State Visualisation

Extends ``06_smart_home.py`` with a Pydantic ``HouseState`` model that drives
the GUI Live State panel: room temperatures, lights, and the stove update in
real-time as the agent executes each command.

## What's new versus 06_smart_home.py

- ``HouseState`` — Pydantic model with ``icon()`` / ``room()`` GUI annotations
- Three tool classes override the base-file versions to mutate ``_HOUSE``
  directly instead of a plain dict, so the Live State panel reflects every change
- ``AgentApp(live_state=_HOUSE, …)`` — enables the Live State panel in the GUI
  Chat tab; the panel shows the initial house state immediately on page load
- All vertices and state/patch/signal types are **imported** from ``06_smart_home``

## Note on importing from a digit-prefixed module

Python's ``import`` statement cannot import a module whose name starts with a
digit.  The standard workaround is ``importlib.util.spec_from_file_location()``,
which loads the module directly from its file path without naming constraints.
"""

# Run:
#     uv run python examples/agents/07_smart_home_live.py run
#     uv run python examples/agents/07_smart_home_live.py graph --browser
#     uv run python examples/agents/07_smart_home_live.py gui
#     uv run python examples/agents/07_smart_home_live.py -h

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from agentflow import AgentApp
from agentflow.llm.cache import LlmFileCache
from agentflow.llm.LlmPool import LlmPool
from agentflow.statemachine import (
    Context,
    StateGraph,
    StdEnd,
    Transition,
)
from agentflow.gui.state_viewer import icon, room
from agentflow.tools.Tool import ToolBase, param_desc
from agentflow.tools.ToolRegistry import ToolRegistry

# ---------------------------------------------------------------------------
# Import reusable symbols from 06_smart_home.py
#
# spec_from_file_location is required because Python identifiers cannot start
# with a digit, making a plain ``import 06_smart_home`` a syntax error.
# ---------------------------------------------------------------------------

def _load_base() -> object:
    """Load 06_smart_home.py as a module object using importlib."""
    spec = importlib.util.spec_from_file_location(
        "_smart_home_base",
        Path(__file__).with_name("06_smart_home.py"),
    )
    mod = importlib.util.module_from_spec(spec)      # type: ignore[arg-type]
    # Must register before exec_module: @dataclass resolves annotations via sys.modules
    sys.modules["_smart_home_base"] = mod
    spec.loader.exec_module(mod)                     # type: ignore[union-attr]
    return mod


_base = _load_base()

# Reuse state, patch, signals, and all four vertices unchanged
SmartHomeState       = _base.SmartHomeState        # type: ignore[attr-defined]
SmartHomePatch       = _base.SmartHomePatch        # type: ignore[attr-defined]
SmartHomeSignal      = _base.SmartHomeSignal       # type: ignore[attr-defined]
IntentParserVertex   = _base.IntentParserVertex    # type: ignore[attr-defined]
DeviceWorkerVertex   = _base.DeviceWorkerVertex    # type: ignore[attr-defined]
SafetyJudgeVertex    = _base.SafetyJudgeVertex     # type: ignore[attr-defined]
VoiceFormatterVertex = _base.VoiceFormatterVertex  # type: ignore[attr-defined]
_DEFAULT_QUESTION    = _base._DEFAULT_QUESTION     # type: ignore[attr-defined]
_SYSTEM_PROMPT       = _base._SYSTEM_PROMPT        # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Live state models — Pydantic with display annotations
#
# icon("name")  → rendered as emoji + value/dot in the Live State panel
# room("Label") → groups a nested model into a labelled room box
# ---------------------------------------------------------------------------


class KitchenState(BaseModel):
    """Kitchen room: temperature, lights, stove, and person count."""

    model_config = ConfigDict(frozen=False)

    temperature: Annotated[float, icon("thermometer", unit="°C")] = Field(20.0, title="Temperature")
    lights:      Annotated[bool,  icon("bulb",        on_color="#fbbf24")] = Field(False, title="Lights")
    stove:       Annotated[bool,  icon("flame",       on_color="#ef4444")] = Field(False, title="Stove")
    persons:     Annotated[int,   icon("person")]                          = Field(1,     title="Persons")


class BedroomState(BaseModel):
    """Bedroom room: temperature, lights, person count."""

    model_config = ConfigDict(frozen=False)

    temperature: Annotated[float, icon("thermometer", unit="°C")] = Field(18.5, title="Temperature")
    lights:      Annotated[bool,  icon("bulb",        on_color="#fbbf24")] = Field(True,  title="Lights")
    persons:     Annotated[int,   icon("person")]                          = Field(0,     title="Persons")


class LivingRoomState(BaseModel):
    """Living room: temperature, lights, person count."""

    model_config = ConfigDict(frozen=False)

    temperature: Annotated[float, icon("thermometer", unit="°C")] = Field(21.0, title="Temperature")
    lights:      Annotated[bool,  icon("bulb",        on_color="#fbbf24")] = Field(True,  title="Lights")
    persons:     Annotated[int,   icon("person")]                          = Field(2,     title="Persons")


class HouseState(BaseModel):
    """Complete house state — drives the GUI Live State panel.

    Fields annotated with ``room()`` appear as labelled room boxes in the Chat tab.
    The col_span value controls how many grid columns the room box occupies.
    """

    model_config = ConfigDict(frozen=False)

    kitchen: Annotated[KitchenState,    room("Kitchen",     col_span=2)] = Field(default_factory=KitchenState)
    bedroom: Annotated[BedroomState,    room("Bedroom")]                 = Field(default_factory=BedroomState)
    living:  Annotated[LivingRoomState, room("Living Room")]             = Field(default_factory=LivingRoomState)


# Shared mutable instance — mutated by the overridden tools below;
# monitored by the GUI Live State panel via AgentApp(live_state=_HOUSE).
_HOUSE = HouseState()

# ---------------------------------------------------------------------------
# Overridden tools — identical API to the base file, but read/write _HOUSE
# (a Pydantic model) instead of the plain dict in 06_smart_home.py
# ---------------------------------------------------------------------------


class GetCurrentStatus(ToolBase):
    """Return temperature, light state and occupancy for a room."""

    name = "get_current_status"
    description = "Return current state (temperature, lights, persons) for the given room."

    @param_desc(room_id="Room name: 'kitchen', 'bedroom', or 'living'.")
    def execute(self, room_id: str) -> str:
        """Read room attributes from the Pydantic HouseState model."""
        room_state = getattr(_HOUSE, room_id, None)
        if room_state is None:
            return f"Unknown room '{room_id}'. Available: kitchen, bedroom, living."
        stove_part = (
            f", stove={'on' if room_state.stove else 'off'}"
            if isinstance(room_state, KitchenState) else ""
        )
        return (
            f"Room '{room_id}': temperature={room_state.temperature}°C, "
            f"lights={'on' if room_state.lights else 'off'}, "
            f"persons={room_state.persons}{stove_part}."
        )


class SetTemperature(ToolBase):
    """Set the target temperature for a room."""

    name = "set_temperature"
    description = "Set the target temperature (°C) in the given room."

    @param_desc(
        room_id="Room name: 'kitchen', 'bedroom', or 'living'.",
        celsius="Target temperature as a number, e.g. '22' or '22.5'.",
    )
    def execute(self, room_id: str, celsius: str) -> str:
        """Update temperature on the Pydantic model; GUI reflects the change instantly."""
        room_state = getattr(_HOUSE, room_id, None)
        if room_state is None:
            return f"Unknown room '{room_id}'."
        temp = float(celsius)
        room_state.temperature = temp  # mutable because model_config frozen=False
        return f"Temperature in '{room_id}' set to {temp}°C."


class ToggleDevice(ToolBase):
    """Turn a device or light on or off."""

    name = "toggle_device"
    description = "Turn a device or light on or off. device_id format: 'room.device'."

    @param_desc(
        device_id="Device to control, e.g. 'kitchen.lights' or 'kitchen.stove'.",
        state="Desired state: 'on' or 'off'.",
    )
    def execute(self, device_id: str, state: str) -> str:
        """Set the boolean attribute on the Pydantic model; GUI reflects the change."""
        parts = device_id.split(".", 1)
        if len(parts) != 2:
            return "Invalid device_id. Use format 'room.device', e.g. 'kitchen.lights'."
        room_key, device = parts
        room_state = getattr(_HOUSE, room_key, None)
        if room_state is None:
            return f"Unknown room '{room_key}'."
        if not hasattr(room_state, device):
            return f"Unknown device '{device}' in room '{room_key}'."
        setattr(room_state, device, state.lower() == "on")
        return f"'{device_id}' turned {state.lower()}."


# ---------------------------------------------------------------------------
# House state snapshot / restore
#
# DeviceWorker calls tools that mutate _HOUSE eagerly, before SafetyJudge
# validates the plan.  If the Judge rejects, we restore the pre-execution
# snapshot so the retry starts from a clean state.
# ---------------------------------------------------------------------------

_HOUSE_SNAPSHOT: dict = {}


def _snapshot_house() -> None:
    """Capture a deep copy of _HOUSE fields into the module-level snapshot dict."""
    global _HOUSE_SNAPSHOT
    _HOUSE_SNAPSHOT = _HOUSE.model_dump()


def _restore_house_from_snapshot() -> None:
    """Write the last snapshot back into _HOUSE (field by field)."""
    if not _HOUSE_SNAPSHOT:
        return
    for room_key, room_data in _HOUSE_SNAPSHOT.items():
        room_state = getattr(_HOUSE, room_key, None)
        if room_state is not None and isinstance(room_data, dict):
            for attr, val in room_data.items():
                setattr(room_state, attr, val)


class LiveDeviceWorkerVertex(DeviceWorkerVertex):
    """DeviceWorker that snapshots/restores _HOUSE around each tool-calling round.

    On first call (no rejection yet): snapshot _HOUSE before tools run.
    On retry (rejection_reason is set): restore _HOUSE first, then snapshot again
    before the new round of tool calls, so the LLM starts from a consistent state.

    This guarantees that _HOUSE (and the Live State panel) reflects only the
    *approved* final outcome — not any intermediate rejected proposals.
    """

    async def run(self, state: object, ctx: Context) -> object:  # type: ignore[override]
        rejection_reason = getattr(state, "rejection_reason", "")
        if rejection_reason:
            # Roll back eager mutations from the rejected execution round
            _restore_house_from_snapshot()
        # Snapshot before this round's tool calls so we can roll back if rejected
        _snapshot_house()
        return await super().run(state, ctx)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Application wiring — identical graph to 06_smart_home.py; only the tools,
# LiveDeviceWorkerVertex, and live_state= differ
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _app = AgentApp(
        doc=__doc__,
        system_prompt=_SYSTEM_PROMPT,
        default_question=_DEFAULT_QUESTION,
        sample_prompts=[
            "Turn on the kitchen lights and set the temperature to 22 degrees.",
            "Turn off all the bedroom lights.",
            "What's the current temperature in the living room?",
            "Set the bedroom temperature to 4 degrees.",   # Safety: below limit → rejected
            "Turn on the kitchen stove.",                  # Safety: nobody in kitchen → rejected
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
        live_state=_HOUSE,
        state_graph=StateGraph(
            start=IntentParserVertex,
            initialized_vertexes=[
                SafetyJudgeVertex(max_revisions=2),
                LiveDeviceWorkerVertex(max_rounds=4),
                IntentParserVertex(),
                VoiceFormatterVertex(),
            ],
            transitions=[
                Transition(IntentParserVertex,      SmartHomeSignal.parsed,   LiveDeviceWorkerVertex),
                Transition(LiveDeviceWorkerVertex,  SmartHomeSignal.proposed, SafetyJudgeVertex),
                Transition(SafetyJudgeVertex,       SmartHomeSignal.rejected, LiveDeviceWorkerVertex),
                Transition(SafetyJudgeVertex,       SmartHomeSignal.approved, VoiceFormatterVertex),
                Transition(VoiceFormatterVertex,    SmartHomeSignal.done,     StdEnd),
            ],
        ),
    )

    _app.cli(__doc__, name=__name__)
