"""# Smart Home Voice Dispatcher

Worker/Judge pattern with safety validation.

## Assignment

A user controls their smart home via a voice transcript. The pipeline:

1. **IntentParser** — classifies the request
2. **DeviceWorker** — proposes device actions with tools:
   - `get_current_status` — room temperature, lights, occupancy
   - `set_temperature` — target temperature in °C
   - `toggle_device` — lights or stove on/off
3. **SafetyJudge** — validates the plan (temperature limits, occupancy checks, …)
4. **VoiceFormatter** — produces a concise TTS-ready reply

If the Judge rejects an unsafe plan, the Worker revises and resubmits (max 2 retries).

## Demonstrates

- Worker/Judge review loop with tool-calling LLMs
- `StateVertex` as Pydantic BaseModel
- Two LLM connector tiers (economy vs quality)
- Typed state without `cast()`, `ctx.stats` after run
- Declarative `AgentApp` with `run` / `graph` / `gui`

## Run

```bash
uv run python examples/agents/06_smart_home_assistant.py run
uv run python examples/agents/06_smart_home_assistant.py graph --browser
uv run python examples/agents/06_smart_home_assistant.py -h
```
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated

from pydantic import Field

from agentflow import AgentApp
from agentflow.llm.cache import LlmFileCache
from agentflow.llm.connectors import LlmConnector
from agentflow.statemachine import (
    Context,
    Signal,
    StateGraph,
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

_SAFETY_RULES = """\
You are a safety officer for a smart home system. Review the proposed action plan.

SAFETY RULES:
1. Temperature must stay between 10°C and 28°C in any room.
2. Never turn on a stove or oven when no person is detected in that room.
3. Never set temperature below 15°C in a room where a person is present.
4. Security cameras cannot be disabled remotely.

If SAFE:   respond exactly with "APPROVED: <one-line confirmation>"
If UNSAFE: respond exactly with "REJECTED: <specific rule violated and how to fix it>"
"""

# ---------------------------------------------------------------------------
# Application state, patch and signals
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SmartHomeState:
    """Immutable state snapshot passed between vertices.

    Attributes:
        messages:         Conversation history (user + assistant turns).
        intent:           Parsed intent category (LIGHTING, TEMPERATURE, …).
        action_plan:      DeviceWorker's proposed device actions.
        rejection_reason: SafetyJudge's latest rejection reason (empty if none).
        revisions:        Number of completed Worker→Judge loops so far.
        final_response:   TTS-optimized response from VoiceFormatterVertex.
    """

    messages:         Annotated[tuple[dict, ...], operator.add] = field(default_factory=tuple)
    intent:           str = ""
    action_plan:      str = ""
    rejection_reason: str = ""
    revisions:        int = 0
    final_response:   str = ""


@dataclass(frozen=True)
class SmartHomePatch:
    """Partial update emitted by each vertex; runner merges it into SmartHomeState.

    Fields default to UNSET so apply_patches() updates only what each vertex sets.
    Use an empty string explicitly when a field must be cleared (e.g. rejection_reason).
    """

    messages:         tuple[dict, ...] | object = UNSET
    intent:           str | object = UNSET
    action_plan:      str | object = UNSET
    rejection_reason: str | object = UNSET
    revisions:        int | object = UNSET
    final_response:   str | object = UNSET


class SmartHomeSignal(Signal):
    """Routing decisions used in the smart home workflow."""

    parsed   = "parsed"    # IntentParserVertex done   → DeviceWorkerVertex
    proposed = "proposed"  # DeviceWorkerVertex done   → SafetyJudgeVertex
    approved = "approved"  # SafetyJudgeVertex ok      → VoiceFormatterVertex
    rejected = "rejected"  # SafetyJudgeVertex unsafe  → DeviceWorkerVertex (loop)
    done     = "done"      # VoiceFormatterVertex done → StdEnd


# ---------------------------------------------------------------------------
# Tools (stub implementations — replace with real smart home API calls)
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
# ---------------------------------------------------------------------------

# NOTE: StateVertex inherits from Pydantic BaseModel (wish API).
#   Class-level Annotated fields auto-generate __init__ + validation + JSON Schema.
#   No __init__ body, no self.x = x assignments needed.


class IntentParserVertex(StateVertex):
    """Parse and classify the user's voice command before passing it to the Worker."""

    connector: Annotated[str, Field(description="LLM connector key from Context.")] = "economy"

    async def run(
        self, state: SmartHomeState, ctx: Context
    ) -> tuple[SmartHomeSignal, SmartHomePatch]:
        """Classify intent into a category used by downstream vertices.

        Args:
            state: Current SmartHomeState with user messages.
            ctx:   ctx.llm() provides the economy LLM connector.

        Returns:
            (SmartHomeSignal.parsed, patch) with intent category populated.
        """
        response = await ctx.llm(self.connector).achat([
            {"role": "system", "content": (
                "Classify the user's smart home request. "
                "Respond with: 'CATEGORY: <LIGHTING|TEMPERATURE|APPLIANCE|STATUS_QUERY|UNKNOWN>'"
            )},
            *state.messages,
        ])
        intent = "UNKNOWN"
        for line in response.text.splitlines():
            if line.startswith("CATEGORY:"):
                intent = line.split(":", 1)[1].strip()
                break
        return SmartHomeSignal.parsed, SmartHomePatch(intent=intent)


class DeviceWorkerVertex(StateVertex):
    """Propose device actions using a cheap LLM with tools (tool loop hidden in connector)."""

    connector:  Annotated[str, Field(description="LLM connector key from Context.")] = "economy"
    tools:      Annotated[str, Field(description="Tool registry key from Context.")] = "default"
    max_rounds: Annotated[int, Field(ge=1, le=10, description="Max tool-calling rounds.")] = 4

    async def run(
        self, state: SmartHomeState, ctx: Context
    ) -> tuple[SmartHomeSignal, SmartHomePatch]:
        """Check current room state via tools, then propose specific actions.

        Args:
            state: Contains messages, intent, and optional prior rejection_reason.
            ctx:   ctx.llm().achat_with_tools() runs the hidden LLM+tool loop.

        Returns:
            (SmartHomeSignal.proposed, patch) with action_plan set.
        """
        correction = (
            f"\n\nYour previous plan was REJECTED for this reason: {state.rejection_reason}\n"
            "Please revise the plan to fix the issue."
            if state.rejection_reason else ""
        )
        response = await ctx.llm(self.connector).achat_with_tools(
            messages=[
                {"role": "system", "content": (
                    "You control a smart home. Use tools to check the current room state, "
                    "then propose specific device actions clearly listed line by line."
                    + correction
                )},
                *state.messages,
            ],
            registry=ctx.get_tools(self.tools),
            max_rounds=self.max_rounds,
        )
        return SmartHomeSignal.proposed, SmartHomePatch(
            action_plan=response.text, rejection_reason=""
        )


class SafetyJudgeVertex(StateVertex):
    """Validate the action plan against safety rules; approve or reject with reason."""

    connector:     Annotated[str, Field(description="LLM connector key from Context.")] = "quality"
    max_revisions: Annotated[int, Field(ge=1, le=3,
                       description="Max Worker→Judge retry loops before forcing approval.")] = 2

    async def run(
        self, state: SmartHomeState, ctx: Context
    ) -> tuple[SmartHomeSignal, SmartHomePatch]:
        """Review the action plan; return approved or rejected signal.

        Args:
            state: action_plan to review, revisions count for loop guard.
            ctx:   ctx.llm() provides the expensive quality LLM connector.

        Returns:
            (SmartHomeSignal.approved, patch) when plan is safe.
            (SmartHomeSignal.rejected, patch) with rejection_reason when unsafe.
        """
        if state.revisions >= self.max_revisions:
            ctx.logger.warning(
                "max_revisions=%d reached; forcing approval", self.max_revisions
            )
            return SmartHomeSignal.approved, SmartHomePatch(revisions=state.revisions + 1)

        response = await ctx.llm(self.connector).achat([
            {"role": "system", "content": _SAFETY_RULES},
            {"role": "user", "content": f"Action plan to review:\n{state.action_plan}"},
        ])
        text = response.text.strip()
        upper = text.upper()

        if upper.startswith("APPROVED"):
            return SmartHomeSignal.approved, SmartHomePatch(revisions=state.revisions + 1)

        reason = text[text.index(":") + 1:].strip() if ":" in text else text
        return SmartHomeSignal.rejected, SmartHomePatch(
            rejection_reason=reason, revisions=state.revisions + 1
        )


class VoiceFormatterVertex(StateVertex):
    """Convert the approved action plan into a natural, TTS-optimised voice response."""

    connector: Annotated[str, Field(description="LLM connector key from Context.")] = "economy"

    async def run(
        self, state: SmartHomeState, ctx: Context
    ) -> tuple[SmartHomeSignal, SmartHomePatch]:
        """Format the approved plan into a concise, friendly voice reply.

        Args:
            state: approved action_plan to summarise.
            ctx:   ctx.llm() provides the economy LLM connector.

        Returns:
            (SmartHomeSignal.done, patch) with TTS-ready final_response.
        """
        response = await ctx.llm(self.connector).achat([
            {"role": "system", "content": (
                "Turn the following smart home action plan into a short, natural voice reply "
                "for a smart speaker. Rules: no markdown, no bullet points, "
                "max 2 sentences, warm and friendly tone, confirm what was done."
            )},
            {"role": "user", "content": state.action_plan},
        ])
        return SmartHomeSignal.done, SmartHomePatch(final_response=response.text.strip())


# ---------------------------------------------------------------------------
# Wiring — fully declarative AgentApp
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
            "Set the bedroom temperature to 4 degrees.",   # should be rejected by SafetyJudge
            "Turn on the kitchen stove.",                  # dangerous if no person detected
        ],
        initial_state_factory=lambda q: SmartHomeState(
            messages=(
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": q},
            ),
        ),
        context=Context(
            llm_connectors={
                # economy: used by IntentParser, DeviceWorker, VoiceFormatter
                "economy": LlmConnector(model="gpt-4o-mini", cache=LlmFileCache(__file__)),
                # quality: used by SafetyJudge — higher reasoning needed for safety checks
                "quality": LlmConnector(model="gemini-3.5-flash",      cache=LlmFileCache(__file__)),
            },
            tool_registries={
                "default": ToolRegistry([
                    GetCurrentStatus(), SetTemperature(), ToggleDevice(),
                ]),
            },
        ),
        state_graph=StateGraph(
            start=IntentParserVertex,
            initialized_vertexes=[
                SafetyJudgeVertex(max_revisions=2),   # quality LLM, 2 retry loops max
                DeviceWorkerVertex(max_rounds=4),      # economy LLM, 4 tool-calling rounds
                # IntentParserVertex and VoiceFormatterVertex use all-default params
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
