# DoD — T010 Abstract `achat` + FakeLlmConnector + ToolAgent.arun

## Definition of Done

- [ ] `LlmConnector.achat` abstract method exists with correct signature and docstring.
- [ ] `FakeLlmConnector.achat` async method implemented; delegates to `self.chat()`.
- [ ] `ToolAgent.arun(question)` async method implemented; calls `await connector.achat(...)`.
- [ ] `Context` module/run_sync docstring updated to remove "until E040" note.
- [ ] `test_achat_fake.py` created with 5 passing tests.
- [ ] `ruff check` passes on all modified files.
- [ ] `mypy --strict --follow-imports=skip` passes on all modified files.
- [ ] Full test suite passes: `pytest src/agentflow/tests/ -v -m "not integration"`.
