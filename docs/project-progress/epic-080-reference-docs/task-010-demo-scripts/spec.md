# Task T010 — Parallel-Research-with-Loop Demo

**Epic:** E080 — Reference Examples & Documentation
**Task:** T010

## Goal

Create the "parallel research with loop" demo — the key reference example that shows
all major statemachine features in one script: parallel fan-out, fan-in join, cycle.

## Files to read FIRST

1. `src/examples/statemachine_demos/01_brief_example.py` — existing parallel graph (no loop)
2. `src/agentflow/statemachine/__init__.py` — full public API
3. `src/agentflow/statemachine/signal.py` — StdSignal, EnumSignal pattern

## Deliverable

`src/examples/statemachine_demos/04_parallel_research_loop.py`

**Note:** E070 also creates a file named `04_...`. If the E070 demo was already created,
name this one `05_parallel_research_loop.py` instead (check what files exist in
`src/examples/statemachine_demos/` first).

## Graph design

```
Research
   │ ok (fan-out)
   ├──────────────┐
WriteIntro     WriteBody
   │               │
   └──────┬────────┘
          │ done (fan-in join — implicit via same signal)
        Review ──── approved ──→ Publish → StdEnd
          │
       needs_revision
          │
          └──→ Research  (cycle — max 2 revisions, then auto-approve)
```

### Custom signal enum

```python
from enum import Enum
from agentflow.statemachine import EnumSignal

class ReviewSignal(Enum):  # EnumSignal = type alias for Enum
    approved = "approved"
    needs_revision = "needs_revision"
```

### State

```python
@dataclass(frozen=True)
class ResearchState:
    topic: str = "BSP execution model"
    intro: str = ""
    body: str = ""
    review_notes: str = ""
    revision_count: int = 0
    final_report: str = ""
```

Use `Annotated[int, lambda a, b: b]` for `revision_count` (last-writer-wins).
Use `Annotated[str, lambda a, b: a + b]` for `intro` and `body` (concatenate in parallel).

### Vertex logic

- `Research`: returns `StdSignal.ok`, patch with `intro=""`, `body=""`, `review_notes=""`
  (reset for new iteration), prints revision count.
- `WriteIntro`: returns `StdSignal.done`, patch with `intro="Intro #{revision_count}"`
- `WriteBody`: returns `StdSignal.done`, patch with `body="Body #{revision_count}"`
- `Review`: if `state.revision_count >= 2` → `ReviewSignal.approved`, else `ReviewSignal.needs_revision`,
  patch with `revision_count=state.revision_count+1`, `review_notes="Revision needed"`
- `Publish`: returns `StdSignal.ok`, patch with `final_report=f"{state.intro}\n{state.body}"`, prints result.

### Transitions

```python
from agentflow.statemachine import Transition, Parallel, StateGraph, StdSignal

graph = StateGraph(
    start=Research,
    transitions=[
        Transition(Research, StdSignal.ok, Parallel(WriteIntro, WriteBody)),
        Transition(WriteIntro, StdSignal.done, Review),
        Transition(WriteBody, StdSignal.done, Review),
        Transition(Review, ReviewSignal.approved, Publish),
        Transition(Review, ReviewSignal.needs_revision, Research),  # cycle!
        Transition(Publish, StdSignal.ok, StdEnd),
    ],
)
```

## Code quality

```bash
cd /home/ivo/workspace/git.hub.lab.ivo/ai_agents_education
uv run ruff check src/examples/statemachine_demos/
uv run mypy --strict --follow-imports=skip src/examples/statemachine_demos/04_parallel_research_loop.py
python src/examples/statemachine_demos/04_parallel_research_loop.py
```

Demo must terminate (loop breaks after revision_count >= 2) and print the final report.
