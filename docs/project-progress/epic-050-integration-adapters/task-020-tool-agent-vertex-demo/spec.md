# Task T020 — ToolAgentVertex + Demo

**Epic:** E050 — Integration Adapters
**Task:** T020
**Root:** `src/agentflow/`

## Goal

Implement `ToolAgentVertex` (wraps entire ToolAgent as a single vertex), export all three
adapters, and create a demo showing migration of an existing agent to StateGraph.

## Context Bundle

- `src/agentflow/agents/ToolAgent.py` — `ToolAgent.arun()` (E040 output).
- `src/agentflow/statemachine/adapters/` — T010 output.
- `src/agentflow/statemachine/__init__.py` — update exports.
- `src/examples/statemachine_demos/01_brief_example.py` — reference for demo structure.
- `src/agentflow/statemachine/testing/fakes.py` — FakeLlmConnector, make_fake_context.

## Deliverables

| File | Action |
|------|--------|
| `src/agentflow/statemachine/adapters/tool_agent_vertex.py` | **Create** |
| `src/agentflow/statemachine/adapters/__init__.py` | **Modify** — add ToolAgentVertex |
| `src/agentflow/statemachine/__init__.py` | **Modify** — export ToolCallVertex, LlmTurnVertex, ToolAgentVertex |
| `src/agentflow/tests/statemachine/adapters/test_tool_agent_vertex.py` | **Create** |
| `src/examples/statemachine_demos/02_tool_agent_demo.py` | **Create** |

## Implementation

### `ToolAgentVertex`

```python
class ToolAgentVertex(StateVertex):
    """Wrap an entire ToolAgent as a single StateVertex.

    The agent runs its full ReAct loop (arun) and returns the final answer
    as a single atomic graph step. Simplest migration path for existing agents.

    Args:
        agent: Configured ToolAgent instance (with connector, tools, system_prompt).
        question_from_state: Callable[[state], str] — extracts the question.
        answer_to_patch: Callable[[str], patch] — maps final answer to patch.
        ok_signal: Signal returned after completion (default StdSignal.ok).
    """

    def __init__(
        self,
        agent: ToolAgent,
        question_from_state: Callable[[Any], str],
        answer_to_patch: Callable[[str], Any],
        *,
        ok_signal: Any = StdSignal.ok,
    ) -> None: ...

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        question = self._question_from_state(state)
        answer = await self._agent.arun(question)
        return self._ok_signal, self._answer_to_patch(answer)
```

Note: `ToolAgentVertex` uses `agent.arun()` (the agent's own connector), not `ctx.connector`.
The `ctx` parameter is accepted per the `StateVertex` contract but only `ctx.logger` may be
used for logging — the agent runs with its own injected dependencies.

## Demo (`02_tool_agent_demo.py`)

Build a graph with a single `ToolAgentVertex` node:
```
StartVertex → ToolAgentVertex → StdEnd
```

- Use `FakeLlmConnector` for the inner ToolAgent (no real API key needed).
- Use a minimal `FakeCalculatorTool` that echoes back a result.
- Show the complete lifecycle: initial state → question → answer in final state.
- Print the final state's answer to stdout.
- Must be runnable as `python src/examples/statemachine_demos/02_tool_agent_demo.py`.

The demo should produce output like:
```
Question: What is 42 + 8?
Answer: 50
```

## Tests (`test_tool_agent_vertex.py`, 2 tests)

Use `unittest.mock.AsyncMock` to patch `ToolAgent.arun`:
1. `test_tool_agent_vertex_calls_arun_with_question_from_state`
2. `test_tool_agent_vertex_maps_answer_to_patch_with_ok_signal`

## Code Quality

```bash
cd /home/ivo/workspace/git.hub.lab.ivo/ai_agents_education
uv run ruff check src/agentflow/statemachine/adapters/tool_agent_vertex.py
uv run mypy --strict --follow-imports=skip src/agentflow/statemachine/adapters/tool_agent_vertex.py
uv run pytest src/agentflow/tests/statemachine/adapters/test_tool_agent_vertex.py -v
python src/examples/statemachine_demos/02_tool_agent_demo.py
uv run pytest src/agentflow/tests/ -v -m "not integration"
```
