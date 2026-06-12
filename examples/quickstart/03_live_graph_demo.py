"""Live graph snapshot demo — §2.5 graph with LiveGraphHooks.

Builds the Research → Parallel(WriteIntro, WriteBody) → Review → StdEnd graph
using FakeVertex subclasses, runs it with LiveGraphHooks, and saves one DOT
snapshot per super-step to nogit_data/graphs/step_N.dot.
"""

# Run:
#     uv run python examples/quickstart/03_live_graph_demo.py -h           # help
#     uv run python examples/quickstart/03_live_graph_demo.py run        # run workflow
#     uv run python examples/quickstart/03_live_graph_demo.py graph --browser
#     uv run python examples/quickstart/03_live_graph_demo.py graph -o graph.html

import operator
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Annotated, Any

from agentflow import AgentApp
from agentflow.describable.graph_renderer import GraphRenderer
from agentflow.statemachine import (
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
from agentflow.statemachine.testing.fakes import FakeLlmConnector

# Project root resolved relative to this file (examples/quickstart/ → project root).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


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


_connector = FakeLlmConnector()
_graph = StateGraph(
    start=Research,
    transitions=[
        Transition(Research, DemoSignal.ok, Parallel(WriteIntro, WriteBody)),
        Transition(WriteIntro, StdSignal.done, Review),
        Transition(WriteBody, StdSignal.done, Review),
        Transition(Review, DemoSignal.approved, StdEnd),
    ],
)

_app = AgentApp(
    doc=__doc__,
    context=Context(),
    state_graph=_graph,
    initial_state_factory=lambda _q: DemoState(),
)


async def _live_graph_run_workflow(self: AgentApp) -> str | None:
    """Run the demo graph and save DOT snapshots for each super-step."""
    ctx = Context(llm_connectors={"default": _connector})
    hooks = LiveGraphHooks()
    runner = StateGraphRunner(graph=self._state_graph, context=ctx, hooks=hooks)
    await runner.run(DemoState())

    output_dir = _PROJECT_ROOT / "nogit_data" / "graphs"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n--- Live Graph Demo: {len(hooks.snapshots)} super-steps recorded ---")
    for i, (step_num, active_names) in enumerate(hooks.snapshots, start=1):
        snapshot = hooks.get_snapshot_graph(self._state_graph, i)
        dot_src = GraphRenderer.to_dot(snapshot)
        dot_path = output_dir / f"step_{i}.dot"
        dot_path.write_text(dot_src, encoding="utf-8")
        print(f"  Step {step_num}: active={sorted(active_names)} → saved {dot_path}")

    print("\nDOT files saved to:", output_dir)
    return None


_app.run_workflow = _live_graph_run_workflow.__get__(_app, AgentApp)  # type: ignore[method-assign]

if __name__ == "__main__":
    _app.cli(__doc__, name=__name__)
