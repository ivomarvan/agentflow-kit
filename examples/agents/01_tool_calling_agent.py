"""Minimal ReAct tool-calling agent using agentflow.statemachine.

Demonstrates the core ReAct loop (Reason + Act) with two tools:
  - Calculator  — safe math evaluator
  - GetWeather  — stub weather lookup by city

The agent decides which tool to call, reads the result, and iterates until
it can produce a final answer or hits the step limit.

Run:
    uv run python examples/agents/01_tool_calling_agent.py -h
    uv run python examples/agents/01_tool_calling_agent.py run
    uv run python examples/agents/01_tool_calling_agent.py gui
    uv run python examples/agents/01_tool_calling_agent.py graph --browser
"""

import json
import operator
from dataclasses import dataclass
from enum import auto
from typing import Annotated, Any, cast

from pydantic import Field

from agentflow import AgentApp
from agentflow.llm.cache import LlmFileCache
from agentflow.llm.ChatResponse import ToolCallInfo
from agentflow.llm.LlmPool import LlmPool
from agentflow.logging_config import setup_pretty_logging
from agentflow.statemachine import (
    Context,
    EnumSignal,
    StateGraph,
    StateGraphRunner,
    LlmStateVertex,
    StateVertex,
    StdEnd,
    StdSignal,
    Transition,
)
from agentflow.statemachine.hooks import LoggingHooks
from agentflow.tools.Tool import ToolBase, param_desc
from agentflow.tools.ToolRegistry import ToolRegistry

_DEFAULT_QUESTION = "What's the weather in Prague, and what is 19 times 23?"

_SYSTEM_PROMPT = (
    "You are a helpful assistant. "
    "Always use the available tools to obtain reliable facts and perform calculations. "
    "Never guess weather or math results — call the appropriate tool."
)

_WEATHER_DB: dict[str, str] = {
    "Prague": "12°C, cloudy",
    "Tokyo": "24°C, sunny",
    "New York": "18°C, windy",
}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


class Calculator(ToolBase):
    """Evaluate a simple arithmetic expression safely."""

    @param_desc(expression="Arithmetic expression using digits and +-*/() only, e.g. '19 * 23'")
    def execute(self, expression: str) -> str:
        """Evaluate the expression; reject any non-arithmetic input.

        Args:
            expression: Math expression string.

        Returns:
            String with the numeric result, or an error message.
        """
        allowed = set("0123456789+-*/() .")
        if not set(expression) <= allowed:
            return f"GUARDRAIL: disallowed characters in '{expression}'"
        try:
            return str(eval(expression))  # noqa: S307
        except Exception as exc:  # noqa: BLE001
            return f"ERROR: {exc}"


class GetWeather(ToolBase):
    """Return current weather for a known city."""

    @param_desc(city="City name, e.g. 'Prague', 'Tokyo', 'New York'")
    def execute(self, city: str) -> str:
        """Look up stub weather data for the requested city.

        Args:
            city: City name.

        Returns:
            Weather description string, or a not-found message.
        """
        return _WEATHER_DB.get(city, f"No weather data available for '{city}'.")


# ---------------------------------------------------------------------------
# State / Patch / Signal
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReactState:
    """Immutable agent state for a single ReAct run."""

    messages: Annotated[tuple[dict[str, Any], ...], operator.add] = ()
    last_tool_calls: tuple[ToolCallInfo, ...] = ()
    final_answer: str = ""
    step: int = 0


@dataclass
class ReactPatch:
    """Mutable patch applied to ReactState after each super-step."""

    messages: tuple[dict[str, Any], ...] | None = None
    last_tool_calls: tuple[ToolCallInfo, ...] | None = None
    final_answer: str | None = None
    step: int | None = None


class ReactSignal(EnumSignal):
    """Routing signals for the ReAct loop."""

    tool_call = auto()
    final_answer = auto()
    max_steps = auto()


# ---------------------------------------------------------------------------
# Vertices
# ---------------------------------------------------------------------------

_MAX_STEPS = 7


class LlmCallVertex(LlmStateVertex):
    """Calls the LLM and decides whether to invoke a tool or emit a final answer."""

    model: Annotated[str, Field(
        description="LLM model name (e.g. 'gpt-4o-mini'). Empty = use pool default.",
        json_schema_extra={"x-model-select": True},
    )] = "gpt-4.1-mini"

    tools: Annotated[str, Field(description="Tool registry key from Context.")] = "default"

    async def run(self, state: ReactState, ctx: Context) -> tuple[ReactSignal, ReactPatch]:
        """Run one LLM turn and route based on the response.

        Args:
            state: Current ReactState snapshot.
            ctx: Shared context with LLM connector and tool registry.

        Returns:
            (ReactSignal.tool_call, patch) when the LLM requests a tool;
            (ReactSignal.final_answer, patch) when the LLM returns plain text;
            (ReactSignal.max_steps, patch) when the step limit is reached.
        """
        if state.step >= _MAX_STEPS:
            return ReactSignal.max_steps, ReactPatch(
                final_answer=f"AGENT ERROR: exceeded {_MAX_STEPS} steps"
            )
        response = await ctx.llm_for_model(self.model).achat(
            list(state.messages),
            tools=ctx.get_tools(self.tools).schemas(),
            temperature=self.temperature,
        )
        assistant_msg = response.to_message_dict()
        if response.has_tool_calls:
            return ReactSignal.tool_call, ReactPatch(
                messages=(assistant_msg,),
                last_tool_calls=tuple(response.tool_calls or []),
                step=state.step + 1,
            )
        return ReactSignal.final_answer, ReactPatch(
            messages=(assistant_msg,),
            final_answer=response.text,
            step=state.step + 1,
        )


class ToolExecutionVertex(StateVertex):
    """Executes all tool calls requested by the LLM in the previous step."""

    tools: Annotated[str, Field(description="Tool registry key from Context.")] = "default"

    async def run(self, state: ReactState, ctx: Context) -> tuple[Any, ReactPatch]:
        """Execute each pending tool call and collect results.

        Args:
            state: Current ReactState snapshot.
            ctx: Shared context; logger used for structured output.

        Returns:
            (StdSignal.ok, patch) with tool result messages appended.
        """
        from agentflow.events import ToolCallEvent

        registry = ctx.get_tools(self.tools)
        tool_msgs: list[dict[str, Any]] = []
        for tc in state.last_tool_calls:
            try:
                args = json.loads(tc.arguments or "{}")
                args_fmt = ", ".join(f"{k}={v!r}" for k, v in args.items())
            except (json.JSONDecodeError, AttributeError):
                args = {}
                args_fmt = tc.arguments or ""
            ctx.logger.info("tool_call: %s(%s)", tc.name, args_fmt)
            tool = registry.get(tc.name)
            if tool is None:
                result = f"ERROR: unknown tool '{tc.name}'"
            else:
                try:
                    result = str(tool.execute(**args))
                except Exception as exc:  # noqa: BLE001
                    result = f"ERROR: {exc}"
            ctx.logger.info("tool_result: %s  →  %.120s", tc.name, result)
            await ctx.event_bus.emit(ToolCallEvent(
                tool_name=tc.name,
                step=ctx.step,
                inputs=args,
                output=result,
            ))
            tool_msgs.append(
                {"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": result}
            )
        return StdSignal.ok, ReactPatch(messages=tuple(tool_msgs), last_tool_calls=())


# ---------------------------------------------------------------------------
# Wiring — declarative AgentApp
# ---------------------------------------------------------------------------

_registry = ToolRegistry([Calculator(), GetWeather()])
_llm_vertex = LlmCallVertex()
_tool_vertex = ToolExecutionVertex()

_app = AgentApp(
    doc=__doc__,
    system_prompt=_SYSTEM_PROMPT,
    default_question=_DEFAULT_QUESTION,
    sample_prompts=[
        "What's the weather in Tokyo and New York?",
        "Calculate (17 + 8) * 4 and tell me the weather in Prague.",
        "Is Prague warmer than New York? Also compute 100 / 4.",
    ],
    context=Context(
        pool=LlmPool(cache=LlmFileCache(__file__)),
        tool_registries={"default": _registry},
    ),
    state_graph=StateGraph(
        start=_llm_vertex,
        transitions=[
            Transition(_llm_vertex, ReactSignal.tool_call, _tool_vertex),
            Transition(_tool_vertex, StdSignal.ok, _llm_vertex),
            Transition(_llm_vertex, ReactSignal.final_answer, StdEnd),
            Transition(_llm_vertex, ReactSignal.max_steps, StdEnd),
        ],
    ),
)

if __name__ == "__main__":
    _app.cli(__doc__, name=__name__)
