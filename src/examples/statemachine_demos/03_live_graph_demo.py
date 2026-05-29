"""Live graph snapshot demo — §2.5 graph with LiveGraphHooks.

Builds the Research → Parallel(WriteIntro, WriteBody) → Review → StdEnd graph
using FakeVertex subclasses, runs it with LiveGraphHooks, and saves one DOT
snapshot per super-step to nogit_data/graphs/step_N.dot.

Run with:
    python src/examples/statemachine_demos/03_live_graph_demo.py
"""

from pathlib import Path

from git_root_to_syspath import agr  # locate project root and add it to sys.path

PROJECT_ROOT = Path(agr())

import operator  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from enum import Enum, auto  # noqa: E402
from typing import Annotated, Any  # noqa: E402

from src.agentflow.describable.graph_renderer import GraphRenderer  # noqa: E402
from src.agentflow.statemachine import (  # noqa: E402
    Context,
    LiveGraphHooks,
    Parallel,
    StateGraph,
    StateGraphRunner,
    StateVertex,
    StdEnd,
    StdSignal,
    Transition,
)
from src.agentflow.statemachine.testing.fakes import FakeLlmConnector  # noqa: E402


@dataclass(frozen=True)
class DemoState:
    """Immutable state for the live-graph demo.

    Attributes:
        messages: Accumulated activity log; uses operator.add reducer.
    """

    messages: Annotated[tuple[str, ...], operator.add] = ()


@dataclass
class DemoPatch:
    """Mutable patch for DemoState.

    Attributes:
        messages: Tuple of new messages to append via the reducer.
    """

    messages: tuple[str, ...] | None = None


class DemoSignal(Enum):
    """Routing signals for the live-graph demo."""

    ok = auto()
    approved = auto()


# ---------------------------------------------------------------------------
# FakeVertex subclasses — one per node in the §2.5 topology
# ---------------------------------------------------------------------------


class Research(StateVertex):
    """Research phase — always signals ok."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Emit ok signal with a research-done message.

        Args:
            state: Current state snapshot.
            ctx: Shared context (unused).

        Returns:
            (DemoSignal.ok, DemoPatch).
        """
        return DemoSignal.ok, DemoPatch(messages=("Research done.",))


class WriteIntro(StateVertex):
    """Introduction writing — always signals done."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Emit done signal with an intro-written message.

        Args:
            state: Current state snapshot.
            ctx: Shared context (unused).

        Returns:
            (StdSignal.done, DemoPatch).
        """
        return StdSignal.done, DemoPatch(messages=("Introduction written.",))


class WriteBody(StateVertex):
    """Body writing — always signals done."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Emit done signal with a body-written message.

        Args:
            state: Current state snapshot.
            ctx: Shared context (unused).

        Returns:
            (StdSignal.done, DemoPatch).
        """
        return StdSignal.done, DemoPatch(messages=("Body written.",))


class Review(StateVertex):
    """Review phase — always approves on first try for demo simplicity."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Emit approved signal with a review-passed message.

        Args:
            state: Current state snapshot.
            ctx: Shared context (unused).

        Returns:
            (DemoSignal.approved, DemoPatch).
        """
        return DemoSignal.approved, DemoPatch(messages=("Review: approved.",))


def build_graph() -> StateGraph:
    """Construct the §2.5 demo StateGraph.

    Topology:
        Research --ok--> Parallel(WriteIntro, WriteBody)
        WriteIntro --done--> Review
        WriteBody  --done--> Review
        Review --approved--> StdEnd

    Returns:
        Fully wired StateGraph ready for StateGraphRunner.
    """
    return StateGraph(
        start=Research,
        transitions=[
            Transition(Research, DemoSignal.ok, Parallel(WriteIntro, WriteBody)),
            Transition(WriteIntro, StdSignal.done, Review),
            Transition(WriteBody, StdSignal.done, Review),
            Transition(Review, DemoSignal.approved, StdEnd),
        ],
    )


def run_demo() -> None:
    """Run the demo graph and save DOT snapshots for each super-step."""
    connector = FakeLlmConnector()
    ctx = Context(connector=connector)
    hooks = LiveGraphHooks()

    graph = build_graph()
    runner = StateGraphRunner(graph=graph, context=ctx, hooks=hooks)
    runner.run_sync(DemoState())

    output_dir = PROJECT_ROOT / "nogit_data" / "graphs"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n--- Live Graph Demo: {len(hooks.snapshots)} super-steps recorded ---")
    for i, (step_num, active_names) in enumerate(hooks.snapshots, start=1):
        snapshot = hooks.get_snapshot_graph(graph, i)
        dot_src = GraphRenderer.to_dot(snapshot)
        dot_path = output_dir / f"step_{i}.dot"
        dot_path.write_text(dot_src, encoding="utf-8")
        print(f"  Step {step_num}: active={sorted(active_names)} → saved {dot_path}")

    print("\nDOT files saved to:", output_dir)


if __name__ == "__main__":
    run_demo()
