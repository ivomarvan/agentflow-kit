# Task T010 — Abstract `achat` + FakeLlmConnector + ToolAgent.arun

**Epic:** E040 — Async LLM Refactor
**Task:** T010
**Root:** `src/agentflow/`

## Goal

Extend the `LlmConnector` abstract interface with `achat`, implement it in
`FakeLlmConnector`, add `async arun(question)` to `ToolAgent`, and update the
`Context` docstring.

## Context Bundle

- **spec.md TD-07** — async vertices + `ctx.run_sync`; after E040, direct `await` path.
- **spec.md TD-15** — `runner.run_sync` vs `Context.run_sync` distinct semantics.
- `src/agentflow/llm/LlmConnector.py` — abstract base (to add `achat`).
- `src/agentflow/statemachine/testing/fakes.py` — `FakeLlmConnector` (to add `achat`).
- `src/agentflow/agents/ToolAgent.py` — `ToolAgent` (to add `arun`).
- `src/agentflow/statemachine/context.py` — update docstring.

## Deliverables

| File | Action |
|------|--------|
| `src/agentflow/llm/LlmConnector.py` | **Modify** — add `achat` abstract method |
| `src/agentflow/statemachine/testing/fakes.py` | **Modify** — add `achat` |
| `src/agentflow/agents/ToolAgent.py` | **Modify** — add `arun` |
| `src/agentflow/statemachine/context.py` | **Modify** — update docstring |
| `src/agentflow/tests/llm/test_achat_fake.py` | **Create** |

## Implementation Detail

### `LlmConnector.achat` (abstract)

Add immediately after the `chat` method:

```python
@abstractmethod
async def achat(
    self,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.2,
    model_override: str | None = None,
) -> ChatResponse:
    """Async counterpart to chat() — native coroutine, no thread pool needed.

    Args:
        messages: List of message dicts in OpenAI format.
        tools: Optional list of OpenAI-format tool definitions.
        temperature: Sampling temperature.
        model_override: Per-call model name override.

    Returns:
        ChatResponse with role, content, tool_calls, and usage.

    Raises:
        Exception: Backend-specific error on network, auth, or quota failures.
    """
    ...
```

### `FakeLlmConnector.achat`

Delegates to `self.chat()` (sync, no I/O, safe to call from async context):

```python
async def achat(
    self,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.2,
    model_override: str | None = None,
) -> ChatResponse:
    """Async version of chat() — delegates to the sync implementation."""
    return self.chat(messages, tools=tools, temperature=temperature,
                     model_override=model_override)
```

### `ToolAgent.arun`

Add after `run()`:

```python
async def arun(self, question: str) -> str:
    """Async counterpart to run() — uses connector.achat() for native coroutines.

    Identical logic to run() but awaits achat() instead of calling chat().
    Prefer arun() when integrating ToolAgent inside an async StateVertex.

    Args:
        question: User question or instruction.

    Returns:
        Final text answer from the LLM, or an error string when
        max_steps is exceeded.
    """
    # ... same logic as run() but: response = await self.connector.achat(...)
```

### `Context` docstring

Remove "until Epic E040" from the `run_sync` docstring. Update module docstring to reflect
that `achat` is now the preferred path for LLM calls within vertices.

## Tests (`test_achat_fake.py`) — 5 tests

Use `pytest.mark.asyncio` (or `asyncio_mode=strict` from pyproject.toml).

1. `test_fake_connector_achat_returns_chat_response` — basic happy path.
2. `test_fake_connector_achat_dequeues_responses_in_order` — two enqueued responses.
3. `test_fake_connector_achat_raises_when_queue_empty` — `RuntimeError` raised.
4. `test_tool_agent_arun_returns_final_answer` — one-shot response (no tool calls).
5. `test_tool_agent_arun_max_steps_exceeded_returns_error_string` — all steps used.

## Code Quality

```bash
cd /home/ivo/workspace/git.hub.lab.ivo/ai_agents_education
uv run ruff check src/agentflow/llm/LlmConnector.py src/agentflow/statemachine/testing/fakes.py src/agentflow/agents/ToolAgent.py
uv run mypy --strict --follow-imports=skip src/agentflow/llm/LlmConnector.py
uv run mypy --strict --follow-imports=skip src/agentflow/statemachine/testing/fakes.py
uv run mypy --strict --follow-imports=skip src/agentflow/agents/ToolAgent.py
uv run pytest src/agentflow/tests/llm/test_achat_fake.py -v
uv run pytest src/agentflow/tests/ -v -m "not integration"
```
