# Epic E050 — Integration Adapters

**Goal:** Three `StateVertex` adapters bridging `ToolBase`/`ToolAgent` into the StateGraph
so existing tools and agents can participate in graphs without rewriting their logic.

**Root:** `src/agentflow/` (not git root)

---

## Scope

| Deliverable | File |
|-------------|------|
| `ToolCallVertex` | `src/agentflow/statemachine/adapters/tool_call_vertex.py` |
| `LlmTurnVertex` | `src/agentflow/statemachine/adapters/llm_turn_vertex.py` |
| `ToolAgentVertex` | `src/agentflow/statemachine/adapters/tool_agent_vertex.py` |
| Package init | `src/agentflow/statemachine/adapters/__init__.py` |
| Demo example | `src/examples/statemachine_demos/02_tool_agent_demo.py` |
| Unit tests | `src/agentflow/tests/statemachine/adapters/` |
| Export update | `src/agentflow/statemachine/__init__.py` |

---

## Task List

| Task | Name | Depends on |
|------|------|-----------|
| T010 | ToolCallVertex + LlmTurnVertex | E010 + E040 done |
| T020 | ToolAgentVertex + demo | T010 |

---

## Adapter Interfaces (from brief §9)

### `ToolCallVertex`
```python
ToolCallVertex(
    tool: ToolBase,
    args_from_state: Callable[[Any], dict[str, Any]],
    result_to_patch: Callable[[str], Any],
    *,
    ok_signal: Any = StdSignal.ok,
    fail_signal: Any = StdSignal.fail,
)
```
- Calls `tool.execute(json.dumps(args_from_state(state)))` via `ctx.run_sync` (ToolBase.execute is sync).
- On success → `return ok_signal, result_to_patch(result)`.
- On exception → `return fail_signal, result_to_patch("")` (or re-raise?). Use fail_signal.

### `LlmTurnVertex`
```python
LlmTurnVertex(
    messages_from_state: Callable[[Any], list[dict[str, Any]]],
    response_to_patch: Callable[[ChatResponse], Any],
    *,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.2,
    ok_signal: Any = StdSignal.ok,
)
```
- Calls `await ctx.connector.achat(messages, tools=tools, temperature=temperature)`.
- Returns `ok_signal, response_to_patch(response)`.

### `ToolAgentVertex`
```python
ToolAgentVertex(
    agent: ToolAgent,
    question_from_state: Callable[[Any], str],
    answer_to_patch: Callable[[str], Any],
    *,
    ok_signal: Any = StdSignal.ok,
)
```
- Calls `await agent.arun(question_from_state(state))`.
- Returns `ok_signal, answer_to_patch(answer)`.

---

## T010 — ToolCallVertex + LlmTurnVertex

**Inputs:**
- `src/agentflow/tools/Tool.py` — ToolBase interface
- `src/agentflow/llm/ChatResponse.py` — ChatResponse type
- `src/agentflow/statemachine/vertex.py` — StateVertex
- `src/agentflow/statemachine/context.py` — Context (has run_sync + connector.achat)
- `src/agentflow/statemachine/signal.py` — StdSignal

**Deliverables:**
1. Create `src/agentflow/statemachine/adapters/__init__.py`
2. Create `src/agentflow/statemachine/adapters/tool_call_vertex.py` — `ToolCallVertex`
3. Create `src/agentflow/statemachine/adapters/llm_turn_vertex.py` — `LlmTurnVertex`
4. Create test directory + `test_tool_call_vertex.py` + `test_llm_turn_vertex.py`

**Tests:**

`test_tool_call_vertex.py` (3 tests):
1. `test_tool_call_vertex_executes_tool_and_returns_patch` — happy path; verify result in patch.
2. `test_tool_call_vertex_returns_fail_signal_on_exception` — tool raises → fail_signal returned.
3. `test_tool_call_vertex_uses_args_from_state` — verify correct args passed to execute.

`test_llm_turn_vertex.py` (3 tests):
1. `test_llm_turn_vertex_calls_achat_and_returns_patch` — uses FakeLlmConnector.
2. `test_llm_turn_vertex_passes_tools_to_achat` — verify tools forwarded correctly.
3. `test_llm_turn_vertex_uses_messages_from_state` — verify correct messages from state.

---

## T020 — ToolAgentVertex + Demo

**Inputs:**
- `src/agentflow/agents/ToolAgent.py` — ToolAgent (with arun from E040)
- T010 output (adapters package)

**Deliverables:**
1. Create `src/agentflow/statemachine/adapters/tool_agent_vertex.py` — `ToolAgentVertex`
2. Update `src/agentflow/statemachine/adapters/__init__.py` — export all 3 adapters
3. Update `src/agentflow/statemachine/__init__.py` — export adapters
4. Create `src/examples/statemachine_demos/02_tool_agent_demo.py` — demo
5. Create `test_tool_agent_vertex.py`

**Tests** (`test_tool_agent_vertex.py`, 2 tests):
1. `test_tool_agent_vertex_calls_arun_and_returns_patch` — mock ToolAgent.arun.
2. `test_tool_agent_vertex_question_from_state` — verify question extracted from state.

**Demo (`02_tool_agent_demo.py`)**:
- Build a simple StateGraph with `ToolAgentVertex` wrapping a `ToolAgent` using `FakeLlmConnector`.
- Demonstrates the migration path: existing ReAct agent as a single `StateVertex`.
- Run end-to-end with `FakeLlmConnector` (no real API key needed).

---

## Definition of Done (Epic Level)

- [ ] `ToolCallVertex`, `LlmTurnVertex`, `ToolAgentVertex` in `adapters/`.
- [ ] All 3 adapters exported from `statemachine/__init__.py`.
- [ ] 8 unit tests pass.
- [ ] `02_tool_agent_demo.py` runs end-to-end with exit 0.
- [ ] Full regression: `pytest src/agentflow/tests/ -v -m "not integration"`.
- [ ] `ruff check` + `mypy --strict` pass on adapter files.
