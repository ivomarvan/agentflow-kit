"""# Smart Home Voice Dispatcher

Worker/Judge pattern with safety validation.

## Pipeline

1. **IntentParser** — classifies the user request into a category
2. **DeviceWorker** — calls tools to inspect rooms, then proposes actions:
   - `get_current_status` — temperature, lights, occupancy for a room
   - `set_temperature`    — set target °C in a room
   - `toggle_device`      — turn lights or stove on/off
3. **SafetyJudge** — validates the plan; rejects if rules are violated
4. **VoiceFormatter** — produces a concise TTS-ready reply

If the Judge rejects the plan, the Worker revises it (max 2 retries).

## Demonstrates

- Worker/Judge review loop with tool-calling LLMs
- `StateVertex` as Pydantic BaseModel with Inspector-editable fields
- Two LLM connector tiers (economy vs quality)
- Typed state without `cast()`, `ctx.stats` after run
- Declarative `AgentApp` with `run` / `graph` / `gui`
"""

# Run:
#     uv run python examples/agents/06_smart_home.py run
#     uv run python examples/agents/06_smart_home.py graph --browser
#     uv run python examples/agents/06_smart_home.py gui
#     uv run python examples/agents/06_smart_home.py -h

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
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_QUESTION = "Turn on the kitchen lights and set the temperature to 22 degrees."

_SYSTEM_PROMPT = (
    "You are a smart home assistant. "
    "Use tools to check the current state of rooms before proposing changes. "
    "Safety is the top priority."
)

# ---------------------------------------------------------------------------
# State, patch and signals
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SmartHomeState:
    """Immutable state snapshot passed between vertices.

    Attributes:
        messages:         Conversation history (system + user + assistant turns).
        intent:           Category from IntentParser (LIGHTING, TEMPERATURE, …).
        action_plan:      DeviceWorker's proposed actions.
        rejection_reason: SafetyJudge's latest rejection message; empty when none.
        revisions:        Number of Worker→Judge loops completed.
        final_response:   TTS-ready reply from VoiceFormatter.
    """

    messages:         Annotated[tuple[dict, ...], operator.add] = field(default_factory=tuple)
    intent:           str = ""
    action_plan:      str = ""
    rejection_reason: str = ""
    revisions:        int = 0
    final_response:   str = ""


@dataclass(frozen=True)
class SmartHomePatch:
    """Partial update returned by each vertex; runner merges it into SmartHomeState.

    Only set the fields a vertex actually changes; leave the rest as UNSET.
    Pass an empty string explicitly when a field must be cleared.
    """

    messages:         tuple[dict, ...] | object = UNSET
    intent:           str | object = UNSET
    action_plan:      str | object = UNSET
    rejection_reason: str | object = UNSET
    revisions:        int | object = UNSET
    final_response:   str | object = UNSET


class SmartHomeSignal(Signal):
    """Routing decisions emitted by each vertex."""

    parsed   = "parsed"    # IntentParser  → DeviceWorker
    proposed = "proposed"  # DeviceWorker  → SafetyJudge
    approved = "approved"  # SafetyJudge   → VoiceFormatter
    rejected = "rejected"  # SafetyJudge   → DeviceWorker (retry loop)
    done     = "done"      # VoiceFormatter → StdEnd


# ---------------------------------------------------------------------------
# Tools — stub implementations backed by a plain dict
#
# 06_smart_home_live.py subclasses these tools so they mutate a Pydantic
# HouseState instead, enabling real-time GUI visualisation.
# ---------------------------------------------------------------------------

_HOUSE_STATE: dict[str, dict] = {
    "kitchen": {"temperature": 20.0, "lights": False, "persons": 1, "stove": False},
    "bedroom": {"temperature": 18.5, "lights": True,  "persons": 0},
    "living":  {"temperature": 21.0, "lights": True,  "persons": 2},
}


class GetCurrentStatus(ToolBase):
    """Return temperature, light state and occupancy for a room."""

    name = "get_current_status"
    description = "Return current state (temperature, lights, persons) for the given room."

    @param_desc(room_id="Room name: 'kitchen', 'bedroom', or 'living'.")
    def execute(self, room_id: str) -> str:
        """Look up room data from the in-memory dict and format as a plain string."""
        room = _HOUSE_STATE.get(room_id)
        if room is None:
            return f"Unknown room '{room_id}'. Available: {', '.join(_HOUSE_STATE)}."
        return (
            f"Room '{room_id}': temperature={room['temperature']}°C, "
            f"lights={'on' if room['lights'] else 'off'}, "
            f"persons={room['persons']}"
            + (f", stove={'on' if room.get('stove') else 'off'}" if "stove" in room else "")
            + "."
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
        """Validate the room, then update the dict entry."""
        if room_id not in _HOUSE_STATE:
            return f"Unknown room '{room_id}'."
        temp = float(celsius)
        _HOUSE_STATE[room_id]["temperature"] = temp
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
        """Parse 'room.device', validate both parts, then flip the boolean in the dict."""
        parts = device_id.split(".", 1)
        if len(parts) != 2:
            return "Invalid device_id. Use format 'room.device', e.g. 'kitchen.lights'."
        room, device = parts
        if room not in _HOUSE_STATE:
            return f"Unknown room '{room}'."
        if device not in _HOUSE_STATE[room]:
            return f"Unknown device '{device}' in room '{room}'."
        _HOUSE_STATE[room][device] = state.lower() == "on"
        return f"'{device_id}' turned {state.lower()}."


# ---------------------------------------------------------------------------
# Vertices
#
# Each vertex is a Pydantic BaseModel (via LlmStateVertex/StateVertex).
# Fields declared as Annotated[T, Field(...)] are editable in the Inspector GUI.
# json_schema_extra={"x-textarea": True} renders a multi-line editor in Inspector.
# ---------------------------------------------------------------------------


class IntentParserVertex(LlmStateVertex):
    """Classify the user request into a category before passing it to DeviceWorker."""

    model: Annotated[str, Field(
        description="LLM model name (e.g. 'gpt-4o-mini'). Empty = use pool default.",
        json_schema_extra={"x-model-select": True},
    )] = "gpt-4o-mini"

    system_prompt: Annotated[str, Field(
        description="Instruction for classifying user intent.",
        json_schema_extra={"x-textarea": True},
    )] = (
        "Classify the user's smart home request. "
        "Respond with: 'CATEGORY: <LIGHTING|TEMPERATURE|APPLIANCE|STATUS_QUERY|UNKNOWN>'"
    )

    async def run(
        self, state: SmartHomeState, ctx: Context
    ) -> tuple[SmartHomeSignal, SmartHomePatch]:
        """Call LLM to parse intent; extract the CATEGORY: line from the response."""
        response = await ctx.llm_for_model(self.model).achat([
            {"role": "system", "content": self.system_prompt},
            *state.messages,
        ], temperature=self.temperature)
        intent = "UNKNOWN"
        for line in response.text.splitlines():
            if line.startswith("CATEGORY:"):
                intent = line.split(":", 1)[1].strip()
                break
        return SmartHomeSignal.parsed, SmartHomePatch(intent=intent)


class DeviceWorkerVertex(LlmStateVertex):
    """Check room state with tools, then propose device actions.

    On retry the prior rejection_reason is appended to the system prompt so the
    LLM can correct its plan.
    """

    model: Annotated[str, Field(
        description="LLM model name (e.g. 'gpt-4o-mini'). Empty = use pool default.",
        json_schema_extra={"x-model-select": True},
    )] = "gpt-4o-mini"

    tools:      Annotated[str, Field(description="Tool registry key from Context.")] = "default"
    max_rounds: Annotated[int, Field(ge=1, le=10, description="Max tool-calling rounds.")] = 4
    system_prompt: Annotated[str, Field(
        description="Instruction for proposing device actions using tools.",
        json_schema_extra={"x-textarea": True},
    )] = (
        "You control a smart home. Use tools to check the current room state, "
        "then propose specific device actions clearly listed line by line."
    )

    async def run(
        self, state: SmartHomeState, ctx: Context
    ) -> tuple[SmartHomeSignal, SmartHomePatch]:
        """Run LLM+tool loop; append correction hint when retrying after rejection."""
        correction = (
            f"\n\nYour previous plan was REJECTED: {state.rejection_reason}\n"
            "Please revise the plan to fix the issue."
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
    """Validate the action plan; approve or reject with a reason.

    Forces approval after max_revisions to prevent an infinite loop.
    """

    model: Annotated[str, Field(
        description="LLM model name (e.g. 'gpt-4o-mini'). Empty = use pool default.",
        json_schema_extra={"x-model-select": True},
    )] = "gemini-3.5-flash"

    max_revisions: Annotated[int, Field(ge=1, le=3,
                       description="Max Worker→Judge loops before forcing approval.")] = 2
    system_prompt: Annotated[str, Field(
        description="Safety rules for validating the proposed action plan.",
        json_schema_extra={"x-textarea": True},
    )] = """\
You are a safety officer for a smart home system. Review the proposed action plan.

SAFETY RULES:
1. Temperature must stay between 10°C and 28°C in any room.
2. Never turn on a stove or oven when no person is detected in that room.
3. Never set temperature below 15°C in a room where a person is present.
4. Security cameras cannot be disabled remotely.

If SAFE:   respond exactly with "APPROVED: <one-line confirmation>"
If UNSAFE: respond exactly with "REJECTED: <specific rule violated and how to fix it>"
"""

    async def run(
        self, state: SmartHomeState, ctx: Context
    ) -> tuple[SmartHomeSignal, SmartHomePatch]:
        """Ask the quality LLM to review the plan; parse APPROVED/REJECTED from the reply."""
        if state.revisions >= self.max_revisions:
            ctx.logger.warning("max_revisions=%d reached; forcing approval", self.max_revisions)
            return SmartHomeSignal.approved, SmartHomePatch(revisions=state.revisions + 1)

        response = await ctx.llm_for_model(self.model).achat([
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Action plan to review:\n{state.action_plan}"},
        ], temperature=self.temperature)
        text = response.text.strip()

        if text.upper().startswith("APPROVED"):
            return SmartHomeSignal.approved, SmartHomePatch(revisions=state.revisions + 1)

        reason = text[text.index(":") + 1:].strip() if ":" in text else text
        return SmartHomeSignal.rejected, SmartHomePatch(
            rejection_reason=reason, revisions=state.revisions + 1
        )


class VoiceFormatterVertex(LlmStateVertex):
    """Convert the approved action plan into a short, natural TTS-ready reply."""

    model: Annotated[str, Field(
        description="LLM model name (e.g. 'gpt-4o-mini'). Empty = use pool default.",
        json_schema_extra={"x-model-select": True},
    )] = "gpt-4o-mini"

    system_prompt: Annotated[str, Field(
        description="Instruction for formatting the plan as a voice reply.",
        json_schema_extra={"x-textarea": True},
    )] = (
        "Turn the following smart home action plan into a short, natural voice reply "
        "for a smart speaker. Rules: no markdown, no bullet points, "
        "max 2 sentences, warm and friendly tone, confirm what was done."
    )

    async def run(
        self, state: SmartHomeState, ctx: Context
    ) -> tuple[SmartHomeSignal, SmartHomePatch]:
        """Format approved plan into final_response."""
        response = await ctx.llm_for_model(self.model).achat([
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": state.action_plan},
        ], temperature=self.temperature)
        return SmartHomeSignal.done, SmartHomePatch(final_response=response.text.strip())


# ---------------------------------------------------------------------------
# Application wiring
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
