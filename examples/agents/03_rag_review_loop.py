"""RAG review loop: Retrieve → Generate → Review (with retry cycle).

Demonstrates a pure-Python state machine without a real LLM:
  1. Retrieve  — fetches stub context documents
  2. Generate  — produces a draft answer (improves on retry)
  3. Review    — approves the draft or sends it back for revision

The loop runs until the draft is approved or Review.max_attempts is reached.
FakeLlmConnector is used to satisfy the Context API — no LLM calls are made.

Run:
    uv run python examples/agents/03_rag_review_loop.py -h
    uv run python examples/agents/03_rag_review_loop.py run
    uv run python examples/agents/03_rag_review_loop.py gui
    uv run python examples/agents/03_rag_review_loop.py graph --browser
"""

from dataclasses import dataclass
from enum import auto
from typing import Annotated, Any, cast

from pydantic import Field

from agentflow import AgentApp
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
from agentflow.statemachine.testing import FakeLlmConnector

_STUB_DOCS: tuple[str, ...] = (
    "[doc1] Employees receive 25 days of paid vacation per year.",
    "[doc2] Sick leave allowance is 3 days per year without a doctor's note.",
)


# ---------------------------------------------------------------------------
# State / Patch / Signal
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewState:
    """Immutable state for the RAG review loop."""

    question: str = "How many vacation days do employees have?"
    context: tuple[str, ...] = ()
    draft: str = ""
    feedback: str = ""
    attempts: int = 0


@dataclass
class ReviewPatch:
    """Mutable patch applied to ReviewState after each super-step."""

    question: str | None = None
    context: tuple[str, ...] | None = None
    draft: str | None = None
    feedback: str | None = None
    attempts: int | None = None


class ReviewSignal(EnumSignal):
    """Routing signals emitted by the Review vertex."""

    approved = auto()
    needs_revision = auto()
    max_attempts = auto()


# ---------------------------------------------------------------------------
# Vertices
# ---------------------------------------------------------------------------


class Retrieve(StateVertex):
    """Fetches stub context documents relevant to the question."""

    async def run(self, state: ReviewState, ctx: Context) -> tuple[Any, ReviewPatch]:
        """Populate the context tuple with stub documents.

        Args:
            state: Current ReviewState snapshot.
            ctx: Shared context (not used in this pure-Python vertex).

        Returns:
            (StdSignal.ok, patch) with context set to stub documents.
        """
        ctx.logger.info("retrieve: loading %d stub documents", len(_STUB_DOCS))
        return StdSignal.ok, ReviewPatch(context=_STUB_DOCS)


class Generate(StateVertex):
    """Produces a draft answer; cites sources on retry attempts."""

    async def run(self, state: ReviewState, ctx: Context) -> tuple[Any, ReviewPatch]:
        """Generate a stub draft, citing context documents on second attempt.

        First attempt produces a short, uncited draft. Subsequent attempts
        produce a cited answer that passes the Review quality gate.

        Args:
            state: Current ReviewState snapshot.
            ctx: Shared context (not used in this pure-Python vertex).

        Returns:
            (StdSignal.ok, patch) with an updated draft and incremented attempt count.
        """
        new_attempts = state.attempts + 1
        if new_attempts == 1:
            draft = "Yes."
        else:
            context_text = " ".join(state.context)
            draft = f"According to company policy {context_text}"
        ctx.logger.info("generate: attempt=%d draft_len=%d", new_attempts, len(draft))
        return StdSignal.ok, ReviewPatch(draft=draft, attempts=new_attempts, feedback="")


class Review(StateVertex):
    """Approves the draft if it is cited and sufficiently detailed."""

    max_attempts: Annotated[
        int, Field(ge=1, le=10, description="Max Generate→Review cycles before forcing approval.")
    ] = 3

    async def run(self, state: ReviewState, ctx: Context) -> tuple[ReviewSignal, ReviewPatch]:
        """Check draft quality and route accordingly.

        Approval requires the draft to contain '[doc' (cited source) and
        be longer than 40 characters.  Emits max_attempts when the limit
        is reached to prevent infinite loops.

        Args:
            state: Current ReviewState snapshot.
            ctx: Shared context (not used in this pure-Python vertex).

        Returns:
            (ReviewSignal.approved, empty patch) when the draft passes;
            (ReviewSignal.max_attempts, empty patch) when the attempt limit is reached;
            (ReviewSignal.needs_revision, patch with feedback) otherwise.
        """
        if state.attempts >= self.max_attempts - 1:
            ctx.logger.info("review: max_attempts=%d reached", state.attempts)
            return ReviewSignal.max_attempts, ReviewPatch()
        is_cited = "[doc" in state.draft
        is_long = len(state.draft) > 40
        if is_cited and is_long:
            ctx.logger.info("review: approved draft_len=%d", len(state.draft))
            return ReviewSignal.approved, ReviewPatch()
        feedback = "Draft must cite sources (use [docN]) and be longer than 40 characters."
        ctx.logger.info("review: needs_revision feedback=%r", feedback)
        return ReviewSignal.needs_revision, ReviewPatch(feedback=feedback)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


class RagReviewApp(AgentApp):
    """RAG pipeline with an iterative review-revision loop (no real LLM)."""

    def __init__(self) -> None:
        super().__init__()
        self.connector = FakeLlmConnector()
        self.graph = StateGraph(
            start=Retrieve,
            transitions=[
                Transition(Retrieve, StdSignal.ok, Generate),
                Transition(Generate, StdSignal.ok, Review),
                Transition(Review, ReviewSignal.approved, StdEnd),
                Transition(Review, ReviewSignal.max_attempts, StdEnd),
                Transition(Review, ReviewSignal.needs_revision, Generate),
            ],
        )

    async def run_workflow(self) -> str | None:
        """Run the RAG review loop and print the approved draft.

        Returns:
            Final draft string or a status message.
        """
        setup_pretty_logging()
        ctx = Context(
            llm_connectors={"default": self.connector},
            event_bus=self.event_bus,
        )
        hooks = LoggingHooks()
        runner = StateGraphRunner(graph=self.graph, context=ctx, hooks=hooks)
        final = cast(ReviewState, await runner.run(ReviewState()))
        print(f"\nFinal draft (attempts={final.attempts}):\n{final.draft}")
        return final.draft or "Completed."


if __name__ == "__main__":
    RagReviewApp().cli(__doc__, name=__name__)
