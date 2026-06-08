"""End-to-end demo of the brief §2.5 state graph.

Demonstrates the full agentflow.statemachine MVP:
  Research → Parallel(WriteIntro, WriteBody) → Review → (loop | StdEnd)

Run with:
    uv run python examples/quickstart/01_brief_example.py -h           # help
    uv run python examples/quickstart/01_brief_example.py run         # run workflow
    uv run python examples/quickstart/01_brief_example.py graph --browser
    uv run python examples/quickstart/01_brief_example.py graph -o graph.html

The graph cycles until Review approves — after APPROVE_AFTER rejections.
FakeLlmConnector is used so no real LLM calls are made.
"""

import operator
from dataclasses import dataclass
from enum import Enum, auto
from typing import Annotated, Any

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

    async def run(self, state: DemoState, ctx: Context) -> tuple[Any, Any]:
        """Produce a research-completed message and route with ok.

        Args:
            state: Current DemoState snapshot.
            ctx: Shared context (FakeLlmConnector; not called here).

        Returns:
            Tuple (CustomSignal.ok, DemoPatch with research message).
        """
        patch = DemoPatch(messages=(f"Research completed (cycle={state.iteration}).",))
        return CustomSignal.ok, patch


class WriteIntro(StateVertex):
    """Simulates writing the introduction section."""

    async def run(self, state: DemoState, ctx: Context) -> tuple[Any, Any]:
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

    async def run(self, state: DemoState, ctx: Context) -> tuple[Any, Any]:
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

    async def run(self, state: DemoState, ctx: Context) -> tuple[Any, Any]:
        """Approve or reject based on how many cycles have occurred.

        Args:
            state: Current DemoState snapshot; iteration is read to decide.
            ctx: Shared context (unused).

        Returns:
            (CustomSignal.approved, patch) when iteration >= _APPROVE_AFTER;
            (CustomSignal.rejected, patch with incremented iteration) otherwise.
        """
        if state.iteration >= _APPROVE_AFTER:
            patch = DemoPatch(messages=("Review: content approved.",))
            return CustomSignal.approved, patch

        new_iter = state.iteration + 1
        patch = DemoPatch(
            messages=(f"Review: rejected — revision {new_iter} requested.",),
            iteration=new_iter,
        )
        return CustomSignal.rejected, patch


_connector = FakeLlmConnector()

_app = AgentApp(
    doc=__doc__,
    sample_prompts=[
        "Write a short essay about the benefits of AI.",
        "Summarize the history of machine learning.",
        "Explain the BSP execution model in 3 sentences.",
    ],
    context=Context(),
    state_graph=StateGraph(
        start=Research,
        transitions=[
            Transition(Research, CustomSignal.ok, Parallel(WriteIntro, WriteBody)),
            Transition(WriteIntro, StdSignal.done, Review),
            Transition(WriteBody, StdSignal.done, Review),
            Transition(Review, CustomSignal.rejected, Research),
            Transition(Review, CustomSignal.approved, StdEnd),
        ],
    ),
    initial_state_factory=lambda _q: DemoState(),
)

_app._extract_result = (  # type: ignore[method-assign]
    lambda state: f"Completed {state.iteration + 1} cycles."
)
_app.connector = _connector  # backward compat for e2e tests


def BriefExampleApp() -> AgentApp:
    """Backward-compatible factory returning the module-level app instance."""
    return _app


if __name__ == "__main__":
    _app.cli(__doc__, name=__name__)
