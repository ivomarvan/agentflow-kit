---
apm_category: glossary
apm_ref: PROJECT
apm_level: project
created_by: Planner
model: claude-opus-4-7
intended_for: All
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Glosář projektu agentflow.statemachine

Centrální slovník doménových pojmů. Při čtení APM dokumentů (spec, roadmap, plan, task spec, report) odsud čerpejte přesný význam jednotlivých termínů.

## Doménové pojmy

| Termín                | Definice |
|-----------------------|----------|
| **StateGraph**        | Topologie orchestrace: seznam přechodů (`Transition`) mezi vrcholy. Deklarativní, IDE-friendly. |
| **StateVertex**       | Bezstavový uzel grafu. Implementuje `async run(state, ctx) -> (signal, patch)`. |
| **State**             | Imutabilní snapshot dat workflow (`@dataclass(frozen=True)`). |
| **StatePatch**        | Popis změn stavu vrácený z vrcholu. Aplikovaný přes per-field reducery. |
| **Reducer**           | Čistá funkce `(old, new) -> merged` připojená k poli stavu přes `Annotated[T, reducer]`. |
| **EnumSignal**        | Typový alias `Enum` pro signály vracené vrcholy; používá se v `Transition`. |
| **Transition**        | Trojice `(From, Signal, To)` definující jednu hranu topologie. |
| **Parallel**          | Fan-out marker — aktivuje N větví v dalším super-kroku. |
| **End / StdEnd**      | Marker base / default implementace koncového uzlu. Runner zastaví hlavní smyčku po doběhnutí. |
| **Context**           | Sdílené služby (LLM connector, tools, logger, run_id) injektované do každého `run()`. |
| **StateGraphRunner**  | Spouštěcí jádro — implementuje BSP smyčku. |
| **VertexResolver**    | Interní singleton-per-class registr instancí pro auto-instanciaci tříd v topologii. |
| **RunnerHooks**       | Protocol pro asynchronní callbacky observability (super-step start/end, vertex error, run start/end). |
| **CheckpointStore**   | Protocol pro persistenci snapshotů stavu po každém super-kroku. |
| **Router (pattern)**  | Vzor: `StateVertex`, který nedělá business logiku, jen emituje state-dependent signály. |
| **Adapter**           | Vrchol obalující existující komponentu (`ToolBase`, `ToolAgent`) jako `StateVertex`. |

## APM pojmy (shrnutí pro rychlou referenci)

| Termín     | Definice |
|------------|----------|
| **Planner**| Role: plánování, dekompozice, příprava kontextu pro Coder. |
| **Coder**  | Role: implementace, testy, reporty. |
| **Epic**   | Tematický celek; číslovaný `E010`, `E020`, …; obsahuje seznam Tasků. |
| **Task**   | Atomická implementační jednotka; číslovaná `T010`, `T020`, …; má spec, dod a report. |
| **DoD**    | Definition of Done — checklist akceptačních kritérií tasku. |

## BSP / paralelismus

| Termín           | Definice |
|------------------|----------|
| **BSP**          | Bulk Synchronous Parallel — model „super-kroků" se třemi fázemi (Compute → Barrier → Apply&Route). |
| **Super-step**   | Jeden cyklus BSP smyčky: paralelní výpočet všech aktivních uzlů, synchronizace, aplikace patchů, určení dalších aktivních uzlů. |
| **Fan-out**      | Větvení toku z jednoho uzlu do více paralelních větví (`Parallel`). |
| **Fan-in / Join**| Sloučení paralelních větví zpět do jednoho uzlu. V tomto frameworku implicitní přes `set()` (viz §2.4 briefu). |
| **Race condition** | Konflikt nedeterministických zápisů do sdíleného stavu — BSP ho z principu eliminuje. |
