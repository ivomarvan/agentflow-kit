---
apm_category: epic-plan
apm_ref: E010
apm_level: epic
created_by: Planner
model: claude-opus-4-7
intended_for: Coder, Human
created_at: 2026-05-28
updated_at: 2026-05-28
approved_by: Human
approved_at: 2026-05-28
human_decisions_at: 2026-05-28
---

# Epic Plan: E010 — Core StateGraph MVP

## Epic Goal

Postavit minimální funkční jádro `agentflow.statemachine` s BSP smyčkou, do kterého lze ručně sestavit graf z předem zinstancovaných vrcholů a spustit ho. Bez auto-instanciace (E020), bez plnohodnotných observability hooků (E030), bez integračních adapterů (E050). Po dokončení Epicu **lze sestavit graf z briefu §2.5** (research → parallel write → review → loop) z ručně předaných instancí a spustit ho přes `runner.run_sync(initial_state)`.

## Task List

| Task  | Name                                    | Depends on  | Coder model |
|-------|-----------------------------------------|-------------|-------------|
| T010  | Package scaffolding & signals           | —           | Composer-2.5 Fast  |
| T020  | State, StatePatch & per-field reducery  | T010        | claude-sonnet-4-6 |
| T030  | Context + StateVertex + End/StdEnd      | T010        | Composer-2.5 Fast  |
| T040  | Topology: Transition, Parallel, StateGraph (manual instances) | T030 | Composer-2.5 Fast |
| T050  | StateGraphRunner with BSP loop          | T020, T040  | claude-sonnet-4-6 |
| T060  | Hooks: Protocol + NoOpHooks + LoggingHooks (minimal) | T050 | Composer-2.5 Fast |
| T070  | Testing utilities (FakeVertex, FakeLlmConnector, FakeContext, fixtures) | T050 | Composer-2.5 Fast |
| T080  | End-to-end demo: brief §2.5 graph běží s FakeLlmConnectorem | T060, T070 | Composer-2.5 Fast |

## Task Specifications

---

### T010 — Package scaffolding & signals

**Goal:** Založit balíček `src/agentflow/statemachine/` se strukturou dle briefu §8, přidat `frozendict` dependency a implementovat triviální `EnumSignal` typ + `StdSignal` enum jako první stavební kámen, který validuje, že struktura funguje.

**Inputs:**
- `src/agentflow/doc/project-progress/brief.md` (§1.3, §8)
- `src/agentflow/doc/project-progress/spec.md` (TD-03, TD-13)
- `pyproject.toml` (pro přidání závislosti)

**Outputs:**
- `src/agentflow/statemachine/__init__.py` — placeholder s re-exporty pouze `EnumSignal`, `StdSignal` (postupně růst).
- `src/agentflow/statemachine/signal.py` — `EnumSignal: TypeAlias = Enum`, `class StdSignal(EnumSignal)` s členy `ok`, `fail`, `done`.
- Prázdné placeholder soubory pro budoucí moduly (s docstringem popisujícím účel): `state.py`, `context.py`, `vertex.py`, `topology.py`, `runner.py`, `hooks.py`.
- `src/agentflow/statemachine/README.md` — krátký stub (Epic E080 doplní obsah).
- `src/agentflow/tests/statemachine/__init__.py` + `test_signal.py`.
- `pyproject.toml` — přidaná závislost `frozendict>=2.4` s komentářem zdůvodnění.

**Context Bundle:**
- Read:
  - `src/agentflow/doc/project-progress/brief.md` — celý dokument pro pochopení směru (zejm. §1.3 a §8).
  - `src/agentflow/doc/project-progress/spec.md` — TD-03 (Enum), TD-13 (žádné nové dep kromě frozendict).
  - `pyproject.toml` — formát závislostí, `requires-python`.
  - `src/agentflow/__init__.py` — vzor public re-exportů.
  - `src/agentflow/llm/__init__.py` — vzor strukturovaného modulu s `__init__.py`.
- Do not modify:
  - `src/agentflow/llm/**` (cizí scope).
  - `src/agentflow/agents/**`.
  - `src/agentflow/tools/**`.
  - `src/agentflow/describable/**`.
  - `doc/**` (mimo vlastní task adresář).
- Interfaces from prior tasks: žádné (první task).

**Test Specification:**
- `test_signal.py`:
  - `test_std_signal_has_ok_fail_done_members` — kontrola členů.
  - `test_std_signal_is_enum_signal_alias` — `isinstance(StdSignal.ok, EnumSignal)` resp. `isinstance(StdSignal.ok, Enum)` projde (alias je `Enum`).
  - `test_custom_signal_can_be_defined_independently` — definice ad-hoc `class CustomSig(EnumSignal): approved = auto()` neselže.
- Import smoke: `from src.agentflow.statemachine import EnumSignal, StdSignal` musí projít.
- mypy `--strict` na `src/agentflow/statemachine/` musí projít.

**Definition of Done:** viz `task-010-package-scaffolding/dod.md`.

**Recommended Coder model:** Composer-2.5 Fast (strukturální task bez složité logiky).

---

### T020 — State, StatePatch & per-field reducery

**Goal:** Implementovat mechanismus per-field reducerů z briefu §1.1. Klíčová funkce `apply_patches(state, patches)`, která pro každé pole stavu načte reducer z `Annotated[T, reducer]` anotace, postupně aplikuje příspěvky z patchů a vrátí novou instanci stavu. Pole bez reduceru → last-writer-wins + WARNING při kolizi.

**Inputs:**
- `src/agentflow/doc/project-progress/brief.md` (§1.1, §1.2)
- T010 deliverables (existující balíček).

**Outputs:**
- `src/agentflow/statemachine/state.py`:
  - Funkce `apply_patches(state: T, patches: Sequence[StatePatch]) -> T`.
  - Helper `extract_reducer(annotated_type)` — vrací reducer callable nebo `None`.
  - Konstanta `UNSET = object()` jako sentinel pro „nesetuj".
  - Dokumentace s ukázkou jak definovat `State` (frozen dataclass s `Annotated` poli) a `StatePatch` (dataclass s `| None = None` poli).
- `src/agentflow/statemachine/__init__.py` — přidat `apply_patches`, `UNSET` do re-exportů.
- `src/agentflow/tests/statemachine/test_state_reducers.py`:
  - `test_apply_patches_uses_reducer_for_annotated_field` — `operator.add` na `tuple` konkateuje dvě listy z dvou patchů.
  - `test_apply_patches_max_reducer_keeps_higher_score` — `max` aplikováno.
  - `test_apply_patches_no_reducer_last_writer_wins` — pole bez reduceru: poslední patch vyhrává.
  - `test_apply_patches_no_reducer_warns_on_collision` — `caplog` zachytí WARNING když 2 patche píší stejné pole bez reduceru.
  - `test_apply_patches_skips_none_value_in_patch` — `None` v patchi se ignoruje (= „nesetuj").
  - `test_apply_patches_returns_new_instance` — původní state nezměněn (immutability).
  - `test_apply_patches_empty_patch_list_returns_same_state` — edge case.

**Context Bundle:**
- Read:
  - `src/agentflow/doc/project-progress/brief.md` (§1.1, §1.2)
  - `src/agentflow/doc/project-progress/GLOSSARY.md` (definice Reducer, State, StatePatch)
  - Python stdlib `typing.get_type_hints(include_extras=True)`, `typing.get_args` — referenční dokumentace pro extrakci `Annotated` metadat.
- Do not modify: stejně jako T010 + `src/agentflow/statemachine/signal.py` (T010 hotov).
- Interfaces from prior tasks: žádné (state.py je nový, signal.py jen importuje pro StdSignal v případě potřeby — v T020 zatím není).

**Test Specification:** viz výše v Outputs (7 testů).

**Definition of Done (T020):**
- [ ] `apply_patches` implementováno, dokumentováno (docstring per `10-python.mdc`).
- [ ] Extrakce reduceru z `Annotated[T, reducer]` funguje pro typický případ (`Annotated[tuple, operator.add]`).
- [ ] WARNING při kolizi 2+ patchů na poli bez reduceru.
- [ ] `None` v patchi = „nenastavovat" (konvence z briefu §1.1).
- [ ] Všech 7 testů zelených.
- [ ] mypy `--strict` zelený.
- [ ] Žádná regrese v `pytest src/agentflow/tests/`.

**Recommended Coder model:** claude-sonnet-4-6 (reducer dispatch je nontrivální typová introspekce).

---

### T030 — Context + StateVertex + End/StdEnd

**Goal:** Implementovat `Context` dataclass s `run_sync` helperem (briefu §1.4), `StateVertex` ABC (§1.5), `End` marker a `StdEnd` default (§1.6).

**Inputs:**
- Brief §1.4, §1.5, §1.6.
- T010 deliverables.

**Outputs:**
- `src/agentflow/statemachine/context.py` — `Context` dataclass + `async run_sync(fn, *args, **kwargs)`.
- `src/agentflow/statemachine/vertex.py` — `StateVertex` ABC, `End` (marker subclass), `StdEnd` (default vrátí `StdSignal.done, StatePatch()`).
- `src/agentflow/statemachine/__init__.py` — přidat `Context`, `StateVertex`, `End`, `StdEnd` do re-exportů.
- Testy: `test_context.py`, `test_vertex_endings.py`.

**Context Bundle:**
- Read: brief §1.4–§1.6; `src/agentflow/llm/LlmConnector.py` (typ konstrukce `Context.connector`); `src/agentflow/tools/ToolRegistry.py` (typ `Context.tools`).
- Do not modify: existující `LlmConnector`, `ToolRegistry` (jen importujeme).
- Interfaces from prior tasks: `EnumSignal`, `StdSignal` z T010; `StatePatch` z T020 (jen jako typ v `StdEnd.run()`).
- Pozor na cyklický import: `vertex.py` importuje `StatePatch` z `state.py` jen pro type hint → použít `from __future__ import annotations` + `if TYPE_CHECKING:`.

**Test Specification:**
- `test_context_run_sync_executes_sync_callable` — sync fn vrátí hodnotu, await je možný.
- `test_context_run_id_is_unique_per_instance`.
- `test_context_default_logger_named_statemachine`.
- `test_state_vertex_is_abstract` — `pytest.raises(TypeError)` při instanciaci.
- `test_std_end_returns_done_and_empty_patch`.
- `test_end_subclass_detected_by_isinstance` — `isinstance(StdEnd(), End)` True.

**DoD (T030):**
- [ ] Všech 6 testů zelených, mypy --strict zelený, žádné regrese.
- [ ] Public API kompletní per brief §1.4–§1.6.

**Recommended Coder model:** Composer-2.5 Fast.

---

### T040 — Topology: Transition, Parallel, StateGraph (manual instances)

**Goal:** Implementovat `Transition` dataclass, `Parallel` třídu a `StateGraph` třídu. **V tomto Epicu pouze ručně předané instance** — žádná auto-instanciace tříd (`VertexResolver` přijde v E020). `StateGraph` poskytuje `get_targets(node, signal)`, `expand_target(target)`, `apply_patches(state, patches)` (delegace na T020), `resolve_start()`.

**Inputs:**
- Brief §2.1, §2.2, §2.5.
- T020, T030 deliverables.

**Outputs:**
- `src/agentflow/statemachine/topology.py`:
  - `@dataclass(frozen=True) class Transition` — `from_node: StateVertex`, `signal: EnumSignal`, `to_target: StateVertex | Parallel`.
  - `class Parallel` — drží `vertices: tuple[StateVertex, ...]`, metoda `expand() -> list[StateVertex]` (bez resolveru, jen vrátí instance jak přišly).
  - `class StateGraph` — `start: StateVertex`, `transitions: list[Transition]`; metody dle Goalu.
  - Kontrola při `__init__`: pokud je v `transitions` třída místo instance, vyhodit `TypeError` s informativní zprávou „auto-instantiation will be added in Epic E020; pass an instance for now".
- `__init__.py` aktualizace.
- `tests/statemachine/test_topology.py`:
  - `test_transition_stores_from_signal_to`.
  - `test_parallel_expand_returns_vertices_list`.
  - `test_state_graph_get_targets_returns_matching_transition_target`.
  - `test_state_graph_get_targets_no_match_returns_empty`.
  - `test_state_graph_expand_target_parallel_returns_flat_list`.
  - `test_state_graph_expand_target_single_vertex_returns_singleton_list`.
  - `test_state_graph_rejects_class_in_transitions_with_helpful_error`.

**Context Bundle:**
- Read: brief §2.
- Do not modify: žádný cizí modul.
- Interfaces from prior tasks: `StateVertex` (T030), `EnumSignal` (T010).

**DoD (T040):**
- [ ] Všech 7 testů zelených.
- [ ] mypy --strict zelený.
- [ ] Žádné regrese.

**Recommended Coder model:** Composer-2.5 Fast.

---

### T050 — StateGraphRunner with BSP loop

**Goal:** Implementovat `StateGraphRunner` per brief §3.2. Async smyčka s fázemi Compute → Barrier (`asyncio.gather`) → Apply (`graph.apply_patches`) → Route (set-based join). `_safe_run` mapuje výjimky na `(StdSignal.fail, StatePatch())`. Convenience `run_sync(state)` wrapper.

**Inputs:**
- Brief §3 (kompletně).
- T020, T040 deliverables.

**Outputs:**
- `src/agentflow/statemachine/runner.py`:
  - `class StateGraphRunner` — konstruktor přijímá `graph`, `context`, volitelně `hooks` (default `NoOpHooks` z T060, dočasně `None` až do dokončení T060 — pak importujeme).
  - `async def run(self, initial_state) -> State`.
  - `def run_sync(self, initial_state) -> State` — `asyncio.run(self.run(...))`.
  - `_safe_run(node, state)` — try/except, log.exception, vrátí `(StdSignal.fail, StatePatch())`.
- `__init__.py` aktualizace.
- `tests/statemachine/test_runner_bsp.py`:
  - `test_runner_sequential_two_vertices_runs_to_std_end` — `A → B → StdEnd`.
  - `test_runner_parallel_fan_out_runs_both_branches` — `A → Parallel(B, C) → StdEnd`, ověř že B i C běžely (přes side-effect ve FakeVertexu — který přidá svoji značku do patchu).
  - `test_runner_set_based_join_dedups_same_instance` — dvě větve → stejná instance `Review`, `Review` běžel jen jednou (čítač v FakeVertex).
  - `test_runner_cycle_terminates_via_std_end_after_n_iterations`.
  - `test_runner_vertex_exception_maps_to_std_signal_fail` — vrchol vyhodí, runner pokračuje přes `StdSignal.fail` transition.
  - `test_runner_run_sync_returns_final_state`.

**Context Bundle:**
- Read: brief §3, §1.1 (apply_patches), §2 (graph queries).
- Do not modify: nic mimo `statemachine/runner.py` a testy.
- Interfaces from prior tasks: `State`, `StatePatch`, `apply_patches` (T020), `Context` (T030), `StateGraph`, `Parallel`, `End` (T030, T040), `StdSignal` (T010).
- **Závisí na T060 pro `NoOpHooks`** — Coder může nejprve implementovat inline placeholder `_noop_hooks` a po T060 přejít na importovaný `NoOpHooks`. Plánovat T060 ihned po T050 nebo paralelně.

**Test Specification:** 6 testů viz Outputs. Použít `FakeVertex` z T070 — proto buď napsat jednoduchý ad-hoc fake přímo v testech, nebo počkat na T070 a T050 dokončit po T070. **Doporučení Plannerovi:** posunout pořadí T070 před T050 dependency-wise, jinak runner testy budou používat ad-hoc fakes a duplikovat se s T070. **Akceptováno: T050 závisí na T070.** Aktualizovat task list (T050 depends on T020, T040, T070).

**DoD (T050):**
- [ ] Všech 6 testů zelených.
- [ ] mypy --strict zelený.
- [ ] BSP smyčka přesně odpovídá pseudokódu z briefu §3.2.

**Recommended Coder model:** claude-sonnet-4-6 (jádro frameworku, kritické).

---

### T060 — Hooks: Protocol + NoOpHooks + LoggingHooks (minimal)

**Goal:** Definovat `RunnerHooks` Protocol s minimálním rozsahem callbacků pro MVP. Implementovat `NoOpHooks` (default) a `LoggingHooks` (strukturované DEBUG/INFO logy). Plnohodnotná verze s `RecorderHooks` patří do E030 — zde jen rozhraní + 2 default implementace.

**Inputs:**
- Brief §3.3.
- T050 deliverables.

**Outputs:**
- `src/agentflow/statemachine/hooks.py`:
  - `class RunnerHooks(Protocol)` s 5 metodami (per brief §3.3).
  - `class NoOpHooks` — všechny metody `async def ... -> None: return None`.
  - `class LoggingHooks` — strukturované logy přes `logging.getLogger(name)`.
- `__init__.py` aktualizace.
- `tests/statemachine/test_hooks.py`:
  - `test_noop_hooks_callbacks_return_none`.
  - `test_logging_hooks_logs_at_super_step_start` (přes `caplog`).
  - `test_logging_hooks_logs_vertex_error`.

**Context Bundle:**
- Read: brief §3.3.
- Do not modify: nic mimo `statemachine/hooks.py`.
- Interfaces from prior tasks: `State`, `StateVertex`, `EnumSignal`, `StatePatch`.

**DoD (T060):** 3 testy zelené, mypy --strict, žádné regrese.

**Recommended Coder model:** Composer-2.5 Fast.

---

### T070 — Testing utilities

**Goal:** Vystavět `src/agentflow/statemachine/testing/` modul s `FakeVertex`, `FakeLlmConnector`, `FakeContext` factory a pytest fixturami pro snadné testování grafů.

**Inputs:**
- Brief §7.
- T010–T060 deliverables.

**Outputs:**
- `src/agentflow/statemachine/testing/__init__.py`.
- `src/agentflow/statemachine/testing/fakes.py`:
  - `class FakeVertex(StateVertex)` — konstruktor `(signal, patch, *, name=None, call_counter=None)`; každé `run()` zaeviduje volání.
  - `class FakeLlmConnector` — minimální `LlmConnector` subclass s queue odpovědí: `queue_responses(list[str])`, `chat()` vrací další z queue jako `ChatResponse`.
  - `make_fake_context(**overrides) -> Context` — factory.
- `src/agentflow/statemachine/testing/fixtures.py`:
  - `@pytest.fixture def fake_ctx()`.
  - `@pytest.fixture def make_state_graph()` — factory pro snadné sestavení grafu z tuple seznamu.
- `tests/statemachine/test_testing_utilities.py`:
  - `test_fake_vertex_returns_configured_signal_and_patch`.
  - `test_fake_vertex_counts_calls`.
  - `test_fake_llm_connector_returns_queued_responses_in_order`.
  - `test_fake_llm_connector_raises_when_queue_empty`.
  - `test_make_fake_context_provides_default_logger_and_run_id`.

**Context Bundle:**
- Read: brief §7; `src/agentflow/llm/LlmConnector.py` (abstract base); `src/agentflow/llm/ChatResponse.py` (návratový typ).
- Do not modify: existující `LlmConnector` (jen subclass v testing).
- Interfaces from prior tasks: vše z T010–T060.

**DoD (T070):** 5 testů zelených, mypy --strict, žádné regrese.

**Recommended Coder model:** Composer-2.5 Fast.

---

### T080 — End-to-end demo: brief §2.5 graph

**Goal:** Demonstrovat, že MVP funguje — sestavit příklad z briefu §2.5 (research → parallel write → review → loop) z **ručních instancí**, spustit ho s `FakeLlmConnector` a `LoggingHooks`, ověřit terminaci přes `StdEnd`.

**Inputs:**
- Brief §2.5.
- T010–T070 deliverables.

**Outputs:**
- `src/examples/statemachine_demos/__init__.py`.
- `src/examples/statemachine_demos/01_brief_example.py`:
  - Definuje `MyState`, `MyStatePatch`, `MyResearch`, `MyWriteIntro`, `MyWriteBody`, `MyReview` (každý jednoduchý — vrací předdefinovaný signál a malý patch).
  - Sestaví `StateGraph` z ručních instancí.
  - Spustí `runner.run_sync(initial_state)`.
  - Vypíše finální stav a celkový log super-kroků.
  - Volat lze přes `python -m src.examples.statemachine_demos.01_brief_example`.
- `tests/statemachine/test_e2e_brief_example.py`:
  - `test_brief_example_runs_to_completion` — import skriptu, spuštění, asercia že finální state má očekávané hodnoty a běh skončí v `StdEnd`.

**Context Bundle:**
- Read: brief §2.5, kompletní `statemachine/` z T010–T070.
- Do not modify: nic mimo `src/examples/statemachine_demos/` a test.
- Interfaces from prior tasks: kompletní MVP public API.

**DoD (T080):**
- [ ] Demo skript spustitelný z CLI a běží do konce bez výjimky.
- [ ] E2E test zelený.
- [ ] `pytest src/agentflow/tests/` celé zelené (žádné regrese).
- [ ] mypy --strict celé `src/agentflow/statemachine/` + `src/examples/statemachine_demos/`.

**Recommended Coder model:** Composer-2.5 Fast.

## Závislosti — aktualizovaná tabulka

(po revizi T050↔T070 ve specifikaci T050)

| Task  | Depends on        |
|-------|-------------------|
| T010  | —                 |
| T020  | T010              |
| T030  | T010              |
| T040  | T030              |
| T060  | T010              |
| T070  | T010, T020, T030, T060 |
| T050  | T020, T040, T070  |
| T080  | T010..T070, T050  |

Doporučená paralelizace: po T030 lze paralelně T040 a T060. Po T040 + T060 + T020 → T070. Po T070 → T050. Po T050 → T080.

## Rozhodnutí (Human review — 2026-05-28)

| # | Téma | Rozhodnutí | Poznámka |
|---|------|------------|----------|
| 1 | **`apply_patches` API** | **Standalone funkce** v `state.py` | Viz TD-14 v `spec.md`. Uživatelský `State` nedědí od frameworku. |
| 2 | **`runner.run_sync` vs `Context.run_sync`** | **Obě jména ponechána** | Viz TD-15 v `spec.md`. Runner = celý graf; Context = sync→async wrapper. Dokumentovat v README (E080) a docstringy. |
| 3 | **mypy pro `apply_patches`** | **Coder rozhodne při T020** | `TypeVar("T", bound=…)` tak, aby `--strict` vracel stejný typ stavu. |
| 4 | **Python verze** | **Zůstat u 3.10** | `requires-python = ">=3.10"` v `pyproject.toml` je závazné; bump na 3.11 není potřeba. |
| 5 | **Regresní testy v E010** | **`pytest src/agentflow/tests/statemachine/`** | Default po každém tasku. Plné `pytest src/agentflow/tests/` jen u tasků, které mění kód mimo `statemachine/` (např. top-level `__init__.py` v T010). |
| 6 | **Top-level re-export** | **Povinné od T010** | `EnumSignal`, `StdSignal` v `src/agentflow/__init__.py`. Viz TD-16 v `spec.md`. |
