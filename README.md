# agentflow — Declarative AI Agent Orchestration

> A lightweight, educational framework for building LLM agent workflows using a declarative
> state graph with deterministic Bulk Synchronous Parallel (BSP) execution.

## Why agentflow?

agentflow lets you define agent workflows as explicit state graphs: frozen dataclass state,
typed reducers for parallel writes, and a BSP runner that executes super-steps as
Compute → Barrier → Apply & Route. Built-in visualization (`Describable`), checkpoint/resume,
and pluggable storage backends make the execution model inspectable end to end. The framework
is designed to be transparent and educational — no magic, all explicit.

## Features

- **Declarative graph topology** — define agents as `StateVertex` subclasses, wire with `Transition` and `Parallel`
- **BSP execution model** — deterministic super-steps: Compute → Barrier → Apply & Route
- **Immutable state** — frozen dataclasses with typed reducers, no accidental mutation
- **Built-in visualization** — SVG/HTML/DOT graph rendering via `Describable`
- **Checkpointing** — pluggable backends (Memory, JSON file, PostgreSQL, Redis)
- **Pause & resume** — `run_until(predicate)` + `resume(store, run_id, step)` for human-in-the-loop
- **LLM agnostic** — works with OpenAI, Anthropic, Ollama, Gemini, DeepSeek
- **mypy strict** — fully typed, zero-compromise type safety

## Quick Install

```bash
git clone <repo-url>
cd <repo>
uv sync
uv pip install -e .
```

## Hello World (15 lines)

```python
from dataclasses import dataclass
from agentflow.statemachine import (
    Context, StateGraph, StateGraphRunner, StateVertex,
    StdEnd, StdSignal, Transition,
)
from agentflow.statemachine.testing import FakeLlmConnector

@dataclass(frozen=True)
class AppState:
    text: str = ""

@dataclass
class AppPatch:
    text: str | None = None

class Uppercase(StateVertex):
    async def run(self, state, ctx):
        return StdSignal.ok, AppPatch(text=state.text.upper())

class Done(StateVertex):
    async def run(self, state, ctx):
        return StdSignal.done, AppPatch()

graph = StateGraph(
    start=Uppercase,
    transitions=[
        Transition(Uppercase, StdSignal.ok, Done),
        Transition(Done, StdSignal.done, StdEnd),
    ],
)
final = StateGraphRunner(graph, Context(FakeLlmConnector())).run_sync(AppState(text="hello"))
print(final.text)  # HELLO
```

## Comparison with similar frameworks

| Feature | **agentflow** | LangGraph | CrewAI |
|---------|--------------|-----------|--------|
| Execution model | BSP (deterministic super-steps) | Event-driven DAG | Role-based multi-agent |
| State management | Frozen dataclasses + typed reducers | TypedDict (mutable) | Pydantic models |
| Parallel execution | `Parallel(A, B)` with barrier sync | `Send()` API | Agent delegation |
| Graph visualization | Built-in SVG/HTML/DOT (`Describable`) | LangSmith (external service) | — |
| Checkpointing | Protocol-based (memory/file/DB) | PostgresSaver, RedisSaver | — |
| Pause / resume | `run_until()` + `resume()` | `interrupt_before/after` | — |
| Type safety | `mypy --strict`, frozen state | Partial | Partial |
| LLM agnostic | Yes (connector protocol) | Yes (LangChain) | Yes |
| Streaming tokens | ❌ not yet | ✅ | ✅ |
| Distributed execution | ❌ not yet | ❌ | ✅ (agents as services) |
| Production maturity | 🔬 educational | ✅ production-ready | ✅ production-ready |

agentflow prioritizes transparency and correctness over features. It is designed for learning
and prototyping. For production workloads requiring streaming or distributed execution, consider
LangGraph.

## Examples

| Example | Description |
|---------|-------------|
| `examples/quickstart/01_brief_example.py` | Basic graph: research → parallel write → review |
| `examples/quickstart/04_parallel_research_loop.py` | Parallel nodes + feedback loop |
| `examples/quickstart/05_human_in_the_loop_demo.py` | Pause/resume with checkpointing |
| `examples/patterns/02_tool_calling_demo.py` | Tool-calling agent with agentflow |
| `examples/patterns/04_react_agent_statemachine.py` | ReAct agent using StateGraph |

## Documentation

- [`agentflow/README.md`](agentflow/README.md) — library overview + API reference
- [`agentflow/statemachine/README.md`](agentflow/statemachine/README.md) — StateGraph quick-start
- [`docs/guides/statemachine_tutorial.md`](docs/guides/statemachine_tutorial.md) — step-by-step tutorial

## Testing

```bash
# Unit tests (no API keys required)
uv run pytest

# Integration tests (requires LLM API key + Docker services for DB backends)
uv run pytest -m integration
```

## Project Status

Early-stage educational library. Core framework (E010–E080) is stable.
Currently adding production backends (PostgreSQL/Redis checkpoints).
See [roadmap](docs/project-progress/roadmap.md).

## Configuration

Copy `.env.example` to `.env` and set your LLM API key:

```bash
cp .env.example .env
```

| Variable | Description |
|----------|-------------|
| `LLM_BACKEND` | `openai` / `anthropic` / `ollama` / `gemini` / `deepseek` |
| `LLM_MODEL` | Model name (e.g. `gpt-4o-mini`, `claude-3-haiku-20240307`) |
| `OPENAI_API_KEY` | Required for OpenAI backend |
| `ANTHROPIC_API_KEY` | Required for Anthropic backend |
