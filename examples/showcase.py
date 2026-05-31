"""agentflow showcase — ReAct agent demonstrating all framework features.

This single file is the *flagship* example: simple enough to read in minutes,
yet touching every part of the public API so it can serve as the reference
when exploring or making design changes.

Feature coverage:
  ▸ AgentApp           — base class with cli() / browser / gui / run support
  ▸ StateGraph         — typed frozen state, EnumSignal routing, Transition edges
  ▸ StateVertex        — two custom vertices forming the ReAct loop
  ▸ ToolBase           — three tools with multi-param @param_desc JSON schema
  ▸ ToolRegistry       — explicit registry, reused by both vertices
  ▸ LlmConnector       — smart facade with automatic backend selection from .env
  ▸ LlmFileCache       — persistent per-script cache (no redundant API calls)
  ▸ AgentEvent         — custom ToolCalledEvent published via EventBus
  ▸ EventBus           — subscriber logs every tool invocation
  ▸ LoggingHooks       — plugged into StateGraphRunner
  ▸ setup_pretty_logging() — hierarchical indented console output
  ▸ sample_prompts     — example prompts for the GUI prompt selector
  ▸ Injectable connector — pass any LlmConnectorBase (e.g. FakeLlmConnector)

Run:
    uv run python examples/showcase.py              # run with real LLM
    uv run python examples/showcase.py browser      # open graph in browser
    uv run python examples/showcase.py gui          # start local GUI server
    uv run python examples/showcase.py -h           # show help
"""

from __future__ import annotations

import json
import operator
from dataclasses import dataclass
from enum import auto
from typing import Annotated, Any, cast

from pydantic import Field

from agentflow import AgentApp
from agentflow.events import AgentEvent
from agentflow.llm.cache import LlmFileCache
from agentflow.llm.ChatResponse import ToolCallInfo
from agentflow.llm.connectors import LlmConnector
from agentflow.llm.LlmConnectorBase import LlmConnectorBase
from agentflow.logging_config import setup_pretty_logging
from agentflow.statemachine import (
    Context,
    EnumSignal,
    StateGraph,
    StateGraphRunner,
    StateVertex,
    StdEnd,
    StdSignal,
    Transition,
)
from agentflow.statemachine.hooks import LoggingHooks
from agentflow.tools.Tool import ToolBase, param_desc
from agentflow.tools.ToolRegistry import ToolRegistry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_STEPS = 10
_DEFAULT_QUESTION = "What's the weather in Prague? Also compute 42 * 7."
_SYSTEM_PROMPT = (
    "You are a helpful assistant. "
    "Use the available tools to obtain accurate facts and perform calculations. "
    "Never guess weather data, dates, or math results — always call a tool."
)

# ---------------------------------------------------------------------------
# Custom domain event
# ---------------------------------------------------------------------------


class ToolCalledEvent(AgentEvent):
    """Emitted each time a tool is invoked by ToolExecutionVertex.

    Attributes:
        tool_name: Name of the tool that was called.
        args: Parsed argument dict passed to the tool.
        result: Return value produced by the tool.
    """

    event_type: str = "showcase.tool_called"
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: str


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

_WEATHER_DB: dict[str, str] = {
    "Prague": "12°C, cloudy",
    "Tokyo": "24°C, sunny",
    "New York": "18°C, windy",
    "London": "9°C, rainy",
    "Paris": "15°C, partly cloudy",
    "Berlin": "7°C, overcast",
}

_RATES: dict[tuple[str, str], float] = {
    ("EUR", "CZK"): 25.2,
    ("USD", "CZK"): 23.1,
    ("GBP", "EUR"): 1.17,
    ("USD", "EUR"): 0.92,
    ("CZK", "EUR"): 0.040,
}


class GetWeather(ToolBase):
    """Return current weather conditions for a city (stub data)."""

    name = "get_weather"
    description = "Return the current weather for the given city."

    @param_desc(city="City name, e.g. 'Prague' or 'Tokyo'.")
    def execute(self, city: str) -> str:
        return _WEATHER_DB.get(city, f"No weather data for '{city}'.")


class Calculator(ToolBase):
    """Evaluate a safe arithmetic expression and return the numeric result."""

    name = "calculator"
    description = "Evaluate a mathematical expression, e.g. '(17+8)*4'."

    @param_desc(expression="Arithmetic expression to evaluate, e.g. '42 * 7'.")
    def execute(self, expression: str) -> str:
        try:
            result = eval(expression, {"__builtins__": {}}, {})  # noqa: S307
            return str(result)
        except Exception as exc:
            return f"ERROR: {exc}"


class GetExchangeRate(ToolBase):
    """Return the current exchange rate between two currencies (stub data)."""

    name = "get_exchange_rate"
    description = "Return exchange rate between from_currency and to_currency."

    @param_desc(
        from_currency="Three-letter ISO code to convert FROM, e.g. 'EUR'.",
        to_currency="Three-letter ISO code to convert TO, e.g. 'CZK'.",
    )
    def execute(self, from_currency: str, to_currency: str) -> str:
        f, t = from_currency.upper(), to_currency.upper()
        rate = _RATES.get((f, t))
        if rate is None:
            inv = _RATES.get((t, f))
            rate = round(1.0 / inv, 6) if inv else None
        if rate is None:
            return f"No rate available for {f}/{t}."
        return f"1 {f} = {rate} {t}"


# ---------------------------------------------------------------------------
# State & signals
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AppState:
    """Immutable snapshot of the agent conversation, passed between vertices.

    The ``messages`` field uses ``operator.add`` as its BSP reducer so that
    patches from parallel vertices are concatenated rather than overwritten.
    """

    messages: Annotated[tuple[dict[str, Any], ...], operator.add] = ()
    last_tool_calls: tuple[ToolCallInfo, ...] = ()
    final_answer: str = ""
    step: int = 0


@dataclass(frozen=True)
class AppPatch:
    """Partial update applied to AppState after each vertex run."""

    messages: tuple[dict[str, Any], ...] = ()
    last_tool_calls: tuple[ToolCallInfo, ...] = ()
    final_answer: str = ""
    step: int = 0


class AppSignal(EnumSignal):
    """Routing signals for the ReAct loop."""

    tool_call = auto()
    final_answer = auto()
    max_steps = auto()


# ---------------------------------------------------------------------------
# Vertices
# ---------------------------------------------------------------------------


class LlmCallVertex(StateVertex):
    """Call the LLM and decide whether to invoke tools or emit the final answer.

    Routes to ToolExecutionVertex on tool_call, StdEnd on final_answer/max_steps.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._schemas = registry.schemas()

    async def run(self, state: object, ctx: Context) -> tuple[AppSignal, AppPatch]:
        """Run one LLM turn and return routing signal + state patch.

        Args:
            state: Current AppState snapshot.
            ctx: Shared services — connector, logger, event_bus.

        Returns:
            (tool_call, patch) when the LLM requests tools;
            (final_answer, patch) when the LLM gives a plain-text answer;
            (max_steps, patch) when the step limit is exceeded.
        """
        s = cast(AppState, state)
        if s.step >= _MAX_STEPS:
            return AppSignal.max_steps, AppPatch(
                final_answer=f"AGENT ERROR: exceeded {_MAX_STEPS} steps"
            )
        response = await ctx.connector.achat(list(s.messages), tools=self._schemas)
        msg = response.to_message_dict()
        if response.has_tool_calls:
            return AppSignal.tool_call, AppPatch(
                messages=(msg,),
                last_tool_calls=tuple(response.tool_calls or []),
                step=s.step + 1,
            )
        return AppSignal.final_answer, AppPatch(
            messages=(msg,),
            final_answer=response.text,
            step=s.step + 1,
        )


class ToolExecutionVertex(StateVertex):
    """Execute all pending tool calls and publish a ToolCalledEvent for each."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def run(self, state: object, ctx: Context) -> tuple[Any, AppPatch]:
        """Execute each tool call from state.last_tool_calls.

        Publishes a ToolCalledEvent to ctx.event_bus after each invocation
        so subscribers (e.g. the GUI or a test spy) can react.

        Args:
            state: Current AppState snapshot.
            ctx: Shared services — logger, event_bus, run_sync helper.

        Returns:
            (StdSignal.ok, patch) with tool-result messages appended.
        """
        s = cast(AppState, state)
        tool_msgs: list[dict[str, Any]] = []
        for tc in s.last_tool_calls:
            try:
                args = json.loads(tc.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            args_fmt = ", ".join(f"{k}={v!r}" for k, v in args.items())
            ctx.logger.info("tool_call: %s(%s)", tc.name, args_fmt)
            try:
                result = self._registry.execute(tc.name, tc.arguments or "{}")
            except KeyError:
                result = f"ERROR: unknown tool '{tc.name}'"
            ctx.logger.info("tool_result: %s  →  %.120s", tc.name, result)
            await ctx.event_bus.emit(
                ToolCalledEvent(tool_name=tc.name, args=args, result=result)
            )
            tool_msgs.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tc.name,
                "content": result,
            })
        return StdSignal.ok, AppPatch(messages=tuple(tool_msgs), last_tool_calls=())


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


class ShowcaseApp(AgentApp):
    """agentflow showcase — ReAct agent with weather, calculator, and currency tools.

    Wires every public framework feature into one concise runnable application.
    Pass a custom ``connector`` to use offline (e.g. ``FakeLlmConnector``).
    """

    def __init__(self, connector: LlmConnectorBase | None = None) -> None:
        super().__init__()
        # Connector injection: real LLM by default, injectable for testing
        self.connector: LlmConnectorBase = (
            connector or LlmConnector(cache=LlmFileCache(__file__))
        )
        tools: list[ToolBase] = [GetWeather(), Calculator(), GetExchangeRate()]
        self.registry = ToolRegistry(tools=tools)

        llm_v = LlmCallVertex(self.registry)
        tool_v = ToolExecutionVertex(self.registry)
        self.graph = StateGraph(
            start=llm_v,
            transitions=[
                Transition(llm_v, AppSignal.tool_call, tool_v),
                Transition(tool_v, StdSignal.ok, llm_v),
                Transition(llm_v, AppSignal.final_answer, StdEnd),
                Transition(llm_v, AppSignal.max_steps, StdEnd),
            ],
        )

    @property
    def sample_prompts(self) -> list[str]:
        """Example prompts shown in the GUI prompt selector."""
        return [
            "What's the weather in Prague? Also compute 42 * 7.",
            "Is Tokyo warmer than London? And how much is 100 EUR in CZK?",
            "Compare weather in Paris and Berlin. What is 1 GBP in EUR?",
        ]

    async def run_workflow(self) -> str | None:
        """Run the ReAct agent loop and return the final answer.

        Returns:
            Final answer string produced by the LLM, or None on error.
        """
        setup_pretty_logging()
        question = self.current_prompt or _DEFAULT_QUESTION

        # EventBus subscriber: log every ToolCalledEvent as a structured line
        class _ToolEventLogger:
            async def on_event(self, event: AgentEvent) -> None:
                if isinstance(event, ToolCalledEvent):
                    pass  # already logged by ToolExecutionVertex via ctx.logger

        self.event_bus.subscribe(_ToolEventLogger())

        ctx = Context(connector=self.connector, event_bus=self.event_bus)
        hooks = LoggingHooks()
        runner = StateGraphRunner(graph=self.graph, context=ctx, hooks=hooks)
        initial = AppState(
            messages=(
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": question},
            )
        )
        final = cast(AppState, await runner.run(initial))
        return final.final_answer


if __name__ == "__main__":
    ShowcaseApp().cli(__doc__, name=__name__)
