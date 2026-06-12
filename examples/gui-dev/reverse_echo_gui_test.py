"""Reverse-echo agent — GUI Chat tab smoke test (no LLM).

Accepts a user prompt and returns the words in reversed order with each
word's characters also reversed:

    "ABC DEF"  →  "FED CBA"

Purpose: test the Chat tab without requiring any LLM API keys.
"""

# Run:
#     uv run python examples/agents/07_reverse_echo.py run
#     uv run python examples/agents/07_reverse_echo.py gui
#     uv run python examples/agents/07_reverse_echo.py graph --browser

from __future__ import annotations

from dataclasses import dataclass
import logging

from agentflow import AgentApp
from agentflow.statemachine import (
    Context,
    StateGraph,
    StateVertex,
    StdEnd,
    StdSignal,
    Transition,
)

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class EchoState:
    """Immutable state passed through the graph."""

    question: str = ""
    answer: str = ""


@dataclass
class EchoPatch:
    """Partial state update."""

    answer: str | None = None


class ReverseVertex(StateVertex):
    """Reverse every word and the word order of the input prompt.

    Example: 'ABC DEF' → 'FED CBA'.
    No LLM is used — pure Python string transformation.
    """

    async def run(self, state: EchoState, ctx: Context) -> tuple[object, EchoPatch]:
        """Reverse characters in each word and reverse the word order.

        Args:
            state: Current state containing the user question.
            ctx:   Shared context (unused — no LLM required).

        Returns:
            Tuple (StdSignal.ok, EchoPatch with reversed answer).
        """
        words = state.question.split()
        reversed_answer = " ".join(w[::-1] for w in reversed(words))
        logger.info("Reversed answer: %s", reversed_answer)
        return StdSignal.ok, EchoPatch(answer=reversed_answer)


app = AgentApp(
    doc=__doc__,
    default_question="ABC DEF",
    sample_prompts=[
        "ABC DEF",
        "Hello World",
        "agentflow GUI test",
        "one two three four five",
    ],
    context=Context(),
    state_graph=StateGraph(
        start=ReverseVertex,
        transitions=[
            Transition(ReverseVertex, StdSignal.ok, StdEnd),
        ],
    ),
    initial_state_factory=lambda q: EchoState(question=q or "ABC DEF"),
)

app._extract_result = lambda state: state.answer  # type: ignore[method-assign, attr-defined]

if __name__ == "__main__":
    app.cli(__doc__, name=__name__)
