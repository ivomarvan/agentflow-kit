"""Parallel-research-with-loop demo for agentflow.statemachine.

Demonstrates all major statemachine features in a single script:

  - Parallel fan-out  : Research → Parallel(WriteIntro, WriteBody)
  - Fan-in join       : both parallel vertices route to the same Review vertex
  - Cycle / loop      : Review routes back to Research on needs_revision
  - Custom signal enum: ReviewSignal (approved / needs_revision)
  - Loop termination  : auto-approve after _MAX_REVISIONS Research iterations

Run with:
    uv run python examples/quickstart/04_parallel_research_loop.py -h           # help
    uv run python examples/quickstart/04_parallel_research_loop.py run            # run workflow
    uv run python examples/quickstart/04_parallel_research_loop.py graph --browser
    uv run python examples/quickstart/04_parallel_research_loop.py graph -o graph.html
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from agentflow import AgentApp
from agentflow.logging_config import setup_pretty_logging
from agentflow.statemachine import (
    Context,
    Parallel,
    StateGraph,
    StateGraphRunner,
    StateVertex,
    StdEnd,
    StdSignal,
    Transition,
)
from agentflow.statemachine.hooks import LoggingHooks
from agentflow.statemachine.testing import FakeLlmConnector

# Minimum number of Review cycles before auto-approval.
_MAX_REVISIONS: int = 2


class ReviewSignal(Enum):
    """Domain-specific routing signals emitted by the Review vertex."""

    approved = "approved"
    needs_revision = "needs_revision"


@dataclass(frozen=True)
class ResearchState:
    """Immutable state for the parallel-research-with-loop demo.

    Attributes:
        topic: Research topic title; constant throughout the run.
        intro: Written introduction section; reset at the start of each iteration.
        body: Written body section; reset at the start of each iteration.
        review_notes: Reviewer feedback from the most recent Review cycle.
        revision_count: Total number of completed Research → Review cycles.
        final_report: Assembled report produced by Publish; non-empty after approval.
    """

    topic: str = "BSP execution model in AI agents"
    intro: str = ""
    body: str = ""
    review_notes: str = ""
    revision_count: int = 0
    final_report: str = ""


@dataclass
class ResearchPatch:
    """Mutable patch applied to ResearchState after each super-step.

    A field set to None means "do not overwrite" in apply_patches().
    An empty string is a valid value and resets the corresponding field.

    Attributes:
        topic: Optional new topic (never mutated in this demo).
        intro: Optional new intro section; set by WriteIntro, reset by Research.
        body: Optional new body section; set by WriteBody, reset by Research.
        review_notes: Optional reviewer feedback; set by Review, reset by Research.
        revision_count: Optional new cycle count; incremented by Review.
        final_report: Optional assembled report; set by Publish.
    """

    topic: str | None = None
    intro: str | None = None
    body: str | None = None
    review_notes: str | None = None
    revision_count: int | None = None
    final_report: str | None = None


class Research(StateVertex):
    """Resets draft fields and logs the start of a new research iteration."""

    async def run(self, state: ResearchState, ctx: Context) -> tuple[Any, Any]:
        """Reset intro, body and review_notes, then signal fan-out to parallel writers.

        Args:
            state: Current ResearchState snapshot.
            ctx: Shared context (not used here).

        Returns:
            (StdSignal.ok, ResearchPatch) that clears draft fields for this cycle.
        """
        print(f"Research: iteration {state.revision_count + 1}, topic='{state.topic}'")
        return StdSignal.ok, ResearchPatch(intro="", body="", review_notes="")


class WriteIntro(StateVertex):
    """Writes the introduction section of the research report."""

    async def run(self, state: ResearchState, ctx: Context) -> tuple[Any, Any]:
        """Produce a stub introduction and signal completion.

        Args:
            state: Current ResearchState snapshot; topic is read for the intro text.
            ctx: Shared context (not used here).

        Returns:
            (StdSignal.done, ResearchPatch) with intro populated.
        """
        return StdSignal.done, ResearchPatch(intro=f"[Intro for '{state.topic}']")


class WriteBody(StateVertex):
    """Writes the body content of the research report."""

    async def run(self, state: ResearchState, ctx: Context) -> tuple[Any, Any]:
        """Produce a stub body and signal completion.

        Args:
            state: Current ResearchState snapshot; topic is read for the body text.
            ctx: Shared context (not used here).

        Returns:
            (StdSignal.done, ResearchPatch) with body populated.
        """
        return StdSignal.done, ResearchPatch(body=f"[Body for '{state.topic}']")


class Review(StateVertex):
    """Reviews the draft and auto-approves after _MAX_REVISIONS iterations."""

    async def run(self, state: ResearchState, ctx: Context) -> tuple[Any, Any]:
        """Approve or request revision based on the current revision_count.

        Args:
            state: Current ResearchState snapshot; revision_count determines the outcome.
            ctx: Shared context (not used here).

        Returns:
            (ReviewSignal.approved, patch) when new_count >= _MAX_REVISIONS;
            (ReviewSignal.needs_revision, patch with incremented count) otherwise.
        """
        new_count = state.revision_count + 1
        if new_count >= _MAX_REVISIONS:
            print(f"Review: approving after {new_count} revision(s)")
            return ReviewSignal.approved, ResearchPatch(revision_count=new_count)
        print(f"Review: requesting revision {new_count}")
        return ReviewSignal.needs_revision, ResearchPatch(
            revision_count=new_count,
            review_notes="Need more detail",
        )


class Publish(StateVertex):
    """Assembles and prints the final report from the approved intro and body."""

    async def run(self, state: ResearchState, ctx: Context) -> tuple[Any, Any]:
        """Combine intro and body into final_report and print it.

        Args:
            state: Current ResearchState snapshot; intro and body must be set.
            ctx: Shared context (not used here).

        Returns:
            (StdSignal.ok, ResearchPatch) with final_report assembled.
        """
        report = f"{state.intro}\n{state.body}"
        print(f"\n=== PUBLISHED ===\n{report}\n================")
        return StdSignal.ok, ResearchPatch(final_report=report)


_app = AgentApp(
    doc=__doc__,
    sample_prompts=[
        "Research the impact of large language models on software development.",
        "Write a report on the current state of autonomous agents.",
        "Analyze the trade-offs between BSP and event-driven agent architectures.",
    ],
    context=Context(),
    state_graph=StateGraph(
        start=Research,
        transitions=[
            Transition(Research, StdSignal.ok, Parallel(WriteIntro, WriteBody)),
            Transition(WriteIntro, StdSignal.done, Review),
            Transition(WriteBody, StdSignal.done, Review),
            Transition(Review, ReviewSignal.needs_revision, Research),
            Transition(Review, ReviewSignal.approved, Publish),
            Transition(Publish, StdSignal.ok, StdEnd),
        ],
    ),
    initial_state_factory=lambda q: ResearchState(topic=q) if q else ResearchState(),
)

def _extract_research_result(state: ResearchState) -> str | None:
    if state.final_report:
        return f"Report published: {state.final_report[:50]}..."
    return "Completed."

_app._extract_result = _extract_research_result  # type: ignore[method-assign]

if __name__ == "__main__":
    _app.cli(__doc__, name=__name__)
