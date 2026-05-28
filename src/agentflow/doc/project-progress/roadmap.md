---
apm_category: roadmap
apm_ref: PROJECT
apm_level: project
created_by: Planner
model: claude-opus-4-7
intended_for: All
created_at: 2026-05-28
updated_at: 2026-05-28
approved_by: Human
approved_at: 2026-05-28
---

# Roadmap — `agentflow.statemachine`

Posloupnost Epics vedoucích od prázdného balíčku k produktivnímu `agentflow.statemachine` modulu s end-to-end příklady. Číslování po 10 pro snadné vkládání mezi-epiků (`E015`, `E025`, …).

Závislosti mezi Epics jsou explicitně uvedeny; v rámci závislostí lze běžet sekvenčně, mimo závislosti paralelně (typicky E040 a E050 lze prohodit).

## Přehled

| Ref  | Název                                              | Závisí na   | Složitost | Stav     |
|------|----------------------------------------------------|-------------|-----------|----------|
| E010 | Core StateGraph MVP (sync vrcholy, manuální instance) | —         | high      | planned  |
| E020 | Auto-instanciace & topology validation             | E010        | medium    | planned  |
| E030 | Observability hooks (full)                         | E010        | medium    | planned  |
| E040 | Async LLM refactor across agentflow                | (E010)*     | high      | planned  |
| E050 | Integration adapters (ToolCallVertex, …)           | E010, E040  | medium    | planned  |
| E060 | Describable integration + live graph visualization | E010, E030  | medium    | planned  |
| E070 | Checkpointing & pause/resume                       | E010, E030  | medium    | planned  |
| E080 | Reference examples & documentation                 | E050, E060  | medium    | planned  |

*) E040 je technicky nezávislý na E010, ale dává smysl ho spustit až po E010, protože E010 už definuje, kde se `LlmConnector` v `Context` použije.

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

## Mimo roadmapu (deferred)

- Explicit `Join(...)` count-based barrier.
- Streaming LLM tokenů uvnitř `LlmTurnVertex`.
- Distribuovaný BSP.
- GUI editor topologie.
- Postgres/Redis backendy pro `CheckpointStore`.

Tyto položky se vrátí na roadmapu, pokud konkrétní use-case ukáže jejich potřebu.
