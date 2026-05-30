"""Chapter 02 (my): tool-calling demo rewritten using agentflow.statemachine.

Demonstrates the same flow as orig/02_tool_calling_demo.py and my/02_tool_calling_demo.py,
but the ReAct loop is expressed as an explicit StateGraph (BSP) instead of ToolAgent.

Library phase: Epic E010 (Core StateGraph MVP) is complete — manual vertex instances,
StateGraphRunner, LoggingHooks, ctx.run_sync for sync LlmConnector.chat().
Integration adapters (ToolAgentVertex, E050) are not used here.

Graph topology (same pattern as 04_react_agent_statemachine.py):
    LlmCallVertex --tool_call--> ToolExecutionVertex
                                        |
                  <-------- ok ---------+   (cycle)
    LlmCallVertex --final_answer--> FinalAnswerEnd
    LlmCallVertex --max_steps----> FinalAnswerEnd

Tools:
  - Calculator  (src.agentflow.tools.common_tools)
  - FakeWeather (demo stub, same as my/02_tool_calling_demo.py)

Run (requires a running LLM backend, e.g. Ollama):
    cd <repo-root>
    ollama pull qwen3:8b
    uv run python examples/patterns/02_tool_calling_demo.1.py

Switch backend:
    LLM_BACKEND=openai uv run python examples/patterns/02_tool_calling_demo.1.py
    LLM_MODEL=qwen3:8b uv run python examples/patterns/02_tool_calling_demo.1.py
"""



import json  # noqa: E402
import logging  # noqa: E402
import operator  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from enum import auto  # noqa: E402
from typing import Annotated, Any, cast  # noqa: E402

from agentflow.llm.ChatResponse import ToolCallInfo  # noqa: E402
from agentflow.llm.LlmConfig import LlmConfig  # noqa: E402
from agentflow.llm.LlmConnector import LlmConnector  # noqa: E402
from agentflow.statemachine import (  # noqa: E402
    Context,
    End,
    EnumSignal,
    StateGraph,
    StateGraphRunner,
    StateVertex,
    StdSignal,
    Transition,
)
from agentflow.statemachine.hooks import LoggingHooks  # noqa: E402
from agentflow.tools.common_tools.Calculator import Calculator  # noqa: E402
from agentflow.tools.Tool import ToolBase, param_desc  # noqa: E402

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Demo-specific tool (same as my/02_tool_calling_demo.py)
# ---------------------------------------------------------------------------


class FakeWeather(ToolBase):
    """Return the current weather for a given city (hard-coded demo data)."""

    _WEATHER_DB: dict[str, str] = {
        "Prague": "12 C, cloudy",
        "Tokyo": "24 C, sunny",
        "New York": "18 C, windy",
    }

    @param_desc(city="City name, e.g. 'Prague'.")
    def execute(self, city: str) -> str:  # type: ignore[override]
        """Look up weather for the city from the hard-coded database.

        Args:
            city: City name.

        Returns:
            Weather description string, or ``Unknown city`` when not found.
        """
        result = self._WEATHER_DB.get(city, "Unknown city")
        logger.debug("FakeWeather: city=%s result=%s", city, result)
        return result


# ---------------------------------------------------------------------------
# State & Patch
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolCallingState:
    """Immutable conversation state for the tool-calling demo graph.

    Attributes:
        messages: OpenAI-format message dicts accumulated across turns.
        last_tool_calls: Tool calls from the latest LLM response.
        final_answer: Set when the LLM returns a text answer.
        step: Number of LLM calls made so far.
    """

    messages: Annotated[tuple[dict[str, Any], ...], operator.add] = ()
    last_tool_calls: tuple[ToolCallInfo, ...] = ()
    final_answer: str = ""
    step: int = 0


@dataclass
class ToolCallingPatch:
    """Patch applied to ToolCallingState after each BSP super-step.

    None in any field means leave unchanged (apply_patches convention).
    """

    messages: tuple[dict[str, Any], ...] | None = None
    last_tool_calls: tuple[ToolCallInfo, ...] | None = None
    final_answer: str | None = None
    step: int | None = None


# ---------------------------------------------------------------------------
# Routing signals
# ---------------------------------------------------------------------------


class ToolCallingSignal(EnumSignal):
    """Routing signals for the tool-calling state machine."""

    tool_call = auto()
    final_answer = auto()
    max_steps = auto()


# ---------------------------------------------------------------------------
# Vertices
# ---------------------------------------------------------------------------


class LlmCallVertex(StateVertex):
    """Call the LLM with current messages and tool schemas."""

    def __init__(self, tools: list[ToolBase], max_steps: int = 6) -> None:
        self._tool_schemas = [t.to_openai_schema() for t in tools]
        self._max_steps = max_steps

    async def run(self, state: object, ctx: Context) -> tuple[ToolCallingSignal, ToolCallingPatch]:
        """Invoke LLM and route to tools, final answer, or max-steps exit."""
        s = cast(ToolCallingState, state)

        if s.step >= self._max_steps:
            return ToolCallingSignal.max_steps, ToolCallingPatch(
                final_answer=f"AGENT ERROR: exceeded max_steps={self._max_steps}"
            )

        response = await ctx.run_sync(
            ctx.connector.chat,
            list(s.messages),
            tools=self._tool_schemas,
        )

        assistant_msg = response.to_message_dict()

        if response.has_tool_calls:
            return ToolCallingSignal.tool_call, ToolCallingPatch(
                messages=(assistant_msg,),
                last_tool_calls=tuple(response.tool_calls or []),
                step=s.step + 1,
            )

        return ToolCallingSignal.final_answer, ToolCallingPatch(
            messages=(assistant_msg,),
            final_answer=response.text,
            step=s.step + 1,
        )


class ToolExecutionVertex(StateVertex):
    """Execute pending tool calls from state.last_tool_calls."""

    def __init__(self, tools: list[ToolBase]) -> None:
        self._tool_map: dict[str, ToolBase] = {t.name: t for t in tools}

    async def run(self, state: object, ctx: Context) -> tuple[Any, ToolCallingPatch]:
        """Run each tool call and append role=tool messages to history."""
        s = cast(ToolCallingState, state)
        tool_msgs: list[dict[str, Any]] = []

        for tc in s.last_tool_calls:
            tool = self._tool_map.get(tc.name)
            ctx.logger.info("tool_call: name=%s id=%s", tc.name, tc.id)

            if tool is None:
                result = f"ERROR: unknown tool '{tc.name}'"
            else:
                try:
                    args = json.loads(tc.arguments or "{}")
                    result = str(tool.execute(**args))
                except Exception as exc:  # noqa: BLE001 — errors go back to LLM
                    result = f"ERROR: {exc}"

            ctx.logger.info("tool_result: name=%s result=%.80s", tc.name, result)
            tool_msgs.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": result,
                }
            )

        return StdSignal.ok, ToolCallingPatch(
            messages=tuple(tool_msgs),
            last_tool_calls=(),
        )


class FinalAnswerEnd(End):
    """Terminal node — logs final answer and stops the BSP loop."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, ToolCallingPatch]:
        """Log final answer and return done signal."""
        s = cast(ToolCallingState, state)
        ctx.logger.info("final_answer: %s", s.final_answer or "(no answer)")
        return StdSignal.done, ToolCallingPatch()


# ---------------------------------------------------------------------------
# Graph builder & runner
# ---------------------------------------------------------------------------

_TOOLS: list[ToolBase] = [Calculator(), FakeWeather()]

_SYSTEM_PROMPT = (
    "You are a helpful assistant. "
    "When a tool would give a more reliable answer, call it. "
    "Otherwise answer directly. "
    "Be concise."
)

_DEFAULT_QUESTION = (
    "What's the weather in Prague? "
    "And what is the Prague temperature (the number only) multiplied by 23?"
)


def build_tool_calling_graph(max_steps: int = 6) -> StateGraph:
    """Wire the tool-calling ReAct loop as a StateGraph (E010 manual instances).

    Args:
        max_steps: Maximum LLM turns before forced termination.

    Returns:
        StateGraph ready for StateGraphRunner.
    """
    llm_vertex = LlmCallVertex(tools=_TOOLS, max_steps=max_steps)
    tool_exec = ToolExecutionVertex(tools=_TOOLS)
    end = FinalAnswerEnd()

    return StateGraph(
        start=llm_vertex,
        transitions=[
            Transition(llm_vertex, ToolCallingSignal.tool_call, tool_exec),
            Transition(tool_exec, StdSignal.ok, llm_vertex),
            Transition(llm_vertex, ToolCallingSignal.final_answer, end),
            Transition(llm_vertex, ToolCallingSignal.max_steps, end),
        ],
    )


def run_agent(question: str, max_steps: int = 6) -> str:
    """Run the tool-calling agent for one question and return the final answer.

    Args:
        question: User question.
        max_steps: Maximum LLM turns.

    Returns:
        Final answer text from the LLM or an error message.
    """
    connector = LlmConnector.create(LlmConfig.from_env())
    ctx = Context(connector=connector)
    hooks = LoggingHooks()

    initial_state = ToolCallingState(
        messages=(
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": question},
        )
    )

    graph = build_tool_calling_graph(max_steps=max_steps)
    runner = StateGraphRunner(graph=graph, context=ctx, hooks=hooks)

    final = cast(ToolCallingState, runner.run_sync(initial_state))
    return final.final_answer


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s — %(message)s",
    )

    config = LlmConfig.from_env()
    print(f"LLM backend : {config.backend}")
    print(f"LLM model   : {config.model}")
    print("-" * 40)

    question = _DEFAULT_QUESTION
    print(f"QUESTION: {question}")

    answer = run_agent(question)

    print("\n========== FINAL ANSWER ==========")
    print(answer)
