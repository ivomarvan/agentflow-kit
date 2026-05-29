# Epic E040 — Async LLM Refactor Across agentflow

**Goal:** Add `achat(...)` async counterpart to `LlmConnector` and all concrete
implementations; add `async arun(question)` to `ToolAgent`. Backward-compatible:
existing `chat()` / `run()` unchanged.

**Root:** `src/agentflow/` (not git root)

---

## Scope

| Deliverable | File |
|-------------|------|
| `achat` abstract method | `src/agentflow/llm/LlmConnector.py` |
| `OpenAiConnector.achat` | `src/agentflow/llm/connectors/OpenAiConnector.py` |
| `AnthropicConnector.achat` | `src/agentflow/llm/connectors/AnthropicConnector.py` |
| `FakeLlmConnector.achat` | `src/agentflow/statemachine/testing/fakes.py` |
| `ToolAgent.arun` | `src/agentflow/agents/ToolAgent.py` |
| Context docstring update | `src/agentflow/statemachine/context.py` |
| ADR | `src/agentflow/doc/architecture/decisions/ADR-001-async-llm-api.md` |
| Unit tests | `src/agentflow/tests/llm/test_achat_fake.py` (new) |

---

## Task List

| Task | Name | Depends on |
|------|------|-----------|
| T010 | Abstract interface + FakeLlmConnector + ToolAgent.arun | E010 done |
| T020 | OpenAiConnector.achat + AnthropicConnector.achat + ADR | T010 |

### Dependency Graph

```
T010 ──► T020
```

---

## Key Design Decisions

**Signature** — `achat` mirrors `chat` exactly, but is `async`:
```python
async def achat(
    self,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.2,
    model_override: str | None = None,
) -> ChatResponse: ...
```

**Backward compatibility:**
- `chat()` implementations remain **unchanged** in all connectors and ToolAgent.
- `ToolAgent.run()` remains unchanged (calls `connector.chat()`).
- `ToolAgent.arun()` is a new async method (calls `await connector.achat()`).
- `FakeLlmConnector.achat()` delegates to `self.chat()` — no real I/O.

**Real connectors:**
- `OpenAiConnector` gains a lazily-initialized `_async_client: AsyncOpenAI`
  (created on first `achat` call to avoid import-time overhead).
- `AnthropicConnector` gains a lazily-initialized `_async_client: AsyncAnthropic`.

**ADR:**
- Follows the ADR template in `06-project-structure.mdc`.
- Documents why `achat` was added as a parallel method (not replacing `chat`),
  and why lazy init was chosen for async clients.

---

## T010 — Abstract Interface + FakeLlmConnector + ToolAgent.arun

**Inputs:**
- `src/agentflow/llm/LlmConnector.py`
- `src/agentflow/statemachine/testing/fakes.py`
- `src/agentflow/agents/ToolAgent.py`
- `src/agentflow/statemachine/context.py`

**Deliverables:**
1. Add `achat` abstract method to `LlmConnector` (same signature as `chat`, but `async def`).
2. Add `achat` to `FakeLlmConnector` — async method that calls `self.chat(...)` synchronously.
3. Add `async arun(question)` to `ToolAgent` — mirrors `run()` but calls `await connector.achat(...)`.
4. Update `Context` docstring (remove "until Epic E040" note — E040 is now in progress).
5. Export nothing new from `__init__.py` — `achat` is a method, not a new class.

**Tests** (`test_achat_fake.py`):
1. `test_fake_connector_achat_returns_chat_response` — `await connector.achat([...])` returns `ChatResponse`.
2. `test_fake_connector_achat_dequeues_responses` — responses dequeued in order.
3. `test_fake_connector_achat_raises_when_empty` — `RuntimeError` when queue empty.
4. `test_tool_agent_arun_returns_answer` — `await agent.arun(question)` returns the correct string.
5. `test_tool_agent_arun_calls_achat_not_chat` — verify `achat` is used (patch the connector).

---

## T020 — OpenAiConnector.achat + AnthropicConnector.achat + ADR

**Inputs:**
- `src/agentflow/llm/connectors/OpenAiConnector.py`
- `src/agentflow/llm/connectors/AnthropicConnector.py`
- `src/agentflow/doc/architecture/decisions/` (new ADR)

**Deliverables:**

1. **`OpenAiConnector.achat`**:
   - Lazily initialize `self._async_client: AsyncOpenAI` in a `@property` or on first call.
   - Use `await self._async_client.chat.completions.create(**kwargs)` — same kwargs as `chat()`.
   - Reuse `_parse_response` static method (already exists) for response normalization.

2. **`AnthropicConnector.achat`**:
   - Lazily initialize `self._async_client: AsyncAnthropic`.
   - Use `await self._async_client.messages.create(**kwargs)`.
   - Reuse `_parse_response` static method.

3. **ADR** (`ADR-001-async-llm-api.md`):
   - Status: Accepted
   - Context: statemachine vertices need native async LLM calls; `ctx.run_sync` is a workaround
   - Decision: add `achat` alongside `chat`; lazy async client init; `ToolAgent.arun` as new entry point
   - Consequences: listed

**Tests** (mock-based, no network):
- `test_openai_connector_achat_calls_async_client` — use `unittest.mock.AsyncMock` to patch `AsyncOpenAI.chat.completions.create`.
- `test_anthropic_connector_achat_calls_async_client` — similarly for `AsyncAnthropic.messages.create`.

**Note:** These tests are **unit** (not `integration`) — they mock the SDK clients.

---

## Definition of Done (Epic Level)

- [ ] `LlmConnector.achat` abstract method exists.
- [ ] `FakeLlmConnector.achat` works and passes 3 unit tests.
- [ ] `ToolAgent.arun` works and passes 2 unit tests.
- [ ] `OpenAiConnector.achat` implemented with lazy `AsyncOpenAI`.
- [ ] `AnthropicConnector.achat` implemented with lazy `AsyncAnthropic`.
- [ ] 2 mock-based unit tests for real connectors pass.
- [ ] ADR-001 created.
- [ ] Full regression suite passes: `pytest src/agentflow/tests/ -v` (excluding integration).
- [ ] `ruff check` and `mypy --strict` on modified files pass.
