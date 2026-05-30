---
apm_category: dod
apm_ref: E010.T070
apm_level: task
created_by: Planner
model: claude-opus-4-7
intended_for: Coder
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Definition of Done: E010.T070 — Testing utilities

Coder zaškrtne každý bod po jeho splnění.

## Implementace

- ✅ `src/agentflow/statemachine/testing/__init__.py` existuje a re-exportuje `FakeVertex`, `FakeLlmConnector`, `make_fake_context`.
- ✅ `src/agentflow/statemachine/testing/fakes.py` existuje.
- ✅ `FakeVertex(StateVertex)` — konstruktor `(signal, patch, *, name=None, call_count=None)`, `run()` vrátí `(signal, patch)`, `self.calls` inkrementuje.
- ✅ `FakeLlmConnector(LlmConnector)` — `queue_responses(list[str])`, `chat()` vrací z fronty, `RuntimeError` při prázdné frontě.
- ✅ `make_fake_context(**overrides) -> Context` — factory s `FakeLlmConnector` jako default connector.
- ✅ `src/agentflow/statemachine/testing/fixtures.py` existuje s `fake_ctx` a `make_state_graph` pytest fixturami.

## Testy

- ✅ `src/agentflow/tests/statemachine/test_testing_utilities.py` existuje.
- ✅ `test_fake_vertex_returns_configured_signal_and_patch` ✅
- ✅ `test_fake_vertex_counts_calls` ✅
- ✅ `test_fake_llm_connector_returns_queued_responses_in_order` ✅
- ✅ `test_fake_llm_connector_raises_when_queue_empty` ✅
- ✅ `test_make_fake_context_provides_default_logger_and_run_id` ✅

## Přístupnost fixtur

- ✅ `fake_ctx` fixture je dostupná v testech statemachine (přes `src/agentflow/tests/statemachine/conftest.py`).

## Kvalita kódu

- ✅ Google-style docstringy na všech veřejných třídách a metodách.
- ✅ Žádné relativní importy.

## Verifikace

- ✅ `pytest src/agentflow/tests/statemachine/` — zelené (35/35).
- ✅ `mypy --strict --follow-imports=skip src/agentflow/statemachine/` — zelený (11 source files, 0 errors).
- ✅ `ruff check` — čistý. `ruff format --check` — čistý pro všechny nové soubory. Pre-existující `topology.py` má drobnou format odchylku (mimo scope, nelze upravit).

## Reporting

- ✅ `report.md` v tomto adresáři vypracován dle `07-project-management.mdc`.

## Bezpečnostní zábrany

- ✅ **Žádný `git commit/push`** bez explicitního pokynu Human.
