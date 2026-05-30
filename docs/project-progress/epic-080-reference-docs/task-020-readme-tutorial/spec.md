# Task T020 — statemachine README + Tutorial + Module README

**Epic:** E080 — Reference Examples & Documentation
**Task:** T020

## Goal

Write comprehensive documentation: statemachine quick-start README, step-by-step tutorial,
and update the top-level agentflow README with a statemachine section.

## Files to read FIRST — ALL of these

Source code to understand and document:
1. `src/agentflow/statemachine/__init__.py` — public API exports
2. `src/agentflow/statemachine/state.py` — State, StatePatch, reducers
3. `src/agentflow/statemachine/vertex.py` — StateVertex, End, StdEnd
4. `src/agentflow/statemachine/signal.py` — StdSignal, EnumSignal
5. `src/agentflow/statemachine/context.py` — Context
6. `src/agentflow/statemachine/topology.py` — StateGraph, Transition, Parallel
7. `src/agentflow/statemachine/runner.py` — StateGraphRunner, run_until, resume
8. `src/agentflow/statemachine/hooks.py` — RunnerHooks, RecorderHooks, LiveGraphHooks
9. `src/agentflow/statemachine/adapters/` — ToolCallVertex, LlmTurnVertex, ToolAgentVertex
10. `src/agentflow/statemachine/checkpoint.py` — CheckpointStore, InMemoryCheckpointStore
11. `src/agentflow/README.md` — existing module README (to update)

Demo scripts for code examples:
12. `src/examples/statemachine_demos/01_brief_example.py`
13. `src/examples/statemachine_demos/02_tool_agent_demo.py`
14. `src/examples/statemachine_demos/03_live_graph_demo.py`
15. Latest demo from E080 T010 (04 or 05)

## Deliverables

| File | Action |
|------|--------|
| `src/agentflow/statemachine/README.md` | **Create** |
| `src/agentflow/doc/guides/statemachine_tutorial.md` | **Create** |
| `src/agentflow/README.md` | **Modify** — add statemachine section |

## `statemachine/README.md` structure

```markdown
# agentflow.statemachine

One-paragraph description of what the library does and why it uses BSP.

## Quick Start

# 10-line complete example: two FakeVertex nodes, run, check state

## Core Concepts

### State & StatePatch
### StateVertex
### StateGraph and Transitions  
### StateGraphRunner (BSP loop)
### Signals

## Public API

Table: Class | Purpose | Import path
(cover all exported symbols)

## Cookbook Patterns

### Router node
### Parallel fan-out / fan-in
### Loop (cycle)
### Integration adapters
### Observability hooks
### Checkpointing & pause/resume
### Live graph visualization

## Running the Demos

Short description of each demo file (01–05) and how to run it.
```

**Length:** ≥ 120 lines.

## `statemachine_tutorial.md` structure

```markdown
# StateGraph Tutorial: From First Graph to Parallel Research Agent

## 1. Setup and Prerequisites
## 2. Your First Graph — Hello World
   Code snippet: 2 nodes, linear, prints result
## 3. State with Field Reducers
   Code snippet: parallel merge with list_append reducer
## 4. Routing with Signals
   Code snippet: Router with 3 exits
## 5. Parallel Fan-out and Fan-in
   Code snippet: Parallel(A, B) joining at C
## 6. Cycles (Loops)
   Code snippet: loop back to earlier node
## 7. Integration: ToolCallVertex, LlmTurnVertex, ToolAgentVertex
   Brief example of each
## 8. Observability: RecorderHooks and LiveGraphHooks
   How to inspect history / generate graph snapshots
## 9. Graph Visualization
   graph.get_graph_html() → browser
## 10. Checkpointing & Human-in-the-Loop
   Concise example using run_until + resume
```

**Length:** ≥ 150 lines.

## `src/agentflow/README.md` update

Add a new section `## agentflow.statemachine` after the existing sections:
- 2-sentence description.
- Table of key classes.
- 8-line minimal example code block.
- Link: `See [statemachine/README.md](statemachine/README.md) for full reference.`

## Code quality

The documentation files must:
- Use fenced code blocks with `python` syntax highlighting.
- All code snippets be syntactically correct Python.
- Not contain any TODOs or placeholder text.
