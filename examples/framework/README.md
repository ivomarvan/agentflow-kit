# examples/framework — State machine mechanics

Each script demonstrates one orthogonal framework feature without requiring a real LLM.

| File | What it shows | LLM? |
|------|---------------|------|
| `01_hello_state_machine.py` | Minimal `StateGraph`: 2 vertices, pure Python | None |
| `02_parallel_and_loop.py` | `Parallel` fan-out/fan-in + review loop | `FakeLlmConnector` |
| `03_live_graph.py` | `LiveGraphHooks` — DOT snapshot per super-step | `FakeLlmConnector` |
| `04_checkpoint_resume.py` | Pause / resume with `InMemoryCheckpointStore` | `FakeLlmConnector` |

## Running

```bash
uv run python examples/framework/01_hello_state_machine.py run
uv run python examples/framework/02_parallel_and_loop.py graph --browser
uv run python examples/framework/03_live_graph.py run    # saves DOT files to nogit_data/graphs/
uv run python examples/framework/04_checkpoint_resume.py run
```

## Concepts illustrated

**Pure state machine (01):** `StateGraph`, `StateVertex`, `StdSignal`, `Context`.
The simplest possible runnable graph — no LLM, no tools.

**Parallel fan-out/fan-in (02):** `Parallel(WriteIntro, WriteBody)` — both vertices run in the
same super-step and their patches are merged. Review loops back until approved.

**Live graph (03):** `LiveGraphHooks` records which vertices are active at each super-step and
`GraphRenderer.to_dot()` saves a DOT file per step for offline inspection or animation.

**Checkpoint / pause / resume (04):** `run_until()` pauses execution when a predicate matches,
saves state to `InMemoryCheckpointStore`, and `resume()` continues from that snapshot.
This is the foundation for human-in-the-loop and long-running workflows.
