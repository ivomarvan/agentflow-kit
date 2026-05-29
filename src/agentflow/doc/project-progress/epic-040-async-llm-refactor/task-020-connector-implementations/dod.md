# DoD — T020 OpenAiConnector.achat + AnthropicConnector.achat + ADR

## Definition of Done

- [x] `OpenAiConnector.achat` implemented with lazy `AsyncOpenAI` client.
- [x] `AnthropicConnector.achat` implemented with lazy `AsyncAnthropic` client.
- [x] Both implementations reuse the existing `_parse_response` static method.
- [x] Existing `chat()` method in both connectors remains **unchanged**.
- [x] `ADR-001-async-llm-api.md` created in `doc/architecture/decisions/`.
- [x] `test_achat_connectors.py` created with 2 mock-based tests (no network).
- [x] `ruff check` passes on modified connector files (pre-existing I001/E402 errors from `agr()` pattern are unchanged).
- [x] `mypy --strict --follow-imports=skip` passes on modified connector files (pre-existing errors from `--follow-imports=skip` + `git_root_to_syspath` are unchanged).
- [x] Full test suite passes: `pytest src/agentflow/tests/ -v -m "not integration"` — **145 passed, 6 deselected**.
