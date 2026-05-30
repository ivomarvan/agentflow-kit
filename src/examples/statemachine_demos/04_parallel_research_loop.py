"""Parallel-research-with-loop demo for agentflow.statemachine.

Demonstrates all major statemachine features in a single script:

  - Parallel fan-out  : Research → Parallel(WriteIntro, WriteBody)
  - Fan-in join       : both parallel vertices route to the same Review vertex
  - Cycle / loop      : Review routes back to Research on needs_revision
  - Custom signal enum: ReviewSignal (approved / needs_revision)
  - Loop termination  : auto-approve after _MAX_REVISIONS Research iterations

Run with:
    python src/examples/statemachine_demos/04_parallel_research_loop.py
"""



from dataclasses import dataclass  # noqa: E402
from enum import Enum  # noqa: E402
from typing import Any, cast  # noqa: E402

from agentflow.statemachine import (  # noqa: E402
    Context,
    Parallel,
    StateGraph,
    StateGraphRunner,
    StateVertex,
    StdEnd,
    StdSignal,
    Transition,
)
from agentflow.statemachine.hooks import LoggingHooks  # noqa: E402
from agentflow.statemachine.testing import FakeLlmConnector  # noqa: E402

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

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Reset intro, body and review_notes, then signal fan-out to parallel writers.

        Args:
            state: Current ResearchState snapshot.
            ctx: Shared context (not used here).

        Returns:
            (StdSignal.ok, ResearchPatch) that clears draft fields for this cycle.
        """
        s = cast(ResearchState, state)
        print(f"Research: iteration {s.revision_count + 1}, topic='{s.topic}'")
        return StdSignal.ok, ResearchPatch(intro="", body="", review_notes="")


class WriteIntro(StateVertex):
    """Writes the introduction section of the research report."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Produce a stub introduction and signal completion.

        Args:
            state: Current ResearchState snapshot; topic is read for the intro text.
            ctx: Shared context (not used here).

        Returns:
            (StdSignal.done, ResearchPatch) with intro populated.
        """
        s = cast(ResearchState, state)
        return StdSignal.done, ResearchPatch(intro=f"[Intro for '{s.topic}']")


class WriteBody(StateVertex):
    """Writes the body content of the research report."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Produce a stub body and signal completion.

        Args:
            state: Current ResearchState snapshot; topic is read for the body text.
            ctx: Shared context (not used here).

        Returns:
            (StdSignal.done, ResearchPatch) with body populated.
        """
        s = cast(ResearchState, state)
        return StdSignal.done, ResearchPatch(body=f"[Body for '{s.topic}']")


class Review(StateVertex):
    """Reviews the draft and auto-approves after _MAX_REVISIONS iterations."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Approve or request revision based on the current revision_count.

        Args:
            state: Current ResearchState snapshot; revision_count determines the outcome.
            ctx: Shared context (not used here).

        Returns:
            (ReviewSignal.approved, patch) when new_count >= _MAX_REVISIONS;
            (ReviewSignal.needs_revision, patch with incremented count) otherwise.
        """
        s = cast(ResearchState, state)
        new_count = s.revision_count + 1
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

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Combine intro and body into final_report and print it.

        Args:
            state: Current ResearchState snapshot; intro and body must be set.
            ctx: Shared context (not used here).

        Returns:
            (StdSignal.ok, ResearchPatch) with final_report assembled.
        """
        s = cast(ResearchState, state)
        report = f"{s.intro}\n{s.body}"
        print(f"\n=== PUBLISHED ===\n{report}\n================")
        return StdSignal.ok, ResearchPatch(final_report=report)


def build_graph() -> StateGraph:
    """Construct the parallel-research-with-loop StateGraph.

    Topology::

        Research --ok--> Parallel(WriteIntro, WriteBody)
        WriteIntro --done--> Review
        WriteBody  --done--> Review        (fan-in: both arrive at Review)
        Review --needs_revision--> Research  (cycle)
        Review --approved--> Publish
        Publish --ok--> StdEnd

    Returns:
        Fully wired StateGraph ready for StateGraphRunner.
    """
    return StateGraph(
        start=Research,
        transitions=[
            Transition(Research, StdSignal.ok, Parallel(WriteIntro, WriteBody)),
            Transition(WriteIntro, StdSignal.done, Review),
            Transition(WriteBody, StdSignal.done, Review),
            Transition(Review, ReviewSignal.needs_revision, Research),
            Transition(Review, ReviewSignal.approved, Publish),
            Transition(Publish, StdSignal.ok, StdEnd),
        ],
    )


def run_demo() -> ResearchState:
    """Build the graph and run it synchronously to completion.

    Uses FakeLlmConnector so no real LLM calls are made.

    Returns:
        Final ResearchState after StdEnd is reached; final_report is populated
        and revision_count equals _MAX_REVISIONS.
    """
    connector = FakeLlmConnector()
    ctx = Context(connector=connector)
    hooks = LoggingHooks()

    graph = build_graph()
    runner = StateGraphRunner(graph=graph, context=ctx, hooks=hooks)

    result = runner.run_sync(ResearchState())
    return cast(ResearchState, result)


if __name__ == "__main__":
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s — %(message)s",
    )

    final_state = run_demo()

    print(f"\nFinal revision_count: {final_state.revision_count}")
    print("Done!")
