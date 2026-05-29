# Task T010 — ToolCallVertex + LlmTurnVertex

**Epic:** E050 — Integration Adapters
**Task:** T010
**Root:** `src/agentflow/`

## Goal

Create the `adapters/` package and implement `ToolCallVertex` (wraps one ToolBase call)
and `LlmTurnVertex` (single LLM chat turn without a ReAct loop).

## Context Bundle

- **brief §9** — adapter interface table.
- `src/agentflow/statemachine/vertex.py` — `StateVertex` ABC.
- `src/agentflow/statemachine/context.py` — `Context` (has `run_sync` + `connector.achat`).
- `src/agentflow/statemachine/signal.py` — `StdSignal`.
- `src/agentflow/tools/Tool.py` — `ToolBase.execute(json_args: str) -> str`.
- `src/agentflow/llm/ChatResponse.py` — `ChatResponse`.
- `src/agentflow/statemachine/testing/fakes.py` — `FakeLlmConnector`, `make_fake_context`.

## Deliverables

| File | Action |
|------|--------|
| `src/agentflow/statemachine/adapters/__init__.py` | **Create** (export ToolCallVertex, LlmTurnVertex) |
| `src/agentflow/statemachine/adapters/tool_call_vertex.py` | **Create** |
| `src/agentflow/statemachine/adapters/llm_turn_vertex.py` | **Create** |
| `src/agentflow/tests/statemachine/adapters/__init__.py` | **Create** (empty) |
| `src/agentflow/tests/statemachine/adapters/test_tool_call_vertex.py` | **Create** |
| `src/agentflow/tests/statemachine/adapters/test_llm_turn_vertex.py` | **Create** |

## Implementation

### `ToolCallVertex`

```python
class ToolCallVertex(StateVertex):
    """Wrap a single ToolBase call as a StateVertex.

    Extracts tool arguments from the current state via args_from_state,
    executes the tool synchronously (in a thread via ctx.run_sync), and
    maps the result string to a StatePatch via result_to_patch.

    All __init__ params have defaults (ok_signal, fail_signal) for VertexResolver
    compatibility, EXCEPT tool/args_from_state/result_to_patch which must be
    provided. Users should always pass instances explicitly.

    Args:
        tool: ToolBase instance to execute.
        args_from_state: Callable[[state], dict] — extracts tool kwargs from state.
        result_to_patch: Callable[[str], patch] — maps tool result string to patch.
        ok_signal: Signal on success (default StdSignal.ok).
        fail_signal: Signal on failure (default StdSignal.fail).
    """

    def __init__(
        self,
        tool: ToolBase,
        args_from_state: Callable[[Any], dict[str, Any]],
        result_to_patch: Callable[[str], Any],
        *,
        ok_signal: Any = StdSignal.ok,
        fail_signal: Any = StdSignal.fail,
    ) -> None: ...

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        import json
        try:
            args = self._args_from_state(state)
            result = await ctx.run_sync(self._tool.execute, json.dumps(args))
            return self._ok_signal, self._result_to_patch(result)
        except Exception:
            logger.exception("ToolCallVertex failed: tool=%s", type(self._tool).__name__)
            return self._fail_signal, self._result_to_patch("")
```

### `LlmTurnVertex`

```python
class LlmTurnVertex(StateVertex):
    """Single LLM chat turn as a StateVertex — no ReAct loop.

    Calls ctx.connector.achat with messages extracted from state.
    Suitable for fine-grained orchestration where each LLM call is
    an explicit graph node.

    Args:
        messages_from_state: Callable[[state], list[dict]] — builds messages list.
        response_to_patch: Callable[[ChatResponse], patch] — maps response to patch.
        tools: Optional list of OpenAI-format tool schemas.
        temperature: Sampling temperature (default 0.2).
        ok_signal: Signal returned after successful turn (default StdSignal.ok).
    """

    def __init__(
        self,
        messages_from_state: Callable[[Any], list[dict[str, Any]]],
        response_to_patch: Callable[[ChatResponse], Any],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        ok_signal: Any = StdSignal.ok,
    ) -> None: ...

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        messages = self._messages_from_state(state)
        response = await ctx.connector.achat(
            messages, tools=self._tools, temperature=self._temperature
        )
        return self._ok_signal, self._response_to_patch(response)
```

## Tests

### `test_tool_call_vertex.py`

Use a minimal `ToolBase` subclass as a fake:
```python
class EchoTool(ToolBase):
    """Echo tool — returns the JSON args as the result."""
    def execute(self, text: str) -> str:
        return f"echo:{text}"
```

Tests:
1. `test_tool_call_vertex_executes_tool_and_returns_ok_signal_with_patch`
2. `test_tool_call_vertex_returns_fail_signal_on_tool_exception`
3. `test_tool_call_vertex_extracts_args_from_state_correctly`

### `test_llm_turn_vertex.py`

Use `FakeLlmConnector` and `make_fake_context`.

Tests:
1. `test_llm_turn_vertex_calls_achat_returns_ok_signal_with_patch`
2. `test_llm_turn_vertex_passes_tools_parameter_to_achat`
3. `test_llm_turn_vertex_builds_messages_from_state`

## Code Quality

```bash
cd /home/ivo/workspace/git.hub.lab.ivo/ai_agents_education
uv run ruff check src/agentflow/statemachine/adapters/
uv run mypy --strict --follow-imports=skip src/agentflow/statemachine/adapters/tool_call_vertex.py
uv run mypy --strict --follow-imports=skip src/agentflow/statemachine/adapters/llm_turn_vertex.py
uv run pytest src/agentflow/tests/statemachine/adapters/ -v
uv run pytest src/agentflow/tests/ -v -m "not integration"
```
