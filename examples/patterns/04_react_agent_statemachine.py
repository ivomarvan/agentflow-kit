"""Chapter 04 (my): ReAct agent rewritten using agentflow.statemachine.

Demonstrates how the same ReAct loop from orig/04_react_agent_plain.py maps
to a StateGraph with BSP execution. The tools are the same; the loop is
driven by the state machine instead of a hand-written for-loop.

Graph topology:
    LlmCallVertex --tool_call--> ToolExecutionVertex
                                        |
                  <-------- ok ---------+   (cycle)
    LlmCallVertex --final_answer--> FinalAnswerEnd
    LlmCallVertex --max_steps----> FinalAnswerEnd

Run (requires a running LLM backend, e.g. Ollama):
    uv run python examples/patterns/04_react_agent_statemachine.py              # run workflow
    uv run python examples/patterns/04_react_agent_statemachine.py -h           # help
    uv run python examples/patterns/04_react_agent_statemachine.py browser      # graph in browser
    uv run python examples/patterns/04_react_agent_statemachine.py graph-html   # save HTML graph
"""

import json
import logging
import operator
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import auto
from typing import Annotated, Any, cast

from dateutil import parser as dateutil_parser

from agentflow import AgentApp, ToolRegistry
from agentflow.llm.ChatResponse import ToolCallInfo
from agentflow.llm.LlmConfig import LlmConfig
from agentflow.llm.LlmConnector import LlmConnector
from agentflow.statemachine import (
    Context,
    End,
    EnumSignal,
    StateGraph,
    StateGraphRunner,
    StateVertex,
    StdSignal,
    Transition,
)
from agentflow.statemachine.hooks import LoggingHooks
from agentflow.tools.Tool import ToolBase, param_desc

# ---------------------------------------------------------------------------
# Tools — same implementations as in orig/04_react_agent_plain.py,
# wrapped as ToolBase subclasses so agentflow generates the JSON schema.
# ---------------------------------------------------------------------------

POLICIES: dict[str, str] = {
    "vacation": "Employees are entitled to 25 days of paid vacation per year.",
    "sick days": "Employees may take up to 3 sick days per year without a doctor's note.",
    "remote work": "Remote work is allowed up to 4 days a week.",
    "parking": "Parking at the HQ is free for all employees.",
}


class SearchPolicy(ToolBase):
    """Search the company's internal policies (vacation, sick days, remote work, parking).

    Returns the most relevant policy text.
    """

    @param_desc(query="What you want to look up, e.g. 'vacation days'")
    def execute(self, query: str) -> str:  # type: ignore[override]
        """Return policy text matching the query, or a not-found message.

        Args:
            query: Free-text search query.

        Returns:
            Matching policy lines joined by newline, or 'No relevant policy found.'
        """
        q = query.lower()
        hits: list[str] = [
            text for key, text in POLICIES.items()
            if key in q or any(w in q for w in key.split())
        ]
        return "\n".join(hits) if hits else "No relevant policy found."


class Calculator(ToolBase):
    """Evaluate a simple arithmetic expression."""

    @param_desc(expression="Math expression using +, -, *, /, (, ), e.g. '25 * 2'")
    def execute(self, expression: str) -> str:  # type: ignore[override]
        """Safely evaluate a math expression restricted to numeric characters and operators.

        Args:
            expression: Mathematical expression string.

        Returns:
            String result, or 'ERROR: ...' on invalid input.
        """
        allowed = set("0123456789+-*/(). ")
        if not set(expression) <= allowed:
            return "ERROR: disallowed characters"
        try:
            return str(eval(expression))  # noqa: S307
        except Exception as exc:
            return f"ERROR: {exc}"


class GetCurrentDate(ToolBase):
    """Return the current date in a specified format."""

    @param_desc(format="Date format: 'YYYY-MM-DD', 'DD-MM-YYYY', or 'MM-DD-YYYY'")
    def execute(self, format: str = "YYYY-MM-DD") -> str:  # type: ignore[override]
        """Return today's date formatted according to the requested format.

        Args:
            format: One of 'YYYY-MM-DD', 'DD-MM-YYYY', 'MM-DD-YYYY'.

        Returns:
            Formatted date string, or 'ERROR: invalid format'.
        """
        fmt_map = {
            "YYYY-MM-DD": "%Y-%m-%d",
            "DD-MM-YYYY": "%d-%m-%Y",
            "MM-DD-YYYY": "%m-%d-%Y",
        }
        if format not in fmt_map:
            return "ERROR: invalid format"
        return datetime.now().strftime(fmt_map[format])


class AddDaysToDate(ToolBase):
    """Add a given number of days to a date and return the result."""

    @param_desc(
        date="Source date string in any common format, e.g. '2026-01-15'",
        days="Number of days to add (must be non-negative)",
    )
    def execute(self, date: str, days: int) -> str:  # type: ignore[override]
        """Parse date, add days, return result as YYYY-MM-DD string.

        Args:
            date: Source date in any parseable format.
            days: Non-negative integer number of days to add.

        Returns:
            Result date as 'YYYY-MM-DD', or 'ERROR: ...' on bad input.
        """
        if days < 0:
            return "ERROR: days must be a non-negative integer"
        try:
            dt = dateutil_parser.parse(date, fuzzy=False, dayfirst=True)
        except (ValueError, OverflowError, TypeError) as exc:
            return f"ERROR: could not parse date — {exc}"
        return (dt + timedelta(days=days)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# State & Patch
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReactState:
    """Immutable conversation state for the ReAct agent graph.

    Attributes:
        messages: OpenAI-format message dicts accumulated across all turns.
                  Uses operator.add reducer so parallel writes (if any) concat.
        last_tool_calls: Tool calls from the latest LLM response, consumed by
                         ToolExecutionVertex in the next super-step. Cleared
                         after execution.
        final_answer: Set by LlmCallVertex on final turn; empty string otherwise.
        step: Number of LLM calls made so far (0 = not yet started).
    """

    messages: Annotated[tuple[dict[str, Any], ...], operator.add] = ()
    # last_tool_calls uses last-writer-wins (only one vertex writes per step)
    last_tool_calls: tuple[ToolCallInfo, ...] = ()
    final_answer: str = ""
    step: int = 0


@dataclass
class ReactPatch:
    """Mutable patch applied to ReactState after each BSP super-step.

    None in any field means "leave unchanged" (apply_patches convention).

    Attributes:
        messages: New messages to concatenate via operator.add reducer.
        last_tool_calls: Replaces last_tool_calls (last-writer-wins).
        final_answer: Sets the final answer text.
        step: Increments step counter.
    """

    messages: tuple[dict[str, Any], ...] | None = None
    last_tool_calls: tuple[ToolCallInfo, ...] | None = None
    final_answer: str | None = None
    step: int | None = None


# ---------------------------------------------------------------------------
# Routing signals
# ---------------------------------------------------------------------------

class ReactSignal(EnumSignal):
    """Routing signals for the ReAct state machine."""

    tool_call = auto()      # LLM requested tool calls → execute them
    final_answer = auto()   # LLM returned a final text answer → terminate
    max_steps = auto()      # Step limit reached → terminate with error


# ---------------------------------------------------------------------------
# Vertices
# ---------------------------------------------------------------------------

class LlmCallVertex(StateVertex):
    """Call the LLM with current conversation history and tool schemas.

    On each BSP super-step:
    - Appends the LLM assistant response to messages.
    - If LLM requested tool calls: stores them in last_tool_calls, emits tool_call.
    - If LLM returned a text answer: stores it in final_answer, emits final_answer.
    - If step limit exceeded: emits max_steps without calling LLM.

    Args:
        tools: List of ToolBase instances whose schemas are passed to the LLM.
        max_steps: Maximum number of LLM calls before forced termination.
    """

    def __init__(self, tools: list[ToolBase], max_steps: int = 7) -> None:
        self._tool_schemas = [t.to_openai_schema() for t in tools]
        self._max_steps = max_steps

    async def run(
        self, state: object, ctx: Context
    ) -> tuple[ReactSignal, ReactPatch]:
        """Invoke LLM and route based on whether it wants tools or a final answer.

        Args:
            state: Current ReactState snapshot.
            ctx: Shared context with LlmConnector.

        Returns:
            (ReactSignal.tool_call, patch) when LLM requests tools,
            (ReactSignal.final_answer, patch) when LLM provides final text,
            (ReactSignal.max_steps, patch) when step limit is exceeded.
        """
        s = cast(ReactState, state)

        if s.step >= self._max_steps:
            return ReactSignal.max_steps, ReactPatch(
                final_answer=f"AGENT ERROR: exceeded max_steps={self._max_steps}"
            )

        # Call LLM synchronously via run_sync (E040 will make this async-native)
        response = await ctx.run_sync(
            ctx.connector.chat,
            list(s.messages),
            tools=self._tool_schemas,
        )

        assistant_msg = response.to_message_dict()

        if response.has_tool_calls:
            return ReactSignal.tool_call, ReactPatch(
                messages=(assistant_msg,),
                last_tool_calls=tuple(response.tool_calls or []),
                step=s.step + 1,
            )

        return ReactSignal.final_answer, ReactPatch(
            messages=(assistant_msg,),
            final_answer=response.text,
            step=s.step + 1,
        )


class ToolExecutionVertex(StateVertex):
    """Execute all pending tool calls stored in state.last_tool_calls.

    Appends tool result messages (role='tool') to the conversation history
    and clears last_tool_calls. Always returns StdSignal.ok to loop back
    to LlmCallVertex.

    Args:
        tools: List of ToolBase instances. Tool lookup is by ToolBase.name.
    """

    def __init__(self, tools: list[ToolBase]) -> None:
        self._tool_map: dict[str, ToolBase] = {t.name: t for t in tools}

    async def run(
        self, state: object, ctx: Context
    ) -> tuple[Any, ReactPatch]:
        """Execute pending tool calls and return tool result messages.

        Args:
            state: Current ReactState with last_tool_calls populated.
            ctx: Shared context (logger used for tool call logging).

        Returns:
            (StdSignal.ok, patch) with tool result messages appended.
        """
        s = cast(ReactState, state)
        tool_msgs: list[dict[str, Any]] = []

        for tc in s.last_tool_calls:
            tool = self._tool_map.get(tc.name)
            ctx.logger.info(
                "tool_call: name=%s id=%s", tc.name, tc.id
            )

            if tool is None:
                result = f"ERROR: unknown tool '{tc.name}'"
            else:
                try:
                    args = json.loads(tc.arguments or "{}")
                    result = str(tool.execute(**args))
                except Exception as exc:  # noqa: BLE001 — tool errors go back to LLM
                    result = f"ERROR: {exc}"

            ctx.logger.info("tool_result: name=%s result=%.80s", tc.name, result)
            tool_msgs.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tc.name,
                "content": result,
            })

        return StdSignal.ok, ReactPatch(
            messages=tuple(tool_msgs),
            last_tool_calls=(),  # consumed — clear for next round
        )


class FinalAnswerEnd(End):
    """Terminal node — logs the final answer and signals done.

    Reads state.final_answer and emits it to the logger so the caller can
    retrieve it from the log or by inspecting the final ReactState.
    """

    async def run(self, state: object, ctx: Context) -> tuple[Any, ReactPatch]:
        """Log final answer and terminate the run.

        Args:
            state: Final ReactState; final_answer is read for logging.
            ctx: Shared context (logger).

        Returns:
            (StdSignal.done, empty patch) to terminate BSP loop.
        """
        s = cast(ReactState, state)
        ctx.logger.info(
            "final_answer: %s", s.final_answer or "(no answer)"
        )
        return StdSignal.done, ReactPatch()


_SYSTEM_PROMPT = (
    "You are a helpful company assistant. "
    "Break down each user question into elementary logical parts. "
    "To obtain any fact or perform any date arithmetic, you MUST always use "
    "the appropriate tool. "
    "Never calculate or assume anything — always call the right tool. "
    "Answer concisely in English."
)


class ReactAgentApp(AgentApp):
    """Demonstrates the ReAct loop (LLM + tools) as a BSP StateGraph."""

    def __init__(self) -> None:
        super().__init__()
        self.connector = LlmConnector.create(LlmConfig.from_env())
        self.registry = ToolRegistry(tools=[
            SearchPolicy(),
            Calculator(),
            GetCurrentDate(),
            AddDaysToDate(),
        ])
        llm_vertex = LlmCallVertex(tools=self.registry.tools, max_steps=7)
        tool_exec = ToolExecutionVertex(tools=self.registry.tools)
        end = FinalAnswerEnd()
        self.graph = StateGraph(
            start=llm_vertex,
            transitions=[
                Transition(llm_vertex, ReactSignal.tool_call, tool_exec),
                Transition(tool_exec, StdSignal.ok, llm_vertex),  # loop
                Transition(llm_vertex, ReactSignal.final_answer, end),
                Transition(llm_vertex, ReactSignal.max_steps, end),
            ],
        )

    async def run_workflow(self) -> str | None:
        """Run the ReAct agent for a demo question and print the final answer."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s %(name)s — %(message)s",
        )

        question = (
            "I haven't had any vacation yet. "
            "If I take it all in three days from today, when will the vacation end?"
        )
        print(f"QUESTION: {question}")

        ctx = Context(connector=self.connector)
        hooks = LoggingHooks()
        initial_state = ReactState(
            messages=(
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": question},
            )
        )
        runner = StateGraphRunner(graph=self.graph, context=ctx, hooks=hooks)
        final = cast(ReactState, await runner.run(initial_state))

        print("\n========== FINAL ANSWER ==========")
        print(final.final_answer)


if __name__ == "__main__":
    ReactAgentApp().cli(__doc__, name=__name__)
