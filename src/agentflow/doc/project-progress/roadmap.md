---
apm_category: roadmap
apm_ref: PROJECT
apm_level: project
created_by: Planner
model: claude-opus-4-7
intended_for: All
created_at: 2026-05-28
updated_at: 2026-05-30
approved_by: Human
approved_at: 2026-05-28
---

# Roadmap — `agentflow.statemachine`

Posloupnost Epics vedoucích od prázdného balíčku k produktivnímu `agentflow.statemachine` modulu s end-to-end příklady. Číslování po 10 pro snadné vkládání mezi-epiků (`E015`, `E025`, …).

Závislosti mezi Epics jsou explicitně uvedeny; v rámci závislostí lze běžet sekvenčně, mimo závislosti paralelně (typicky E040 a E050 lze prohodit).

## Přehled — Phase 1: Framework core (E010–E080)

| Ref  | Název                                              | Závisí na   | Složitost | Stav      |
|------|----------------------------------------------------|-------------|-----------|-----------|
| E010 | Core StateGraph MVP (sync vrcholy, manuální instance) | —         | high      | ✅ done   |
| E020 | Auto-instanciace & topology validation             | E010        | medium    | ✅ done   |
| E030 | Observability hooks (full)                         | E010        | medium    | ✅ done   |
| E040 | Async LLM refactor across agentflow                | (E010)*     | high      | ✅ done   |
| E050 | Integration adapters (ToolCallVertex, …)           | E010, E040  | medium    | ✅ done   |
| E060 | Describable integration + live graph visualization | E010, E030  | medium    | ✅ done   |
| E070 | Checkpointing & pause/resume                       | E010, E030  | medium    | ✅ done   |
| E080 | Reference examples & documentation                 | E050, E060  | medium    | ✅ done   |

*) E040 je technicky nezávislý na E010, ale dává smysl ho spustit až po E010, protože E010 už definuje, kde se `LlmConnector` v `Context` použije.

## Přehled — Phase 2: Veřejné publikování (E090+)

| Ref  | Název                                              | Závisí na         | Složitost | Stav     | Priorita |
|------|----------------------------------------------------|--------------------|-----------|----------|----------|
| E090 | Příprava knihovny pro veřejné publikování          | E080               | medium    | planned  | 🔴 High  |
| E091 | PostgreSQL/Redis checkpoint backends               | E070, E090         | medium    | planned  | 🟡 Med   |
| E092 | LangChain ecosystem integration                   | E050, E090         | medium    | planned  | 🟡 Med   |
| E093 | Streaming LLM tokenů                               | E040, E090         | high      | planned  | 🟠 Later |
| E094 | LangGraph export / transpiler                      | E060, E090         | medium    | optional | 🟢 Nice  |

### Závislostní graf Phase 2

```
E080 (done)
  └── E090 (library prep — editable install, cleanup, README)
        ├── E091 (PostgreSQL/Redis checkpoints)
        ├── E092 (LangChain integration)
        ├── E093 (streaming tokens)
        └── E094 (LangGraph export, optional)
```

**Pravidlo pro srovnávací tabulku:** Každý nový Epic musí v DoD zahrnovat aktualizaci
srovnávací tabulky `agentflow vs LangGraph vs CrewAI` v `README.md`, pokud přidává
feature relevantní pro srovnání.

---

## Epic E010 — Core StateGraph MVP

**Cíl:** Funkční minimální runtime, do kterého se dá ručně sestavit graf z předem zinstancovaných vrcholů a spustit ho. Bez auto-instanciace, bez statické analýzy, bez observability hooks (jen no-op + základní logging).

**Klíčové výstupy:**
- Balíček `src/agentflow/statemachine/` se všemi public symboly z briefu §1–§3.
- `StateGraphRunner` implementující BSP smyčku (Compute → Barrier → Apply&Route).
- `ctx.run_sync(fn)` helper pro blokující IO (LLM, tools) — overlay na existující sync `LlmConnector`.
- Testovací utility `FakeVertex`, `FakeLlmConnector`, `FakeContext` v `statemachine/testing/`.
- Jednotkové testy pokrývající: reducery, runner BSP smyčka, parallel fan-out, set-based join, try/except mapping na fail signál, End semantika.

**Definition of Done (Epic-level):**
- Lze sestavit graf z briefu §2.5 (research → parallel write → review → loop) **z ručně předaných instancí**, spustit ho přes `runner.run_sync(initial_state)` a získat finální `State`.
- `pytest src/agentflow/tests/statemachine/` zelená.
- `mypy --strict src/agentflow/statemachine/` zelený.

**Složitost:** high — zakládá architekturu, na které stojí celý zbytek projektu.

---

## Epic E020 — Auto-instanciace & topology validation

**Cíl:** Zavést `VertexResolver` (singleton-per-class), dovolit psát do topologie třídy místo instancí, validovat default parametry s jasným error msg a provést statickou analýzu rizikových join topologií.

**Klíčové výstupy:**
- `VertexResolver` v `statemachine/resolver.py` — udržuje `dict[type[StateVertex], StateVertex]`.
- Validační hook v `StateGraph.__init__`: prochází `transitions`, pro každou třídu (ne instanci) volá `inspect.signature` a kontroluje default hodnoty.
- Statická analýza topologie: pro každý uzel s víc vstupními hranami počítá vzdálenost od fan-out předchůdce; při asymetrii emituje `logging.warning`.
- Aktualizovaný příklad používající **třídy** v `transitions` místo instancí.

**Závislost:** E010.

---

## Epic E030 — Observability hooks (full)

**Cíl:** Plnohodnotný `RunnerHooks` Protocol s implementacemi `NoOpHooks`, `LoggingHooks`, `RecorderHooks`.

**Klíčové výstupy:**
- `RunnerHooks` Protocol v `statemachine/hooks.py`.
- `RecorderHooks` se strukturou `SuperStepRecord(step, state_before, active_nodes, results, state_after, next_active)`.
- Pytest fixtura `recorded_runner` v `testing/`.
- Test ukazující asserci nad `recorder.history` (z briefu §7.3).

**Závislost:** E010. **Připravuje:** E060 (LiveGraphHooks navazují), E070 (Checkpoint může reuse `on_super_step_end`).

---

## Epic E040 — Async LLM refactor across agentflow

**Cíl:** Převést `LlmConnector` rodinu na async-first API. Vrcholy mohou nadále volat sync kód přes `ctx.run_sync`, ale primární cesta je `await ctx.connector.achat(...)`.

**Klíčové výstupy:**
- `LlmConnector.achat(...)` abstract method.
- `OpenAiConnector.achat`, `AnthropicConnector.achat` implementace (přes `openai.AsyncOpenAI` / `anthropic.AsyncAnthropic`).
- `ToolAgent` má `async arun(question)` (případně původní `run` deprecate s `asyncio.run` wrapperem).
- Aktualizovaná dokumentace, README.
- Zpětně kompatibilní: stávající sync `chat()` zůstává funkční (může být thin wrapper nad `asyncio.run(achat(...))`).

**Závislost:** logicky nezávislý na E010, ale prakticky se dělá až po E010, aby bylo jasné, kde se v `Context` použije.

**Pozor:** **vícesouborový refactor mimo `statemachine/`** — sahá do `src/agentflow/llm/`. Při implementaci dodržet pravidlo „nezasahovat do public API bez ADR".

---

## Epic E050 — Integration adapters

**Cíl:** Tři adaptery, které umožní použít existující `ToolBase` / `ToolAgent` jako `StateVertex` v grafu.

**Klíčové výstupy:**
- `ToolCallVertex` — obal jednoho `ToolBase` volání (args ze State → execute → result do StatePatch).
- `LlmTurnVertex` — jeden chat turn, žádný ReAct loop.
- `ToolAgentVertex` — obal celého `ToolAgent` jako jednoho vrcholu.
- Příklad: existující ReAct agent (`src/examples/.../my/02_tool_calling_demo.py`) přepsaný jako StateGraph s adaptery.

**Závislost:** E010 + E040 (kvůli async ToolAgent).

---

## Epic E060 — Describable integration + live graph visualization

**Cíl:** Vizualizace topologie a běhu skrz existující `describable` / `GraphRenderer`.

**Klíčové výstupy:**
- `StateGraph(Describable)`: `get_graph()` produkuje `Vertex`y per uzel + `Edge`y per `Transition` s `label=signal.name`. Parallel jako cluster.
- `LiveGraphHooks` aktualizující `Vertex.attributes["active"] = True` v Compute fázi.
- Rozšíření `GraphRenderer` o styling per-attribute (active node coloring).
- Demo: SVG/HTML snapshot grafu po každém super-kroku.

**Závislost:** E010 + E030.

---

## Epic E070 — Checkpointing & pause/resume

**Cíl:** Pluggable persistence stavu po každém super-kroku.

**Klíčové výstupy:**
- `CheckpointStore` Protocol v `statemachine/checkpoint.py`.
- `InMemoryCheckpointStore` — testy, debug.
- `JsonFileCheckpointStore` — `./checkpoints/<run_id>/<step>.json` (asyncio + aiofiles? nebo `asyncio.to_thread(json.dump)`).
- `SqliteCheckpointStore` (stretch goal — pouze pokud zbyde čas v Epicu).
- `runner.run_until(predicate)` + `runner.resume(run_id, from_step)`.
- Příklad human-in-the-loop: graf se zastaví před `Publish` uzlem, čeká na manuální `approve` ve volání `resume`.

**Závislost:** E010 + E030.

---

## Epic E080 — Reference examples & documentation

**Cíl:** End-to-end demo aplikace + cookbook + tutoriál.

**Klíčové výstupy:**
- `src/examples/statemachine_demos/` se 2 demo skripty:
  1. **Parallel research** — `Research` → `Parallel(WriteIntro, WriteBody)` → `Review` → loop.
  2. **ToolAgent migration** — existující `ToolAgent` zabalený do `ToolAgentVertex`.
- `src/agentflow/statemachine/README.md` — quick-start, public API, cookbook patternů (Router, Parallel, adapters).
- `src/agentflow/doc/guides/statemachine_tutorial.md` — step-by-step průvodce „od prvního grafu k paralelnímu researchi".
- Aktualizovaný hlavní `src/agentflow/README.md` se sekcí o `statemachine`.

**Závislost:** E050 + E060.

---

---

## Epic E090 — Příprava knihovny pro veřejné publikování

**Cíl:** Transformovat soukromý výukový projekt na publikovatelnou open-source knihovnu.
Editable install, čisté importy, veřejné README se srovnávací tabulkou.

**Klíčové výstupy:**
- `pyproject.toml` s `[tool.setuptools.packages.find] where = ["src"]`, editable install přes `uv pip install -e .`.
- Odstranění `git_root_to_syspath` / `agr()` ze všech ~30 souborů, oprava `from src.agentflow.` → `from agentflow.`.
- Vyčištění `src/projects/` od firemních referencí (Mama AI, Telma, Adéla).
- Přejmenování `src/examples/self_education/Agentni_systemy/` → `src/examples/patterns/`.
- Rewrite root `README.md` jako veřejný projekt.
- Srovnávací tabulka `agentflow vs LangGraph vs CrewAI` v README.

**Detail:** viz `epic-090-library-prep/plan.md`.

**Závislost:** E080 (vše dokončeno).

---

## Epic E091 — PostgreSQL/Redis Checkpoint Backends

**Cíl:** Přidat dva produkční checkpoint backendy nad existující `CheckpointStore` Protocol.

**Klíčové výstupy:**
- `PostgresCheckpointStore` (`asyncpg`) — tabulka `(run_id, step, state_json, active_nodes, created_at)`.
- `RedisCheckpointStore` (`redis.asyncio`) — klíče `checkpoint:{run_id}:{step:04d}`, volitelné TTL.
- Docker Compose služby pro integrační testy (`@pytest.mark.integration`).
- Sekce v `statemachine/README.md` — jak nastavit a použít každý backend.
- Aktualizace srovnávací tabulky (checkpointing backends).

**Složitost:** medium — implementace jsou přímočaré, hlavní práce je infrastruktura.

**Závislost:** E070, E090.

---

## Epic E092 — LangChain Ecosystem Integration

**Cíl:** Dovolit použití LangChain nástrojů a LLM modelů přímo v agentflow grafech.

**Klíčové výstupy:**
- `LangChainToolAdapter(tool: BaseTool)` → `ToolCallVertex`-kompatibilní adaptér.
  Umožní použít desítky existujících LC nástrojů (Tavily, Wikipedia, SerpAPI, …).
- `LangChainLLMConnector(llm: BaseChatModel)` → implementace `LlmConnector` Protocol.
  Podpora pro OpenAI, Anthropic, Groq, Ollama, Gemini — cokoli co LangChain podporuje.
- `langchain-core` jako optional dependency (`[project.optional-dependencies] langchain = [...]`).
- Příklad: existující ReAct agent s LC nástrojem zabalený v agentflow grafu.
- Aktualizace srovnávací tabulky (LangChain interop).

**Složitost:** medium — konceptuálně podobné E050 adaptérům.

**Závislost:** E050, E090.

---

## Epic E093 — Streaming LLM Tokenů

**Cíl:** Průběžné zobrazování tokenů z LLM během běhu vrcholu — bez porušení BSP bariéry.

**Klíčové výstupy:**
- `LlmConnector.astream(messages, ...) → AsyncIterator[str]` abstract method.
- `OpenAiConnector.astream` a `AnthropicConnector.astream` implementace.
- `RunnerHooks.on_vertex_token(node, token)` callback.
- `LlmTurnVertex` v streaming módu (volitelný parametr `stream=True`).
- Runner volá `on_vertex_token` průběžně, výsledný patch sestaví na konci (BSP bariéra zachována).
- Demo: streaming výstup v CLI.

**Složitost:** high — zasahuje do `LlmConnector` interfacu, Runner a Hooks.

**Závislost:** E040, E090.

---

## Epic E094 — LangGraph Export / Transpiler (optional)

**Cíl:** Možnost exportovat agentflow `StateGraph` do LangGraph syntaxe pro uživatele,
kteří chtějí migrovat nebo srovnat chování.

**Klíčové výstupy:**
- `StateGraph.to_langgraph_code() → str` — generuje Python source kód ekvivalentního LangGraph grafu.
- Mapování: `StateVertex` → `add_node`, `Transition` → `add_edge`/`add_conditional_edges`,
  `Parallel` → fan-out edges, frozen dataclass state → `TypedDict`.
- Dokumentovaná omezení (BSP vs event-driven sémantika, reducery).
- Příklad transpilace `04_parallel_research_loop.py` do LangGraph.

**Složitost:** medium — syntaktický překlad je přímočarý, sémantické rozdíly je třeba dokumentovat.

**Závislost:** E060, E090. `langgraph` jako optional dependency.

---

## Mimo roadmapu (deferred / vědomě odloženo)

| Položka | Důvod odložení |
|---------|---------------|
| Explicit `Join(...)` count-based barrier | WARNING ze statické analýzy zatím dostačuje |
| Distribuovaný BSP (multi-process/machine) | Out-of-scope pro vzdělávací knihovnu; zmíněno v srovnávací tabulce |
| GUI editor topologie | Visualizace přes `get_graph_html()` dostačuje |
| `SqliteCheckpointStore` | E091 přináší PostgreSQL; SQLite add-on lze přidat jako mini-task v E091 |
| pip publish na PyPI | Po E090 (editable install) je to 1-task práce; odkládáme na pozdější rozhodnutí |
