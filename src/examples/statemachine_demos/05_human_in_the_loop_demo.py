"""Human-in-the-loop pause/resume demo for agentflow.statemachine.

Demonstrates the checkpointing workflow:
  Draft → (pause — human reviews) → HumanReview → Publish → StdEnd

The graph is paused before HumanReview executes via run_until().
A simulated human updates the state (approved=True) and saves it back to
the checkpoint store.  resume() then picks up from that checkpoint and
completes the workflow.

Run with:
    python src/examples/statemachine_demos/05_human_in_the_loop_demo.py
"""

from git_root_to_syspath import agr  # locate project root and add it to sys.path

PROJECT_ROOT = agr()

import asyncio  # noqa: E402
import dataclasses  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from typing import Any  # noqa: E402

from src.agentflow.statemachine import (  # noqa: E402
    CheckpointRecord,
    InMemoryCheckpointStore,
    StateGraph,
    StateGraphRunner,
    StateVertex,
    StdEnd,
    StdSignal,
    Transition,
)
from src.agentflow.statemachine.context import Context  # noqa: E402
from src.agentflow.statemachine.testing import make_fake_context  # noqa: E402


@dataclass(frozen=True)
class ReviewState:
    """Workflow state for the human-review pipeline."""

    topic: str = "AI Agents"
    draft: str = ""
    approved: bool = False


class Draft(StateVertex):
    """Generates a draft document for the given topic."""

    async def run(self, state: ReviewState, ctx: Context) -> tuple[Any, Any]:
        """Produce a draft and patch it into state.

        Args:
            state: Current workflow state.
            ctx: Shared context (unused in this demo).

        Returns:
            (StdSignal.ok, updated state with draft text).
        """
        draft_text = (
            f"Draft about '{state.topic}': AI agents are autonomous systems "
            "that perceive their environment and take actions to achieve goals."
        )
        print(f"[Draft] Created draft ({len(draft_text)} chars)")
        print(f"[Draft] Preview: {draft_text[:60]}...")
        return StdSignal.ok, dataclasses.replace(state, draft=draft_text)


class HumanReview(StateVertex):
    """Validates human approval before allowing publication."""

    async def run(self, state: ReviewState, ctx: Context) -> tuple[Any, Any]:
        """Check approval flag set by the human reviewer.

        Args:
            state: Current workflow state; approved=True means human signed off.
            ctx: Shared context (unused in this demo).

        Returns:
            (StdSignal.ok, unchanged state).
        """
        if state.approved:
            print("[HumanReview] Human approved the draft — proceeding to publish.")
        else:
            print("[HumanReview] WARNING: draft not approved — publishing anyway (demo).")
        return StdSignal.ok, state


class Publish(StateVertex):
    """Publishes the approved draft."""

    async def run(self, state: ReviewState, ctx: Context) -> tuple[Any, Any]:
        """Emit the draft as published content.

        Args:
            state: Current workflow state with populated draft.
            ctx: Shared context (unused in this demo).

        Returns:
            (StdSignal.ok, unchanged state).
        """
        print(f"[Publish] Published: {state.draft[:80]}...")
        return StdSignal.ok, state


_GRAPH = StateGraph(
    start=Draft,
    transitions=[
        Transition(Draft, StdSignal.ok, HumanReview),
        Transition(HumanReview, StdSignal.ok, Publish),
        Transition(Publish, StdSignal.ok, StdEnd),
    ],
)


async def main() -> None:
    """Run the human-in-the-loop pause/resume workflow end-to-end."""
    context = make_fake_context()
    runner = StateGraphRunner(_GRAPH, context)
    store = InMemoryCheckpointStore()
    run_id = "review-demo-1"

    print("=" * 60)
    print("Phase 1: Run until HumanReview becomes the active node")
    print("=" * 60)

    paused_state: ReviewState = await runner.run_until(
        ReviewState(topic="AI Agents in Production"),
        predicate=lambda step, state, active: any(
            type(n).__name__ == "HumanReview" for n in active
        ),
        store=store,
        run_id=run_id,
    )

    steps = await store.list_steps(run_id)
    last_step = steps[-1] if steps else 1
    print(f"\nPaused after step {last_step}. Waiting for human review.")
    print(f"Draft preview: {paused_state.draft[:60]}...")

    print("\n[Human] Reviewing draft and approving...")
    approved_state = dataclasses.replace(paused_state, approved=True)

    # Overwrite the checkpoint with the human-approved state so that resume()
    # picks it up and HumanReview sees approved=True.
    await store.save(
        CheckpointRecord(
            run_id=run_id,
            step=last_step,
            state=approved_state,
            active_node_names=["HumanReview"],
        )
    )
    print("[Human] Approval saved to checkpoint store.")

    print("\n" + "=" * 60)
    print("Phase 2: Resume from checkpoint")
    print("=" * 60)

    final_state: ReviewState = await runner.resume(store, run_id, from_step=last_step)

    print(f"\nWorkflow complete. approved={final_state.approved}")


if __name__ == "__main__":
    asyncio.run(main())
