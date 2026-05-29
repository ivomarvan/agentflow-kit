# Task T030 — Human-in-the-Loop Demo

**Epic:** E070 — Checkpointing & Pause/Resume
**Task:** T030

## Goal

Create a runnable end-to-end demo showing the pause/resume workflow with simulated
human approval using `run_until()` and `resume()`.

## Files to read FIRST

1. `src/agentflow/statemachine/checkpoint.py` — T020 output
2. `src/agentflow/statemachine/runner.py` — T020 output (run_until + resume)
3. `src/examples/statemachine_demos/01_brief_example.py` — demo structure reference
4. `src/agentflow/statemachine/testing/fakes.py` — FakeVertex

## Deliverable

`src/examples/statemachine_demos/04_human_in_the_loop_demo.py`

## Demo design

### State

```python
@dataclass(frozen=True)
class ReviewState:
    topic: str = "AI Agents"
    draft: str = ""
    approved: bool = False
```

### Graph

```
Draft → HumanReview (pause here!) → Publish → StdEnd
```

- `Draft` vertex: returns `StdSignal.ok` + patch `draft="Draft text about {topic}"`
- `HumanReview` vertex: in a real scenario this would pause; here it uses `run_until` to pause before it runs, and the "human" approves by modifying state before `resume()`
- `Publish` vertex: prints "Published: {state.draft}" and returns ok

### Workflow

```python
# 1. Run until HumanReview is in active nodes
store = InMemoryCheckpointStore()
run_id = "demo-run-1"
paused_state = await runner.run_until(
    initial_state,
    predicate=lambda step, state, active: any(
        type(n).__name__ == "HumanReview" for n in active
    ),
    store=store,
    run_id=run_id,
)
print(f"PAUSED at step {last_step}. Draft: {paused_state.draft}")
print("Human reviews and approves...")

# 2. Simulate human modifying state (approve)
approved_state = dataclasses.replace(paused_state, approved=True)

# 3. Save modified state as checkpoint for the resume step
# (need to update the checkpoint with the approved state)
await store.save(CheckpointRecord(run_id, last_step, approved_state, ["HumanReview"]))

# 4. Resume
final_state = await runner.resume(store, run_id, from_step=last_step)
print(f"COMPLETED. Final state: {final_state}")
```

The demo must:
1. Print the topic and draft at pause.
2. Print "Human approved!" when simulating approval.
3. Print the published text at the end.
4. Use `asyncio.run()` as entry point.
5. Exit with code 0.

## Code quality

```bash
cd /home/ivo/workspace/git.hub.lab.ivo/ai_agents_education
uv run ruff check src/examples/statemachine_demos/04_human_in_the_loop_demo.py
python src/examples/statemachine_demos/04_human_in_the_loop_demo.py
```
