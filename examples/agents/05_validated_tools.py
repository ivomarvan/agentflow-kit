"""ReAct agent with input-validating tools (guardrails at the tool boundary).

Demonstrates that ToolBase.execute() can validate inputs and return error
strings instead of raising exceptions.  The LLM receives the error as an
observation and self-corrects — no special framework support needed.

Tools with built-in guardrails:
  - ValidatedCalculator   — rejects expressions with non-arithmetic characters
  - ValidatedSearchPolicy — rejects empty or excessively long queries

Run:
    uv run python examples/agents/05_validated_tools.py
    uv run python examples/agents/05_validated_tools.py gui
    uv run python examples/agents/05_validated_tools.py browser
"""

import json
import operator
import re
from dataclasses import dataclass
from enum import auto
from typing import Annotated, Any, cast

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

_DEFAULT_QUESTION = "What is twice the vacation days count in our policy?"

_POLICIES: dict[str, str] = {
    "vacation": "Employees are entitled to 25 days of paid vacation per year.",
    "sick days": "Employees may take up to 3 sick days per year without a doctor's note.",
    "remote work": "Remote work is allowed up to 4 days a week.",
    "parking": "Parking at the HQ is free for all employees.",
}

_SYSTEM_PROMPT = (
    "You are a helpful company assistant. "
    "Use search_policy to look up policy facts and calculator to perform arithmetic. "
    "Always use tools — never guess facts or calculate manually."
)

_SAFE_EXPR_RE = re.compile(r"^[0-9+\-*/(). ]+$")
_MAX_EXPR_LEN = 100
_MAX_QUERY_LEN = 200


# ---------------------------------------------------------------------------
# Tools with built-in validation
# ---------------------------------------------------------------------------


class ValidatedCalculator(ToolBase):
    """Arithmetic evaluator that blocks expressions with dangerous characters."""

    @param_desc(expression="Safe arithmetic expression, e.g. '25 * 2'")
    def execute(self, expression: str) -> str:
        """Validate then evaluate the expression.

        Rejects expressions containing anything outside digits, operators,
        parentheses, or spaces.  This blocks code-injection attempts such as
        ``__import__('os').system('ls')``.

        Args:
            expression: Math expression string submitted by the LLM.

        Returns:
            Numeric result as string, or a 'GUARDRAIL: ...' error string
            that the LLM will see as an observation and self-correct.
        """
        if len(expression) > _MAX_EXPR_LEN:
            return f"GUARDRAIL: expression too long ({len(expression)} > {_MAX_EXPR_LEN} chars)"
        if not _SAFE_EXPR_RE.match(expression):
            return (
                "GUARDRAIL: expression contains disallowed characters — "
                "only digits and +-*/() are permitted"
            )
        try:
            return str(eval(expression))  # noqa: S307
        except Exception as exc:  # noqa: BLE001
            return f"ERROR: {exc}"


class ValidatedSearchPolicy(ToolBase):
    """Policy search that rejects empty or excessively long queries."""

    @param_desc(query="What you want to look up, e.g. 'vacation days'")
    def execute(self, query: str) -> str:
        """Validate the query then search the policy database.

        Args:
            query: Natural-language search string.

        Returns:
            Matching policy text, a not-found message, or a 'GUARDRAIL: ...'
            error string when the query fails validation.
        """
        if not query or not query.strip():
            return "GUARDRAIL: query must be a non-empty string"
        if len(query) > _MAX_QUERY_LEN:
            return f"GUARDRAIL: query too long ({len(query)} > {_MAX_QUERY_LEN} chars)"
        q = query.lower()
        hits = [
            text for key, text in _POLICIES.items() if key in q or any(w in q for w in key.split())
        ]
        return "\n".join(hits) if hits else "No relevant policy found."


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

_MAX_STEPS = 7


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
        """Execute pending tool calls; validation errors are returned as observations.

        Args:
            state: Current ReactState snapshot.
            ctx: Shared context; logger used for structured output.

        Returns:
            (StdSignal.ok, patch) with tool result messages appended.
            GUARDRAIL errors are included as normal observations so the LLM
            can self-correct without the graph erroring out.
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


class ValidatedToolsApp(AgentApp):
    """ReAct agent showcasing input validation as guardrails inside tools."""

    def __init__(self) -> None:
        super().__init__()
        self.connector = LlmConnector(cache=LlmFileCache(__file__))
        self.registry = ToolRegistry([ValidatedCalculator(), ValidatedSearchPolicy()])
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
            "What is twice the vacation days count in our policy?",
            "How many sick days do we have, and what is 3 * 7?",
            "What are the remote work rules? Also compute (10 + 5) * 2.",
        ]

    async def run_workflow(self) -> str | None:
        """Run the validated-tools agent and return the final answer.

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
    ValidatedToolsApp().cli(__doc__, name=__name__)
