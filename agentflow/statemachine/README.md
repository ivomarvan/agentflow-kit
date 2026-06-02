# agentflow.statemachine

`agentflow.statemachine` is a declarative state-graph orchestration library for AI agents.
You define immutable state (frozen dataclasses), graph nodes (`StateVertex` subclasses),
and routing edges (`Transition` objects keyed by Enum signals). The `StateGraphRunner`
executes the graph using the **Bulk Synchronous Parallel (BSP)** model: each super-step
runs all active vertices in parallel, merges their state patches via per-field reducers,
then routes to the next set of vertices. This barrier semantics makes parallel fan-out
and fan-in predictable without manual locking.

## Quick Start

```python
from dataclasses import dataclass
from agentflow.statemachine import (
    Context, StateGraph, StateGraphRunner, StateVertex,
    StdEnd, StdSignal, Transition,
)
from agentflow.statemachine.testing import FakeLlmConnector

@dataclass(frozen=True)
class HelloState:
    greeting: str = ""

@dataclass
class HelloPatch:
    greeting: str | None = None

class SayHello(StateVertex):
    async def run(self, state: object, ctx: Context) -> tuple[object, object]:
        return StdSignal.ok, HelloPatch(greeting="Hello, statemachine!")

class Finish(StateVertex):
    async def run(self, state: object, ctx: Context) -> tuple[object, object]:
        return StdSignal.done, HelloPatch()

graph = StateGraph(
    start=SayHello,
    transitions=[Transition(SayHello, StdSignal.ok, Finish),
                 Transition(Finish, StdSignal.done, StdEnd)],
)
ctx = Context(connector=FakeLlmConnector())
runner = StateGraphRunner(graph=graph, context=ctx)
final = runner.run_sync(HelloState())
print(final.greeting)  # "Hello, statemachine!"
```

## Core Concepts

### State & StatePatch

State is a **frozen dataclass** — no framework base class required. Each vertex returns
a **StatePatch** (plain dataclass with optional fields defaulting to `None`). Fields set
to `None` or `UNSET` are skipped during merge. For parallel writes to the same field,
annotate the state field with `Annotated[T, reducer]`; the reducer combines contributions
from all patches in one super-step (e.g. `operator.add` for tuples, or a custom append
function for lists). Without a reducer, last-writer-wins applies (with a warning).

### StateVertex

Every graph node inherits from `StateVertex` and implements `async def run(state, ctx)`
returning `(signal, patch)`. The `Context` carries shared services: LLM connector, tool
registry, logger, and `run_id`. Terminal nodes subclass `End` (e.g. `StdEnd`); the runner
stops when all active nodes are `End` instances. Bare vertex **classes** (not instances)
are accepted everywhere — `VertexResolver` auto-instantiates them as singletons per class.

### StateGraph and Transitions

`StateGraph(start, transitions)` holds the topology. Each `Transition(from_node, signal, to_target)`
maps a routing signal to the next target. Targets can be a single vertex or a `Parallel(...)`
fan-out marker that activates all contained vertices in the next super-step. Fan-in happens
implicitly: when multiple branches route to the same vertex, that vertex runs once in the
next super-step (set-based join). `StateGraph` extends `Describable` and provides
`get_graph()`, `get_graph_html()`, and topology query methods used by the runner.

### StateGraphRunner (BSP loop)

`StateGraphRunner` drives the execution loop:

1. **Compute** — run all active non-`End` vertices in parallel (`asyncio.gather`).
2. **Barrier** — gather synchronises all results.
3. **Apply** — merge patches via per-field reducers (`apply_patches`).
4. **Route** — resolve next active vertices from signals and transitions.

The loop repeats until only `End` nodes remain. Use `run_sync()` for scripts and tests;
use `await runner.run()` inside async code. Vertex exceptions map to `StdSignal.fail`
without crashing the super-step.

### Signals

Routing uses **Enum signals**. Define a domain-specific `Enum` subclass (e.g. `ReviewSignal`)
or use `StdSignal` (`ok`, `fail`, `done`). Each vertex's `run()` returns one signal;
`StateGraph.get_targets(node, signal)` resolves matching transitions. Signal matching uses
identity comparison (`is`), so always return the same Enum member instances.

## Public API

| Class / Symbol | Purpose | Import from |
|----------------|---------|-------------|
| `StateVertex` | Abstract base for graph nodes | `src.agentflow.statemachine` |
| `End` | Marker base for terminal nodes | `src.agentflow.statemachine` |
| `StdEnd` | Default terminal node (no-op) | `src.agentflow.statemachine` |
| `Context` | Shared services injected into every vertex (connector, tools, logger, `event_bus`) | `src.agentflow.statemachine` |
| `Transition` | Directed edge: node + signal → target | `src.agentflow.statemachine` |
| `Parallel` | Fan-out marker for parallel branches | `src.agentflow.statemachine` |
| `StateGraph` | Declarative topology + query methods | `src.agentflow.statemachine` |
| `StateGraphRunner` | BSP execution loop | `src.agentflow.statemachine` |
| `VertexResolver` | Singleton-per-class vertex instantiation | `src.agentflow.statemachine` |
| `StdSignal` | Standard routing signals (ok/fail/done) | `src.agentflow.statemachine` |
| `EnumSignal` | Type alias for user-defined Enum signals | `src.agentflow.statemachine` |
| `apply_patches` | Merge StatePatch sequence into state | `src.agentflow.statemachine` |
| `UNSET` | Sentinel: "field not set in this patch" | `src.agentflow.statemachine` |
| `RunnerHooks` | Protocol for observability callbacks | `src.agentflow.statemachine` |
| `NoOpHooks` | Default no-op hooks implementation | `src.agentflow.statemachine` |
| `LoggingHooks` | Structured log output during runs | `src.agentflow.statemachine` |
| `RecorderHooks` | Captures full super-step history | `src.agentflow.statemachine` |
| `SuperStepRecord` | One super-step snapshot for assertions | `src.agentflow.statemachine` |
| `LiveGraphHooks` | Active-node snapshots per super-step | `src.agentflow.statemachine` |
| `ToolCallVertex` | Wraps a single tool call as a node | `src.agentflow.statemachine` |
| `LlmTurnVertex` | Single LLM chat turn as a node | `src.agentflow.statemachine` |
| `ToolAgentVertex` | Wraps a full ToolAgent ReAct loop | `src.agentflow.statemachine` |
| `CheckpointRecord` | Snapshot dataclass for one super-step | `src.agentflow.statemachine.checkpoint` |
| `CheckpointStore` | Protocol for checkpoint persistence | `src.agentflow.statemachine.checkpoint` |
| `InMemoryCheckpointStore` | In-process checkpoint backend | `src.agentflow.statemachine.checkpoint` |

## Cookbook Patterns

### Router

A router vertex inspects state and returns one of several signals; transitions map each
signal to a different target.

```python
class Route(Enum):
    fast = auto()
    slow = auto()

class Router(StateVertex):
    async def run(self, state, ctx):
        signal = Route.fast if state.priority == "high" else Route.slow
        return signal, MyPatch()

transitions = [
    Transition(Router, Route.fast, FastPath),
    Transition(Router, Route.slow, SlowPath),
]
```

### Parallel Fan-out / Fan-in

Use `Parallel(A, B)` as a transition target. Both vertices run in the same super-step;
their patches merge via reducers. Both route to a shared join vertex (fan-in).

```python
Transition(Research, StdSignal.ok, Parallel(WriteIntro, WriteBody)),
Transition(WriteIntro, StdSignal.done, Review),
Transition(WriteBody, StdSignal.done, Review),
```

### Loop (Cycle)

Route a signal back to an earlier vertex. Use a counter in state to bound iterations.

```python
Transition(Review, ReviewSignal.needs_revision, Research),
Transition(Review, ReviewSignal.approved, Publish),
```

### Integration Adapters

Wrap existing agentflow components as graph nodes without rewriting them:

- `ToolCallVertex(tool, args_from_state, result_to_patch)` — one tool invocation.
- `LlmTurnVertex(messages_from_state, response_to_patch)` — one LLM turn.
- `ToolAgentVertex(agent, question_from_state, answer_to_patch)` — full ReAct loop.

### Domain Events

Every `Context` carries an `EventBus` that vertices can use to publish typed domain
events. The bus notifies all registered handlers and maintains a full `history`.

```python
from agentflow import AgentEvent, EventBus, RunCompleteEvent, StepStartEvent

# Emit an event from inside a vertex
async def run(self, state, ctx):
    await ctx.event_bus.emit(StepStartEvent(vertex="Research", step=1, run_id=ctx.run_id))
    # ... do work ...
    return StdSignal.ok, MyPatch()

# Subscribe a custom handler
class WebSocketHandler:
    async def on_event(self, event: AgentEvent) -> None:
        await websocket.send_text(event.model_dump_json())

ctx.event_bus.subscribe(WebSocketHandler())

# Inspect history after the run
for event in ctx.event_bus.history:
    print(event.event_type, event.timestamp)
```

Built-in framework events emitted automatically:

| Event | `event_type` | Payload |
|-------|-------------|---------|
| `StepStartEvent` | `agentflow.step_start` | `vertex`, `step` |
| `StepEndEvent` | `agentflow.step_end` | `vertex`, `step`, `signal` |
| `LogEvent` | `agentflow.log` | `level`, `message`, `logger_name` |
| `RunCompleteEvent` | `agentflow.run_complete` | `result` (optional string) |
| `RunErrorEvent` | `agentflow.run_error` | `message` |

Subclass `AgentEvent` to define application-specific events:

```python
class BookingEvent(AgentEvent):
    event_type: str = "app.booking"
    booking_id: str
    amount: float

await ctx.event_bus.emit(BookingEvent(booking_id="B-42", amount=299.0, run_id=ctx.run_id))
```

### Observability Hooks

Pass a `RunnerHooks` implementation to `StateGraphRunner`:

```python
recorder = RecorderHooks()
runner = StateGraphRunner(graph, ctx, hooks=recorder)
final = runner.run_sync(initial)
assert len(recorder.history) == 3  # three super-steps recorded
```

`LiveGraphHooks` records which nodes were active each step; call
`hooks.get_snapshot_graph(graph, step)` for coloured topology snapshots.

### Checkpointing & Pause/Resume

Save execution state after each super-step using a `CheckpointStore`. Use
`run_until(predicate, store=..., run_id=...)` to pause when a condition is met,
then `resume(store, run_id, from_step)` to continue (human-in-the-loop workflows).

```python
from agentflow.statemachine.checkpoint import InMemoryCheckpointStore

store = InMemoryCheckpointStore()
paused = await runner.run_until(
    initial_state,
    predicate=lambda step, state, active: step >= 1,
    store=store,
    run_id=ctx.run_id,
)
final = await runner.resume(store, ctx.run_id, from_step=1)
```

### Live Graph Visualization

`StateGraph` inherits `get_graph_html()` from `Describable`. From a script entry-point use
``graph --browser`` or ``graph -o file.html``; in code, save HTML or call
``open_graph_browser()``. For step-by-step DOT snapshots use `LiveGraphHooks` + `GraphRenderer.to_dot()`
(see demo 03).

```python
html = graph.get_graph_html(title="My Agent Graph")
Path("graph.html").write_text(html, encoding="utf-8")
```

```bash
uv run python examples/quickstart/03_live_graph_demo.py graph --browser
uv run python examples/quickstart/03_live_graph_demo.py graph --format dot -o graph.dot
```

## Running the Demos

All demos use `FakeLlmConnector` — no API keys required. Each demo script prints help when
run with no arguments; use the `run` subcommand to execute the workflow.

| Demo | Description | Command |
|------|-------------|---------|
| `01_brief_example.py` | Full §2.5 graph: parallel write + review loop | `uv run python examples/quickstart/01_brief_example.py run` |
| `02_tool_agent_demo.py` | Wrap existing `ToolAgent` as a single vertex | `uv run python examples/quickstart/02_tool_agent_demo.py run` |
| `03_live_graph_demo.py` | LiveGraphHooks → DOT snapshot per super-step | `uv run python examples/quickstart/03_live_graph_demo.py run` |
| `04_parallel_research_loop.py` | Parallel fan-out, fan-in, cycle, custom signals | `uv run python examples/quickstart/04_parallel_research_loop.py run` |

See also [statemachine_tutorial.md](../doc/guides/statemachine_tutorial.md) for a
step-by-step walkthrough from Hello World to a parallel research agent.

## Checkpoint Backends

The `CheckpointStore` protocol supports pluggable backends for different persistence needs:

| Backend | Package | Use case |
|---------|---------|---------|
| `InMemoryCheckpointStore` | built-in | Tests, short-lived workflows |
| `JsonFileCheckpointStore` | built-in | Single-process persistence, dev/debug |
| `PostgresCheckpointStore` | `.[postgres]` | Production, multi-process, durable |
| `RedisCheckpointStore` | `.[redis-backend]` | Fast ephemeral, session-scoped workflows |

### Installing backend extras

```bash
uv pip install -e ".[postgres]"        # PostgreSQL via asyncpg
uv pip install -e ".[redis-backend]"   # Redis via redis[asyncio]
```

### Quick example (PostgreSQL)

```python
import asyncio
from agentflow.statemachine import PostgresCheckpointStore, StateGraphRunner

async def main() -> None:
    DSN = "postgresql://agentflow:agentflow@localhost:5432/agentflow"
    async with PostgresCheckpointStore(DSN) as store:
        runner = StateGraphRunner(graph, ctx)
        # Run until a human-approval vertex is reached
        state = await runner.run_until(
            initial_state,
            lambda step, s, active: any(v.__class__.__name__ == "HumanApproval" for v in active),
            store=store,
            run_id="workflow-001",
        )
        # ... human reviews state ...
        final = await runner.resume(store, "workflow-001", from_step=2)
```

See [README.docker.md](../../../README.docker.md) for Docker setup and integration test instructions.
