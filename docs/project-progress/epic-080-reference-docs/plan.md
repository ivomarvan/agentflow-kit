# Epic E080 — Reference Examples & Documentation

**Goal:** Complete the reference demo suite and write the quick-start README, tutorial,
and updated top-level module README so new users can onboard in minutes.

**Root:** `src/agentflow/`

---

## Scope

| Deliverable | File |
|-------------|------|
| Parallel-research-with-loop demo | `src/examples/statemachine_demos/04_parallel_research_loop.py` |
| Note: ToolAgent migration demo | `src/examples/statemachine_demos/02_tool_agent_demo.py` (already exists from E050) |
| `statemachine` README | `src/agentflow/statemachine/README.md` |
| Step-by-step tutorial | `src/agentflow/doc/guides/statemachine_tutorial.md` |
| Updated module README | `src/agentflow/README.md` — add statemachine section |

**Note on existing demos:** E010–E060 already produced demos 01, 02, 03. E080 adds the
"parallel research with loop" variant (04) and focuses mainly on documentation.

---

## Task List

| Task | Name | Depends on |
|------|------|-----------|
| T010 | Parallel-research-with-loop demo | E010 + E020 done |
| T020 | statemachine README + tutorial + module README update | T010 |

---

## T010 — Parallel-Research-with-Loop Demo

**Inputs:**
- `src/examples/statemachine_demos/01_brief_example.py` — existing graph (no loop)
- `src/agentflow/statemachine/` — full library API

**Deliverable:** `src/examples/statemachine_demos/04_parallel_research_loop.py`

**Graph design:**
```
Research → Parallel(WriteIntro, WriteBody) → Review → StdEnd  (if approved)
                                                ↓
                                            Research  (if needs_revision)
```

Signal routing from `Review`:
- `approved` → `StdEnd`
- `needs_revision` → back to `Research` (cycle)

Loop termination: use a `revision_count` field in state; after 2 revisions, `Review` always returns `approved`.

Use `FakeVertex` subclasses (no real LLM — purely deterministic for demo purposes).
State: frozen dataclass with `topic: str`, `intro: str`, `body: str`, `review_notes: str`, `revision_count: int`.

Must be runnable: `python src/examples/statemachine_demos/04_parallel_research_loop.py`

---

## T020 — statemachine README + Tutorial + Module README

**Inputs:**
- Read ALL existing source files in `src/agentflow/statemachine/` to extract the public API.
- Read all demo scripts (`01`–`04`) for code examples.
- Read `src/agentflow/README.md` (existing).

### `src/agentflow/statemachine/README.md` — Quick-start reference

Structure:
```markdown
# agentflow.statemachine

## Quick Start (10 lines)
## Core Concepts
  - State & StatePatch (reducers)
  - StateVertex (async run)
  - StateGraph (Describable topology)
  - StateGraphRunner (BSP loop)
## Public API reference (table: class → purpose → module)
## Cookbook Patterns
  - Router (single decision node)
  - Parallel fan-out / fan-in
  - Loop (cycle back to earlier node)
  - Integration adapters (ToolCallVertex, LlmTurnVertex, ToolAgentVertex)
  - Checkpointing & pause/resume (E070)
  - Live graph visualization (E060)
## Running the demos
```

### `src/agentflow/doc/guides/statemachine_tutorial.md` — Step-by-step tutorial

Structure:
```markdown
# StateGraph Tutorial: From First Graph to Parallel Research

## 1. Installation & setup
## 2. Hello World — two-node graph
## 3. State with reducers
## 4. Routing with signals
## 5. Parallel fan-out / fan-in
## 6. Looping (cycles)
## 7. Integration: ToolCallVertex, LlmTurnVertex, ToolAgentVertex
## 8. Observability: RunnerHooks, RecorderHooks, LiveGraphHooks
## 9. Graph visualization (StateGraph.get_graph_html())
## 10. Checkpointing & human-in-the-loop
```

Each section: 2–4 sentences + a minimal code snippet.

### `src/agentflow/README.md` — Add statemachine section

Add a new `## agentflow.statemachine` section (after existing sections) with:
- 2-sentence purpose.
- Link to `statemachine/README.md`.
- 10-line "Hello World" code block.

---

## Definition of Done (Epic Level)

- [ ] `04_parallel_research_loop.py` runs end-to-end; loop terminates in ≤3 steps.
- [ ] `src/agentflow/statemachine/README.md` exists (≥80 lines, all sections present).
- [ ] `src/agentflow/doc/guides/statemachine_tutorial.md` exists (≥120 lines, 10 sections).
- [ ] `src/agentflow/README.md` has new statemachine section.
- [ ] Full regression still passes (no code changes → same 160 tests).
- [ ] `ruff check` passes on the new demo script.
- [ ] `mypy --strict --follow-imports=skip` passes on the new demo script.
