"""End-to-end demo of the brief §2.5 state graph.

Demonstrates the full agentflow.statemachine MVP:
  Research → Parallel(WriteIntro, WriteBody) → Review → (loop | StdEnd)

Run with:
    uv run python examples/quickstart/01_brief_example.py              # run workflow
    uv run python examples/quickstart/01_brief_example.py -h           # help
    uv run python examples/quickstart/01_brief_example.py browser      # graph in browser
    uv run python examples/quickstart/01_brief_example.py graph-html   # save HTML graph

The graph cycles until Review approves — after APPROVE_AFTER rejections.
FakeLlmConnector is used so no real LLM calls are made.
"""

import logging
import operator
from dataclasses import dataclass
from enum import Enum, auto
from typing import Annotated, Any, cast

from agentflow import AgentApp
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

# How many review rejections must occur before the graph terminates.
_APPROVE_AFTER: int = 2


@dataclass(frozen=True)
class DemoState:
    """Immutable state for the §2.5 demo graph.

    Attributes:
        messages: Accumulated log of vertex activity; uses operator.add reducer
                  so parallel vertices append rather than overwrite each other.
        iteration: Number of completed review cycles (0-based).
    """

    messages: Annotated[tuple[str, ...], operator.add] = ()
    iteration: int = 0


@dataclass
class DemoPatch:
    """Mutable patch applied to DemoState after each super-step.

    Fields default to None to signal "no change" to apply_patches().

    Attributes:
        messages: Tuple of new messages to append via the reducer.
        iteration: New iteration count; None means leave unchanged.
    """

    messages: tuple[str, ...] | None = None
    iteration: int | None = None


class CustomSignal(Enum):
    """Domain-specific routing signals for the §2.5 demo graph."""

    ok = auto()
    approved = auto()
    rejected = auto()


class Research(StateVertex):
    """Simulates a research phase — always succeeds with CustomSignal.ok."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Produce a research-completed message and route with ok.

        Args:
            state: Current DemoState snapshot.
            ctx: Shared context (FakeLlmConnector; not called here).

        Returns:
            Tuple (CustomSignal.ok, DemoPatch with research message).
        """
        s = cast(DemoState, state)
        patch = DemoPatch(messages=(f"Research completed (cycle={s.iteration}).",))
        return CustomSignal.ok, patch


class WriteIntro(StateVertex):
    """Simulates writing the introduction section."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Append an intro-written message and signal done.

        Args:
            state: Current DemoState snapshot (unused).
            ctx: Shared context (unused).

        Returns:
            Tuple (StdSignal.done, DemoPatch with intro message).
        """
        patch = DemoPatch(messages=("Introduction written.",))
        return StdSignal.done, patch


class WriteBody(StateVertex):
    """Simulates writing the body content."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Append a body-written message and signal done.

        Args:
            state: Current DemoState snapshot (unused).
            ctx: Shared context (unused).

        Returns:
            Tuple (StdSignal.done, DemoPatch with body message).
        """
        patch = DemoPatch(messages=("Body written.",))
        return StdSignal.done, patch


class Review(StateVertex):
    """Reviews content and approves after _APPROVE_AFTER rejections.

    Reads state.iteration: if >= _APPROVE_AFTER, returns approved;
    otherwise increments iteration and returns rejected to trigger a loop.
    """

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Approve or reject based on how many cycles have occurred.

        Args:
            state: Current DemoState snapshot; iteration is read to decide.
            ctx: Shared context (unused).

        Returns:
            (CustomSignal.approved, patch) when iteration >= _APPROVE_AFTER;
            (CustomSignal.rejected, patch with incremented iteration) otherwise.
        """
        s = cast(DemoState, state)
        if s.iteration >= _APPROVE_AFTER:
            patch = DemoPatch(messages=("Review: content approved.",))
            return CustomSignal.approved, patch

        new_iter = s.iteration + 1
        patch = DemoPatch(
            messages=(f"Review: rejected — revision {new_iter} requested.",),
            iteration=new_iter,
        )
        return CustomSignal.rejected, patch


class BriefExampleApp(AgentApp):
    """Demonstrates the §2.5 Research→Parallel→Review loop with FakeLlmConnector."""

    def __init__(self) -> None:
        super().__init__()
        self.connector = FakeLlmConnector()
        self.graph = StateGraph(
            start=Research,
            transitions=[
                Transition(Research, CustomSignal.ok, Parallel(WriteIntro, WriteBody)),
                Transition(WriteIntro, StdSignal.done, Review),
                Transition(WriteBody, StdSignal.done, Review),
                Transition(Review, CustomSignal.rejected, Research),
                Transition(Review, CustomSignal.approved, StdEnd),
            ],
        )

    @property
    def sample_prompts(self) -> list[str]:
        """Return example prompts for the GUI prompt selector."""
        return [
            "Write a short essay about the benefits of AI.",
            "Summarize the history of machine learning.",
            "Explain the BSP execution model in 3 sentences.",
        ]

    async def run_workflow(self) -> str | None:
        """Run the §2.5 demo graph to completion and print the summary."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s %(name)s — %(message)s",
        )

        ctx = Context(connector=self.connector)
        hooks = LoggingHooks()
        runner = StateGraphRunner(graph=self.graph, context=ctx, hooks=hooks)
        final_state = cast(DemoState, await runner.run(DemoState()))

        print("\n--- Demo Complete ---")
        print(f"Total cycles:  {final_state.iteration + 1}")
        print(f"Messages ({len(final_state.messages)}):")
        for msg in final_state.messages:
            print(f"  · {msg}")
        return f"Completed {final_state.iteration + 1} cycles."


if __name__ == "__main__":
    BriefExampleApp().cli(__doc__, name=__name__)
