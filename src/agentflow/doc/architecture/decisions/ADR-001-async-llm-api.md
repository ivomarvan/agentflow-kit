# ADR-001: Add achat() as async counterpart to LlmConnector.chat()

**Status**: Accepted
**Date**: 2026-05-29

## Context

`StateVertex.run()` is an async method; calling an LLM via `connector.chat()` required
wrapping the synchronous I/O call in a thread pool (e.g. `asyncio.get_event_loop().run_in_executor`).
This adds unnecessary scheduling overhead, obscures intent at the call site, and bypasses
the async SDK's native connection pooling and timeout handling.

Epic E040 aims to provide a native async path through the connector layer while preserving
full backward compatibility for all existing synchronous callers.

## Decision

Add `achat()` as an abstract async method to `LlmConnector` with an identical signature
to `chat()`.  Concrete connectors lazily create a dedicated async SDK client on the first
`achat()` call:

- `OpenAiConnector` uses `openai.AsyncOpenAI` (same parameters as the existing `OpenAI` client).
- `AnthropicConnector` uses `anthropic.AsyncAnthropic`.

The lazy-initialisation pattern (via a `@property` backed by a `_async_client_cache` field)
ensures that connectors used exclusively via the sync `chat()` path incur zero startup cost
for the async client.

The sync `chat()` method and its `_client` field remain **unchanged** in both connectors.

## Consequences

**Positive**

- Vertices can `await ctx.connector.achat(...)` directly — no thread-pool wrapper needed.
- Backward compatible: all existing code using `chat()` / `run()` continues to work without
  modification.
- Lazy async-client creation avoids startup overhead when only the sync path is used.
- Both SDK clients share the same `LlmConfig`, so model, timeout, and base URL are consistent
  across sync and async paths.

**Negative / Trade-offs**

- Two client instances per connector when both `chat()` and `achat()` are used in the same
  process.  Memory overhead is negligible (a few KB per client object); accepted per spec
  constraint TD-13 (no new third-party dependencies).
- The Anthropic connector's `tools` parameter remains unimplemented in both `chat()` and
  `achat()` — this is a pre-existing limitation, not introduced by this change.
