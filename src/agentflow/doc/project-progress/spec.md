---
apm_category: project-spec
apm_ref: PROJECT
apm_level: project
created_by: Planner
model: claude-opus-4-7
intended_for: All
created_at: 2026-05-28
updated_at: 2026-05-28
approved_by: Human
approved_at: 2026-05-28
human_decisions_at: 2026-05-28
---

# Project Specification — `agentflow.statemachine`

Formalizace projektového briefu (`brief.md`) do specifikace cílového stavu, scope, omezení a kritérií dokončení.

## 1. Goal

Postavit deklarativní, objektově orientovaný framework pro orchestraci LLM agentů, který:
1. **Edukativně transparentní** — umožní hluboce pochopit, jak orchestrace agentů funguje (paralelismus, stav, cykly, fan-in/fan-out).
2. **Architektonicky čistý** — minimalistické jádro postavené na BSP modelu, bez „magie", s jasným oddělením State / Vertex / Topology / Context.
3. **Prakticky použitelný** — slouží jako základ několika konkrétních příkladů a integruje se s existujícím `src/agentflow` (LlmConnector, ToolBase, ToolAgent, Describable).

## 2. Scope

V scope jsou:

- **Jádro StateGraph** (E010): `State`, `StatePatch`, per-field reducery, `EnumSignal`, `Context`, `StateVertex`, `End`/`StdEnd`, `Transition`, `Parallel`, `StateGraphRunner` s BSP smyčkou, ošetření výjimek.
- **Auto-instanciace a statická analýza** (E020): `VertexResolver` (singleton-per-class), validace default parametrů, varování pro asymetrický join.
- **Observability** (E030): `RunnerHooks` Protocol s implementacemi `NoOpHooks`, `LoggingHooks`, `RecorderHooks`.
- **Async LLM refactor** (E040): převod `LlmConnector.chat()` na async; helper `ctx.run_sync`; `runner.run_sync` convenience.
- **Integrace s tools/agents** (E050): adaptery `ToolCallVertex`, `LlmTurnVertex`, `ToolAgentVertex`.
- **Integrace s Describable** (E060): `StateGraph.get_graph()` produkuje topologii + kompoziční pohled; `LiveGraphHooks` aktualizují stav v reálném čase pro vizualizaci.
- **Checkpointing** (E070): `CheckpointStore` Protocol; implementace `InMemory`, `JsonFile`; pause/resume API.
- **Reference examples & docs** (E080): cookbook s `Router` patternem a paralelní researche; `README.md` v `src/agentflow/statemachine/`; tutoriál.
- **Testovací utility** (průřezově ve všech Epics): `FakeVertex`, `FakeLlmConnector`, `FakeContext`, pytest fixtury — vše v `src/agentflow/statemachine/testing/`.

## 3. Non-Goals

Explicitně mimo scope:

- **Produkční náhrada LangGraph/LlamaIndex Workflows/Burr** — cílem je edukace, ne feature parita.
- **Distribuovaný BSP** (uzly v různých procesech/strojích).
- **Explicitní `Join(...)` count-based barrier** — zatím vystačí WARNING ze statické analýzy.
- **Streaming LLM tokenů uvnitř vrcholů** — řešitelné jako extension `LlmTurnVertex` po E040.
- **Plnohodnotný retry/back-off framework** — uzel si retry řeší sám (typicky parametrem `__init__`).
- **Persistence backendy Postgres/Redis** — pro edukativní projekt overkill; pouze in-memory + JSON soubor + případně SQLite.
- **GUI editor topologie** — vizualizace ano (přes `Describable`/`GraphRenderer`), interaktivní editor ne.

## 4. Key Technical Decisions

| # | Rozhodnutí | Důvod |
|---|------------|-------|
| TD-01 | **BSP (Bulk Synchronous Parallel)** místo Fork-Join | Eliminuje race conditions ve stavu při paralelních větvích + cyklech. |
| TD-02 | **`State` immutable + `StatePatch` + per-field reducery** (`Annotated[T, reducer]`) | Deterministický merge více patchů v jednom super-kroku; rozšiřitelnost bez „god-method". |
| TD-03 | **`EnumSignal: TypeAlias = Enum`** (žádný subclassing Enum) | Python neumožňuje subclassing Enum tříd s členy — typový alias je idiomatické řešení. |
| TD-04 | **Imutabilní kontejnery ve stavu** (`tuple`, `frozenset`, `frozendict`) | `@dataclass(frozen=True)` chrání jen reassignment atributů, ne obsah kontejnerů. |
| TD-05 | **Singleton-per-class auto-instanciace** přes interní `VertexResolver` | Umožňuje implicitní fan-in přes `set()` díky identitě instancí. |
| TD-06 | **Auto-instanciace vyžaduje default hodnoty všech konstruktorových parametrů** | Bez defaultů by framework tiše vyrobil rozbitou instanci. Při porušení runner vyhodí jasnou chybu při sestavování grafu. |
| TD-07 | **Async vrcholy + `ctx.run_sync(fn)` helper** | Vrcholy mají jednotné async rozhraní; blokující IO (LLM, tools) jde transparentně přes `asyncio.to_thread`. |
| TD-08 | **`End`/`StdEnd` jako běžné `StateVertex`** (ne magický sentinel) | Konec lze přizpůsobit (logging, notifikace) bez speciální cesty v runneru. |
| TD-09 | **Conditional routing přes `Router` pattern** (žádný `ConditionalTransition`) | Topologie zůstává čistě signal-driven; router je normální vrchol → integruje se s `Describable`. |
| TD-10 | **`RunnerHooks` Protocol** pro observability | Default no-op; opt-in implementace. Jádro zůstává jednoduché. |
| TD-11 | **`CheckpointStore` Protocol** s `InMemory` + `JsonFile` implementacemi (SQLite stretch) | Snadné testování, jednoduchá persistence pro skripty; vyhne se Postgres/Redis overkillu. |
| TD-12 | **Implicitní `set()` join s `WARNING` při asymetrii** (žádný explicitní `Join` v MVP) | Pokrývá 90 % případů s minimální složitostí; uživatel je upozorněn při riziku. |
| TD-13 | **Žádná nová externí závislost kromě `frozendict`** | Minimalismus. |
| TD-14 | **`apply_patches` jako standalone funkce** v `state.py` | Uživatelský `State` zůstává čistý frozen dataclass bez dědičnosti od frameworku. |
| TD-15 | **`runner.run_sync` a `Context.run_sync` obě ponechány** | Různá sémantika: runner spouští celý graf (`asyncio.run`); context obaluje sync callable do async (`asyncio.to_thread`). Dokumentace musí rozlišit. |
| TD-16 | **Top-level re-export signálů** z `src/agentflow/__init__.py` | `EnumSignal` a `StdSignal` dostupné jako `from src.agentflow import …` od T010. |

## 5. Assumptions

- **Python ≥ 3.10** (per `requires-python` v `pyproject.toml`). Plánované API využívá `Annotated` (3.9+), `TypeAlias` a `X | None` (3.10+). **3.11 není vyžadováno** — žádná plánovaná feature z E010–E080 na něm nestojí.
- **Cíl: lokální skripty + Jupyter notebooky**, ne dlouho-běžící servery. Pro server use-case stačí `runner.run_sync` v handleru.
- **LLM volání jsou drahé a pomalé**, proto BSP overhead (`gather` synchronizace) je v poměru zanedbatelný.
- **Uživatel zná Python a má základní povědomí o async/await** (cílová persona = developer + AI engineer).
- **Existující `agentflow` (LlmConnector, ToolBase, ToolAgent, Describable) zůstává funkčně beze změny** mimo Epic E040 (async refactor) a E060 (rozšíření Describable).

## 6. Project-Level Definition of Done

Projekt je hotov, když:

- [ ] Všechny Epics E010 až E080 mají schválené report.
- [ ] `src/agentflow/statemachine/README.md` obsahuje quick-start, public API přehled, cookbook patternů.
- [ ] Existují minimálně **2 end-to-end demo skripty** v `src/examples/`:
  - jeden ilustrující paralelní research (fan-out/fan-in s Router patternem),
  - jeden ilustrující migraci existujícího `ToolAgent` na `StateGraph` přes `ToolAgentVertex`.
- [ ] **Pokrytí testy:** všechny veřejné moduly `statemachine/` mají jednotkové testy; integrační test alespoň jeden ne-trivální graf běží end-to-end s `FakeLlmConnector`.
- [ ] **Live vizualizace** běžícího grafu funguje (HTML/SVG s aktivním uzlem zvýrazněným per super-step).
- [ ] **mypy `--strict` projde** na celém `src/agentflow/statemachine/`.
- [ ] **`pyproject.toml`** obsahuje pinovanou závislost `frozendict` s komentářem zdůvodnění.
- [ ] **Brief, spec, roadmap, všechny epic reports** jsou aktuální a propojené v `src/agentflow/doc/project-progress/`.
