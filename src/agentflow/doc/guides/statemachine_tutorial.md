# StateGraph Tutorial: From First Graph to Parallel Research Agent

This tutorial walks through building state graphs with `agentflow.statemachine` —
from a two-node Hello World to parallel fan-out, routing, loops, LLM integration,
observability, visualization, and checkpointing.

## 1. Setup and Prerequisites

The library lives inside the `ai_agents_education` repository. Install dependencies
with `uv sync` from the project root. Every script starts with `git_root_to_syspath`
so imports work regardless of the working directory. You need Python 3.11+.

```python
from git_root_to_syspath import agr
PROJECT_ROOT = agr()

from src.agentflow.statemachine import StateGraph, StateGraphRunner, Context
from src.agentflow.statemachine.testing import FakeLlmConnector
```

For development and tests, use `FakeLlmConnector` — it queues canned responses and
requires no API key. Replace it with `LlmConnector.create(LlmConfig.from_env())`
when connecting to a real backend.

## 2. Your First Graph — Hello World

A graph needs three pieces: a frozen state dataclass, vertex classes, and transitions.
Each vertex implements `async def run(state, ctx)` and returns `(signal, patch)`.
Wire two nodes linearly and run with `StateGraphRunner`.

```python
from dataclasses import dataclass
from src.agentflow.statemachine import (
    Context, StateGraph, StateGraphRunner, StateVertex,
    StdEnd, StdSignal, Transition,
)

@dataclass(frozen=True)
class HelloState:
    message: str = ""

@dataclass
class HelloPatch:
    message: str | None = None

class Greet(StateVertex):
    async def run(self, state, ctx):
        return StdSignal.ok, HelloPatch(message="Hello, World!")

graph = StateGraph(
    start=Greet,
    transitions=[Transition(Greet, StdSignal.ok, StdEnd)],
)
ctx = Context(connector=FakeLlmConnector())
final = StateGraphRunner(graph, ctx).run_sync(HelloState())
print(final.message)  # Hello, World!
```

## 3. State with Field Reducers

When parallel vertices write the same field, annotate it with a reducer function.
Without a reducer, the last patch wins (and a warning is logged). Use `operator.add`
for tuples or a custom append function for lists.

```python
import operator
from dataclasses import dataclass, field
from typing import Annotated

def list_append(acc: list[str], new: list[str]) -> list[str]:
    return acc + new

@dataclass(frozen=True)
class LogState:
    entries: Annotated[list[str], list_append] = field(default_factory=list)

@dataclass
class LogPatch:
    entries: list[str] | None = None

# Two parallel vertices both return LogPatch(entries=["msg-a"]) and
# LogPatch(entries=["msg-b"]) — reducer merges them into ["msg-a", "msg-b"].
```

For tuple accumulation (common in demos), `Annotated[tuple[str, ...], operator.add]`
works the same way — each patch appends its tuple fragment.

## 4. Routing with Signals

Define a domain Enum for routing decisions. A router vertex inspects state and returns
one signal; `Transition` objects map each signal to a different target vertex.

```python
from enum import Enum, auto

class ReviewSignal(Enum):
    approved = auto()
    needs_revision = auto()

class Review(StateVertex):
    async def run(self, state, ctx):
        if state.revision_count >= 2:
            return ReviewSignal.approved, MyPatch()
        return ReviewSignal.needs_revision, MyPatch(revision_count=state.revision_count + 1)

transitions = [
    Transition(Review, ReviewSignal.approved, Publish),
    Transition(Review, ReviewSignal.needs_revision, Research),
]
```

Use `StdSignal.ok`, `StdSignal.fail`, and `StdSignal.done` when domain-specific
signals are not needed.

## 5. Parallel Fan-out and Fan-in

Wrap multiple targets in `Parallel(A, B)` to activate both vertices in the same
super-step. Each branch runs independently; patches merge via reducers. Both branches
route to the same join vertex — fan-in is implicit (set-based join).

```python
from src.agentflow.statemachine import Parallel

graph = StateGraph(
    start=Research,
    transitions=[
        Transition(Research, StdSignal.ok, Parallel(WriteIntro, WriteBody)),
        Transition(WriteIntro, StdSignal.done, Review),
        Transition(WriteBody, StdSignal.done, Review),
    ],
)
```

In super-step 1, `Research` runs alone. In super-step 2, `WriteIntro` and `WriteBody`
run in parallel. In super-step 3, `Review` receives the merged state from both writers.

## 6. Cycles (Loops)

Route a signal back to an earlier vertex to create a cycle. Always include a termination
condition in state (e.g. a revision counter) so the loop cannot run forever.

```python
class Review(StateVertex):
    async def run(self, state, ctx):
        new_count = state.revision_count + 1
        if new_count >= MAX_REVISIONS:
            return ReviewSignal.approved, ResearchPatch(revision_count=new_count)
        return ReviewSignal.needs_revision, ResearchPatch(
            revision_count=new_count,
            review_notes="Need more detail",
        )

# Cycle edge:
Transition(Review, ReviewSignal.needs_revision, Research),
Transition(Review, ReviewSignal.approved, Publish),
```

The `Research` vertex resets draft fields at the start of each iteration so stale
content from the previous cycle does not leak into the next one.

## 7. Integration: ToolCallVertex, LlmTurnVertex, ToolAgentVertex

Adapter vertices wrap existing agentflow components as graph nodes — no subclassing needed.

**ToolCallVertex** — execute one tool call per super-step:

```python
from src.agentflow.statemachine import ToolCallVertex
from src.agentflow.tools.common_tools.Calculator import Calculator

calc_vertex = ToolCallVertex(
    tool=Calculator(),
    args_from_state=lambda s: {"expression": s.expression},
    result_to_patch=lambda result: MyPatch(calc_result=result),
)
```

**LlmTurnVertex** — one LLM chat turn (no built-in ReAct loop):

```python
from src.agentflow.statemachine import LlmTurnVertex

llm_vertex = LlmTurnVertex(
    messages_from_state=lambda s: [{"role": "user", "content": s.prompt}],
    response_to_patch=lambda resp: MyPatch(answer=resp.text),
)
```

**ToolAgentVertex** — wrap a full `ToolAgent` ReAct loop as a single atomic step:

```python
from src.agentflow.statemachine import ToolAgentVertex

agent_vertex = ToolAgentVertex(
    agent=my_tool_agent,
    question_from_state=lambda s: s.question,
    answer_to_patch=lambda ans: MyPatch(answer=ans),
)
```

## 8. Observability: RecorderHooks and LiveGraphHooks

Pass hooks to `StateGraphRunner` to observe execution. `RecorderHooks` captures the
full history of every super-step — useful for test assertions.

```python
from src.agentflow.statemachine import RecorderHooks

recorder = RecorderHooks()
runner = StateGraphRunner(graph, ctx, hooks=recorder)
final = runner.run_sync(initial)

for record in recorder.history:
    print(f"Step {record.step}: active={[type(n).__name__ for n in record.active_nodes]}")
    print(f"  state_after={record.state_after}")
```

`LiveGraphHooks` records which node class names were active at each step. Call
`hooks.get_snapshot_graph(graph, step)` to get a topology graph with active nodes
marked — pass it to `GraphRenderer.to_dot()` for visual output.

## 9. Graph Visualization

`StateGraph` inherits from `Describable` and provides `get_graph_html()`. The returned
string is a standalone HTML page with an interactive graph — save it and open in a browser.

```python
from pathlib import Path

html = graph.get_graph_html(title="Research Agent Topology")
output = Path("nogit_data/graphs/topology.html")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(html, encoding="utf-8")
print(f"Saved to {output}")
```

For step-by-step animated snapshots during a run, combine `LiveGraphHooks` with
`GraphRenderer.to_dot()` — see `03_live_graph_demo.py`.

## 10. Checkpointing & Human-in-the-Loop

Checkpointing saves state after each super-step so execution can pause and resume.
Use `InMemoryCheckpointStore` for tests; `JsonFileCheckpointStore` persists to disk.

`run_until()` runs the BSP loop and stops when a predicate returns `True` (e.g. before
a human-review vertex). `resume()` loads a saved checkpoint and continues.

```python
import asyncio
from src.agentflow.statemachine.checkpoint import InMemoryCheckpointStore

store = InMemoryCheckpointStore()
runner = StateGraphRunner(graph, ctx)

async def pause_before_review():
    paused = await runner.run_until(
        ResearchState(),
        predicate=lambda step, state, active: "Review" in [type(n).__name__ for n in active],
        store=store,
        run_id=ctx.run_id,
    )
    # Human inspects paused state, optionally modifies it, then resumes:
    final = await runner.resume(store, ctx.run_id, from_step=2)
    return final

result = asyncio.run(pause_before_review())
print(result.final_report)
```

Each saved `CheckpointRecord` contains `run_id`, `step`, the frozen state snapshot,
and `active_node_names` for the next super-step. This enables human approval workflows
where an operator reviews or edits state between automated phases.
