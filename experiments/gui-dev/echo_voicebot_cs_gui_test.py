"""Echo agent — VoiceBot tab smoke test (no LLM).

Accepts a user prompt and responds: "Slyšel jsem <prompt>."

Purpose: test the VoiceBot tab (STT → workflow → TTS) without
requiring any LLM API keys.
"""

# Run:
#     uv run python examples/agents/08_echo_voicebot.py run
#     uv run python examples/agents/08_echo_voicebot.py gui
#     uv run python examples/agents/08_echo_voicebot.py graph --browser

from __future__ import annotations

import logging
from dataclasses import dataclass

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
    """Partial state update produced by EchoVertex."""

    answer: str | None = None


class EchoVertex(StateVertex):
    """Return 'Slyšel jsem: <question>.' without calling any LLM.

    Designed to test the VoiceBot tab end-to-end:
    speech-to-text → workflow → text-to-speech.
    """

    async def run(self, state: EchoState, ctx: Context) -> tuple[object, EchoPatch]:
        """Echo the question back as a plain confirmation sentence.

        Args:
            state: Current state containing the user question.
            ctx:   Shared context (unused — no LLM required).

        Returns:
            Tuple (StdSignal.ok, EchoPatch with the echo answer).
        """
        answer = f"Slyšel jsem: {state.question}."
        logger.info("Echo answer: %s", answer)
        return StdSignal.ok, EchoPatch(answer=answer)


app = AgentApp(
    doc=__doc__,
    default_question="Ahoj světe",
    sample_prompts=[
        "Ahoj světe",
        "Jak se máš?",
        "Testuju VoiceBot",
        "Hello World",
    ],
    context=Context(),
    state_graph=StateGraph(
        start=EchoVertex,
        transitions=[
            Transition(EchoVertex, StdSignal.ok, StdEnd),
        ],
    ),
    initial_state_factory=lambda q: EchoState(question=q or "Ahoj světe"),
)

app._extract_result = lambda state: state.answer  # type: ignore[method-assign, attr-defined]

if __name__ == "__main__":
    app.cli(__doc__, name=__name__)
