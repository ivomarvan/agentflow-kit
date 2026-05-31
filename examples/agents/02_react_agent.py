"""Full ReAct agent with 4 tools: policy search, calculator, date helpers.

Demonstrates a multi-tool ReAct loop where the agent must chain several tool
calls to answer questions involving company policies, arithmetic, and dates.

Tools:
  - SearchPolicy    — in-memory lookup over company policy texts
  - Calculator      — safe arithmetic evaluator
  - GetCurrentDate  — returns today's date in a requested format
  - AddDaysToDate   — adds N days to a given date

Run:
    uv run python examples/agents/02_react_agent.py
    uv run python examples/agents/02_react_agent.py gui
    uv run python examples/agents/02_react_agent.py browser
"""

import json
import operator
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import auto
from typing import Annotated, Any, cast

from dateutil import parser as dateutil_parser
from pydantic import Field

from agentflow import AgentApp
from agentflow.llm.cache import LlmFileCache
from agentflow.llm.ChatResponse import ToolCallInfo
from agentflow.llm.connectors import LlmConnector
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

_DEFAULT_QUESTION = (
    "I haven't had vacation yet. If I take it all in three days from today, when will it end?"
)

_POLICIES: dict[str, str] = {
    "vacation": "Employees are entitled to 25 days of paid vacation per year.",
    "sick days": "Employees may take up to 3 sick days per year without a doctor's note.",
    "remote work": "Remote work is allowed up to 4 days a week.",
    "parking": "Parking at the HQ is free for all employees.",
}

_SYSTEM_PROMPT = (
    "You are a strict company assistant. "
    "To answer any question about policies, math, or dates you MUST always use the appropriate tool. "  # noqa: E501
    "Never assume facts — call search_policy for policy questions, calculator for arithmetic, "
    "get_current_date for today's date, and add_days_to_date for date arithmetic. "
    "Answer concisely in English."
)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


class SearchPolicy(ToolBase):
    """Search the company's internal policy database."""

    @param_desc(query="What you want to look up, e.g. 'vacation days'")
    def execute(self, query: str) -> str:
        """Find policy entries whose key overlaps with the query.

        Args:
            query: Natural-language search string.

        Returns:
            Matching policy texts joined by newlines, or a not-found message.
        """
        q = query.lower()
        hits = [
            text for key, text in _POLICIES.items() if key in q or any(w in q for w in key.split())
        ]
        return "\n".join(hits) if hits else "No relevant policy found."


class Calculator(ToolBase):
    """Evaluate a simple arithmetic expression safely."""

    @param_desc(expression="Arithmetic expression using digits and +-*/() only, e.g. '25 * 2'")
    def execute(self, expression: str) -> str:
        """Evaluate the expression; reject any non-arithmetic input.

        Args:
            expression: Math expression string.

        Returns:
            Numeric result as string, or an error message.
        """
        allowed = set("0123456789+-*/() .")
        if not set(expression) <= allowed:
            return f"GUARDRAIL: disallowed characters in '{expression}'"
        try:
            return str(eval(expression))  # noqa: S307
        except Exception as exc:  # noqa: BLE001
            return f"ERROR: {exc}"


class GetCurrentDate(ToolBase):
    """Return today's date in a requested format."""

    @param_desc(format="Date format: 'YYYY-MM-DD', 'DD-MM-YYYY', or 'MM-DD-YYYY'")
    def execute(self, format: str = "YYYY-MM-DD") -> str:  # noqa: A002
        """Format today's date.

        Args:
            format: One of YYYY-MM-DD, DD-MM-YYYY, MM-DD-YYYY.

        Returns:
            Formatted date string or an error message for unknown formats.
        """
        _fmt_map = {"YYYY-MM-DD": "%Y-%m-%d", "DD-MM-YYYY": "%d-%m-%Y", "MM-DD-YYYY": "%m-%d-%Y"}
        if format not in _fmt_map:
            return f"ERROR: unknown format '{format}'. Use YYYY-MM-DD, DD-MM-YYYY, or MM-DD-YYYY."
        return datetime.now().strftime(_fmt_map[format])


class AddDaysToDate(ToolBase):
    """Add a number of days to a date string."""

    @param_desc(
        date="Date string in any common format, e.g. '2026-05-30'",
        days="Number of days to add (positive integer)",
    )
    def execute(self, date: str, days: int) -> str:
        """Parse the date, add the given days, return ISO-formatted result.

        Args:
            date: Input date string.
            days: Number of days to add; must be non-negative.

        Returns:
            Resulting date in YYYY-MM-DD format, or an error message.
        """
        if days < 0:
            return "ERROR: days must be a non-negative integer"
        if not date or not date.strip():
            return "ERROR: empty date string"
        try:
            dt = dateutil_parser.parse(date, fuzzy=False, dayfirst=True)
        except (ValueError, OverflowError, TypeError) as exc:
            return f"ERROR: could not parse date '{date}': {exc}"
        return (dt + timedelta(days=days)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# State / Patch / Signal
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReactState:
    """Immutable agent state for one ReAct run."""

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

_MAX_STEPS = 10


class LlmCallVertex(StateVertex):
    """Calls the LLM and decides whether to invoke a tool or emit a final answer."""

    connector: Annotated[str, Field(description="LLM connector key from Context.")] = "default"
    tools: Annotated[str, Field(description="Tool registry key from Context.")] = "default"

    async def run(self, state: ReactState, ctx: Context) -> tuple[ReactSignal, ReactPatch]:
        """Run one LLM turn and route based on the response type.

        Args:
            state: Current ReactState snapshot.
            ctx: Shared context with LLM connector and tool registry.

        Returns:
            Tool-call patch when tools requested; final-answer patch otherwise.
        """
        if state.step >= _MAX_STEPS:
            return ReactSignal.max_steps, ReactPatch(
                final_answer=f"AGENT ERROR: exceeded {_MAX_STEPS} steps"
            )
        response = await ctx.llm(self.connector).achat(
            list(state.messages), tools=ctx.get_tools(self.tools).schemas()
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
        """Execute pending tool calls and return result messages.

        Args:
            state: Current ReactState snapshot.
            ctx: Shared context; logger used for structured output.

        Returns:
            (StdSignal.ok, patch) with tool result messages appended.
        """
        registry = ctx.get_tools(self.tools)
        tool_msgs: list[dict[str, Any]] = []
        for tc in state.last_tool_calls:
            ctx.logger.info("tool_call: name=%s", tc.name)
            tool = registry.get(tc.name)
            if tool is None:
                result = f"ERROR: unknown tool '{tc.name}'"
            else:
                try:
                    args = json.loads(tc.arguments or "{}")
                    result = str(tool.execute(**args))
                except Exception as exc:  # noqa: BLE001
                    result = f"ERROR: {exc}"
            ctx.logger.info("tool_result: name=%s result=%.80s", tc.name, result)
            tool_msgs.append(
                {"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": result}
            )
        return StdSignal.ok, ReactPatch(messages=tuple(tool_msgs), last_tool_calls=())


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


class ReactAgentApp(AgentApp):
    """Full ReAct agent with policy search, calculator, and date tools."""

    def __init__(self) -> None:
        super().__init__()
        self.connector = LlmConnector(cache=LlmFileCache(__file__))
        self.registry = ToolRegistry([
            SearchPolicy(), Calculator(), GetCurrentDate(), AddDaysToDate(),
        ])
        llm_vertex = LlmCallVertex()
        tool_vertex = ToolExecutionVertex()
        self.graph = StateGraph(
            start=llm_vertex,
            transitions=[
                Transition(llm_vertex, ReactSignal.tool_call, tool_vertex),
                Transition(tool_vertex, StdSignal.ok, llm_vertex),
                Transition(llm_vertex, ReactSignal.final_answer, StdEnd),
                Transition(llm_vertex, ReactSignal.max_steps, StdEnd),
            ],
        )

    @property
    def sample_prompts(self) -> list[str]:
        """Example prompts for the GUI prompt selector."""
        return [
            "What is twice the number of vacation days in our policy?",
            (
                "I haven't had vacation yet. "
                "If I take it all in three days from today, when will it end?"
            ),
            "How many remote work days am I allowed per week? And what date will it be in 14 days?",
        ]

    async def run_workflow(self) -> str | None:
        """Run the ReAct agent loop and return the final answer.

        Returns:
            Final answer string from the agent.
        """
        setup_pretty_logging()
        question = self.current_prompt or _DEFAULT_QUESTION
        ctx = Context(
            llm_connectors={"default": self.connector},
            tool_registries={"default": self.registry},
            event_bus=self.event_bus,
        )
        hooks = LoggingHooks()
        runner = StateGraphRunner(graph=self.graph, context=ctx, hooks=hooks)
        initial = ReactState(
            messages=(
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": question},
            )
        )
        final = cast(ReactState, await runner.run(initial))
        return final.final_answer


if __name__ == "__main__":
    ReactAgentApp().cli(__doc__, name=__name__)
