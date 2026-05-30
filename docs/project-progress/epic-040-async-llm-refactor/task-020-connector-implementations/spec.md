# Task T020 — OpenAiConnector.achat + AnthropicConnector.achat + ADR

**Epic:** E040 — Async LLM Refactor
**Task:** T020
**Root:** `src/agentflow/`

## Goal

Implement `achat` in `OpenAiConnector` and `AnthropicConnector` using their
respective async SDK clients. Write an ADR documenting the design decision.

## Context Bundle

- **spec.md TD-07, TD-15** — async-first path, backward-compat.
- `src/agentflow/llm/connectors/OpenAiConnector.py` — current sync connector.
- `src/agentflow/llm/connectors/AnthropicConnector.py` — current sync connector.
- `src/agentflow/doc/architecture/decisions/` — ADR directory.

## Deliverables

| File | Action |
|------|--------|
| `src/agentflow/llm/connectors/OpenAiConnector.py` | **Modify** — add `achat` |
| `src/agentflow/llm/connectors/AnthropicConnector.py` | **Modify** — add `achat` |
| `src/agentflow/doc/architecture/decisions/ADR-001-async-llm-api.md` | **Create** |
| `src/agentflow/tests/llm/test_achat_connectors.py` | **Create** |

## Implementation Detail

### `OpenAiConnector.achat`

Lazy-initialize an `AsyncOpenAI` client on first call:

```python
async def achat(
    self,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.2,
    model_override: str | None = None,
) -> ChatResponse:
    """Async counterpart to chat() — uses AsyncOpenAI client natively.

    Args: (same as chat)
    Returns: ChatResponse
    Raises: openai.OpenAIError on API failures.
    """
    model = model_override or self._config.model
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    resp = await self._async_client.chat.completions.create(**kwargs)
    return self._parse_response(resp.choices[0].message, resp.usage)
```

Lazy init of `_async_client`:
```python
@property
def _async_client(self) -> AsyncOpenAI:
    if self.__async_client is None:
        from openai import AsyncOpenAI
        kwargs: dict[str, Any] = {
            "timeout": self._config.timeout,
            "api_key": self._config.api_key or "local",
        }
        if self._config.base_url:
            kwargs["base_url"] = self._config.base_url
        self.__async_client = AsyncOpenAI(**kwargs)
    return self.__async_client
```

Add `self.__async_client: AsyncOpenAI | None = None` in `__init__`.

### `AnthropicConnector.achat`

Same pattern with `AsyncAnthropic`:

```python
async def achat(self, messages, tools=None, temperature=0.2, model_override=None) -> ChatResponse:
    system_messages = [m for m in messages if m.get("role") == "system"]
    user_messages = [m for m in messages if m.get("role") != "system"]
    system_content = system_messages[0]["content"] if system_messages else ""
    resp = await self._async_client.messages.create(
        model=model_override or self._config.model,
        max_tokens=_MAX_TOKENS_DEFAULT,
        system=system_content,
        messages=user_messages,
    )
    return self._parse_response(resp)
```

Lazy init: `self.__async_client: AsyncAnthropic | None = None` + property.

## ADR (`ADR-001-async-llm-api.md`)

Follow the template from `06-project-structure.mdc`:

```markdown
# ADR-001: Add achat() as async counterpart to LlmConnector.chat()

**Status**: Accepted
**Date**: 2026-05-29

## Context
StateVertex.run() is async; calling LLM via connector.chat() required
ctx.run_sync(connector.chat, ...) which wraps sync I/O in a thread pool.
This adds unnecessary overhead and obscures intent. E040 goal is to provide
a native async path while preserving backward compatibility.

## Decision
Add achat() as an abstract async method to LlmConnector with identical
signature to chat(). Concrete connectors lazily create an async SDK client
on first achat() call. ToolAgent gains arun() that uses achat(). sync chat()
and run() remain unchanged.

## Consequences
+ Vertices can use `await ctx.connector.achat(...)` directly — no thread pool.
+ Backward compatible — all existing code using chat()/run() unchanged.
+ Lazy async client avoids startup overhead when only sync path is used.
- Two clients per connector instance when both paths are used (memory overhead
  is negligible; accepted per TD-13: no new dependencies).
```

## Tests (`test_achat_connectors.py`) — 2 mock tests

Use `unittest.mock.AsyncMock` and `unittest.mock.MagicMock` to patch SDK clients.

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_openai_connector_achat_delegates_to_async_client():
    # patch openai.AsyncOpenAI with a mock whose
    # chat.completions.create is an AsyncMock returning a fake response
    ...

@pytest.mark.asyncio
async def test_anthropic_connector_achat_delegates_to_async_client():
    # patch anthropic.AsyncAnthropic similarly
    ...
```

**Note:** These tests are NOT marked `integration`. They should pass without API keys.

## Code Quality

```bash
cd /home/ivo/workspace/git.hub.lab.ivo/ai_agents_education
uv run ruff check src/agentflow/llm/connectors/OpenAiConnector.py src/agentflow/llm/connectors/AnthropicConnector.py
uv run mypy --strict --follow-imports=skip src/agentflow/llm/connectors/OpenAiConnector.py
uv run mypy --strict --follow-imports=skip src/agentflow/llm/connectors/AnthropicConnector.py
uv run pytest src/agentflow/tests/llm/test_achat_connectors.py -v
uv run pytest src/agentflow/tests/ -v -m "not integration"
```
