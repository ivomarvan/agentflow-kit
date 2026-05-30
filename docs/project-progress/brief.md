---
apm_category: project-brief
apm_ref: PROJECT
apm_level: project
created_by: Human
intended_for: Planner
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Architektura StateGraph pro orchestraci AI Agentů

Tento dokument popisuje deklarativní, objektově orientovaný framework připravený na paralelismus, který slouží k orchestraci LLM agentů. Návrh kombinuje silné typování, čistotu zápisu a robustní prováděcí model známý jako Bulk Synchronous Parallel (BSP).

Brief je výsledkem iterativní diskuse mezi Human a Planner; slouží jako vstup pro APM Phase 0 (formalizace do `spec.md` a `roadmap.md`).

## Motivace pro vývoj vlastního frameworku

Tento framework vzniká primárně jako **sebeedukační projekt**. Cílem není vyvinout plnohodnotnou produkční náhradu za existující systémy (jako jsou LangGraph, LlamaIndex Workflows nebo Burr), ale od základu a na vlastní kůži pochopit, **jak orchestrace AI agentů skutečně funguje**.

Vybudováním vlastního minimalistického, ale architektonicky čistého jádra:
1. Získáme hluboké porozumění tomu, jak se řeší stav, cykly a paralelní zpracování (fan-out/fan-in).
2. Odhalíme, proč složité produkční frameworky přijaly určitá architektonická rozhodnutí a jaké problémy tím řeší.
3. Budeme mít k dispozici nástroj, jehož vnitřní fungování je naprosto transparentní, bez vrstev "magie", které by zakrývaly podstatu věci.
4. Vznikne také několik konkrétních, **prakticky použitelných příkladů** postavených na tomto jádře.

## 1. Základní koncepty

Architektura je postavena na striktním oddělení čtyř zodpovědností:
1. **Stav (`State` & `StatePatch`):** Co systém ví (data).
2. **Kontext (`Context`):** Co systém má k dispozici (sdílené služby — LLM, tools, logger).
3. **Uzly (`StateVertex`):** Co systém dělá (exekuce/výpočet).
4. **Graf (`StateGraph`):** Jak tok řízení postupuje (směrování).

### 1.1 Stav (`State`) a `StatePatch` — imutabilita s per-field reducery

Stav je reprezentován jako **neměnná (imutabilní) datová struktura** (`@dataclass(frozen=True)`). Uzly nikdy nemodifikují stav přímo; vracejí `StatePatch` (popis změn).

V BSP super-kroku ale typicky přijde **více patchů od různých paralelních uzlů najednou**. Aby šlo bezpečně a deterministicky sloučit změny do nové verze stavu, používáme **per-field reducery**: každé pole stavu má přiřazený merge-operátor přes typovou anotaci `Annotated[T, reducer]`.

```python
from dataclasses import dataclass
from typing import Annotated
import operator

@dataclass(frozen=True)
class State:
    # Reducer = libovolná čistá funkce (old_value, new_value) -> merged_value
    messages: Annotated[tuple[str, ...], operator.add]   # konkatenace dvou tuple
    score:    Annotated[float, max]                      # vyšší vítězí
    author:   str                                        # bez reduceru = last-writer-wins
```

**Jak reducery fungují uvnitř runneru:**

V Compute fázi BSP super-kroku N běží paralelně N uzlů; každý vrátí `StatePatch`. V Apply fázi runner pro každé pole, které alespoň jeden patch nastavil:
1. Načte aktuální hodnotu ze stavu (`old`).
2. Postupně aplikuje reducer na každý patchem dodaný příspěvek: `merged = reducer(merged, new)`.
3. Vytvoří **novou instanci stavu** s mergovanými hodnotami (`dataclasses.replace`).

```python
@dataclass
class StatePatch:
    messages: tuple[str, ...] | None = None
    score:    float | None = None
    author:   str | None = None
```

- **Pole s reducerem** (asociativní/komutativní operace): merge je deterministický bez ohledu na pořadí patchů. Doporučené reducery: `operator.add` pro `tuple`, `max`/`min` pro skóre, `frozenset.union` pro množiny, vlastní funkce pro složitější domény.
- **Pole bez reduceru** (jako `author: str`): default = **last-writer-wins**. Runner v takovém případě vypíše `WARNING`, pokud v jednom super-kroku přišlo víc nenulových hodnot, protože pořadí mergu je nedeterministické. Uživatel tím dostane signál, že má buď přidat reducer, nebo zajistit, aby pole psal vždy jen jeden uzel.

**Sentinel pro „nesetuj":** rozlišení mezi „pole nebylo v patchi nastaveno" a „pole bylo explicitně nastaveno na `None`/0" řešíme **konvencí** — `None` v `StatePatch` znamená „nenastavovat". Pro pole, kde `None` je validní hodnota, se zavádí vlastní sentinel (`UNSET = object()`).

### 1.2 Imutabilní kontejnery ve stavu

`@dataclass(frozen=True)` zakáže reassignment atributů, ale **neimmutuje obsah kontejnerů**. Aby uzel omylem nemodifikoval seznam sdílený se sourozeneckým uzlem v Compute fázi, používáme striktně imutabilní typy:

| Mutabilní      | Imutabilní náhrada    | Původ                |
|----------------|----------------------|----------------------|
| `list[T]`      | `tuple[T, ...]`      | stdlib               |
| `set[T]`       | `frozenset[T]`       | stdlib               |
| `dict[K, V]`   | `frozendict[K, V]`   | pypi `frozendict`    |

`frozendict` doplňujeme jako jedinou novou závislost. Alternativou bez závislosti je `types.MappingProxyType`, ta je ale jen read-only **view** na mutable dict (méně bezpečná a snadno obejitelná).

### 1.3 Signály (směrování)

Vrcholy vracejí spolu s patchem **signál**, který runner použije k navigaci v topologii. Signály jsou Enum třídy. Protože Python **zakazuje subclassing Enum tříd s členy**, používáme typový alias jako značku:

```python
from enum import Enum, auto
from typing import TypeAlias

EnumSignal: TypeAlias = Enum  # marker pro typovou anotaci v signaturách framework metod

class StdSignal(EnumSignal):
    ok = auto()
    fail = auto()
    done = auto()

class CustomSignal(EnumSignal):
    approved = auto()
    rejected = auto()
```

Kdekoli framework očekává „nějaký signál", anotuje to jako `EnumSignal`. Konkrétními hodnotami jsou pak instance libovolné Enum třídy — `StdSignal.ok`, `CustomSignal.approved`, …

### 1.4 Kontext (`Context`) — sdílené služby

Uzly potřebují přístup ke sdíleným službám: LLM connector, registry tools, logger, run-id pro trasování, případně cancellation token. `Context` je typovaný dataclass, který runner injektuje do každého `run()`:

```python
from dataclasses import dataclass, field
import logging, uuid
from typing import Optional, Callable, Any

from src.agentflow import LlmConnector, ToolRegistry

@dataclass
class Context:
    """Sdílené služby předávané každému StateVertex při běhu grafu."""
    connector:    LlmConnector
    tools:        Optional[ToolRegistry] = None
    logger:       logging.Logger = field(default_factory=lambda: logging.getLogger("statemachine"))
    run_id:       str = field(default_factory=lambda: uuid.uuid4().hex)
    cancellation: Optional["CancellationToken"] = None

    async def run_sync(self, fn: Callable[..., Any], *args, **kwargs) -> Any:
        """Helper pro spuštění blokujícího (sync) kódu z async vrcholu.

        Dokud Epic E040 nepřevede `LlmConnector.chat()` na async, vrcholy volají
        blokující IO (LLM, tools) skrz tento helper. Interně `asyncio.to_thread`.
        Po dokončení E040 zůstává metoda zachována pro user-supplied sync libraries.
        """
        import asyncio
        return await asyncio.to_thread(fn, *args, **kwargs)
```

Pro pokročilejší DI lze podědit od `Context` a přidat aplikačně specifické služby (DB session, secrets store, metric collector). Vrcholy si pak vyžádají vlastní typ kontextu přes typovou anotaci `run(state, ctx: MyContext)`.

### 1.5 Uzly (`StateVertex`)

Každý uzel je potomkem `StateVertex`:
- **Z hlediska byznys logiky bezstavový** (stateless) — veškerý běžící stav patří do `State`. Atributy uzlu slouží pouze pro konfiguraci (např. `max_retries`).
- Metoda `async run(state, ctx)` vrací n-tici `(EnumSignal, StatePatch)`.
- **Všechny parametry konstruktoru MUSÍ mít default hodnoty** — to je předpoklad pro auto-instanciaci frameworkem (viz §2.3). Pokud uživatel deklaruje uzel v topologii jako třídu (ne instanci) a konstruktor má povinný parametr, runner při sestavování grafu vyhodí jasnou chybu:
  > *„StateVertex `Research` má povinný parametr `api_key` bez default hodnoty. Buď přidej default, nebo do topologie předej hotovou instanci `Research(api_key=...)` místo třídy."*

```python
from abc import ABC, abstractmethod

class StateVertex(ABC):
    @abstractmethod
    async def run(self, state: State, ctx: Context) -> tuple[EnumSignal, StatePatch]:
        ...

class Research(StateVertex):
    def __init__(self, max_results: int = 5):  # default → auto-instanciace OK
        self.max_results = max_results

    async def run(self, state, ctx) -> tuple[EnumSignal, StatePatch]:
        # blokující sync volání jdou skrz ctx.run_sync (viz §1.4 a §6)
        response = await ctx.run_sync(ctx.connector.chat, [...])
        return StdSignal.ok, StatePatch(messages=("Data nalezena",))
```

**Ošetření výjimek ve vrcholech:** runner každé volání `node.run(...)` obalí `try/except`. Pokud uzel vyhodí nečekanou výjimku, runner:
1. Zaznamená ji do `ctx.logger.exception(...)`.
2. Zavolá `RunnerHooks.on_vertex_error(node, exc)` (viz §3.3).
3. Vyrobí náhradní výsledek `(StdSignal.fail, StatePatch())`.

Tím se nezhroutí celý super-krok a uživatel může výjimečnou cestu routovat přes `StdSignal.fail`. Pole `error` ve `StatePatch` je volitelná konvence — runner ho nevyžaduje.

### 1.6 Konečné uzly (`End` a `StdEnd`)

Konec běhu je reprezentovaný **běžným `StateVertex`** se speciální sémantikou — runner ho rozpozná podle dědičnosti od `End`. Tím se vyhneme magickým sentinelům a uživatel může konec přizpůsobit (např. naformátovat finální odpověď ze stavu, poslat notifikaci, zavřít databázové spojení).

```python
class End(StateVertex):
    """Marker base — runner zastaví hlavní smyčku, jakmile End uzel doběhne."""

class StdEnd(End):
    """Default konec: nedělá nic, vrátí prázdný patch."""
    async def run(self, state, ctx):
        return StdSignal.done, StatePatch()

class AnswerEnd(End):
    """Uživatelský konec: zaloguje finální odpověď ze stavu."""
    async def run(self, state, ctx):
        ctx.logger.info("Final answer: %s", state.messages[-1])
        return StdSignal.done, StatePatch()
```

V topologii se `End` (bez dalšího upřesnění) chápe jako alias pro `StdEnd` — `Transition(Review, ..., End)` → framework auto-instanciuje `StdEnd()`.

## 2. Deklarace topologie (`StateGraph`)

Graf je definovaný jako seznam přechodů (`Transition`). Zápis stojí na explicitních objektech, díky čemuž ho IDE rozpoznává a podporuje refactoring.

### 2.1 `Transition` (From, Signal, To)

```python
Transition(Research, StdSignal.ok, Review)
```

- `From`: třída nebo instance `StateVertex`.
- `Signal`: konkrétní hodnota `EnumSignal`.
- `To`: třída/instance `StateVertex`, instance `Parallel(...)`, nebo třída/instance `End`.

### 2.2 `Parallel` (fan-out)

`Parallel` je třída; zápis `Parallel(WriteIntro, WriteBody)` je její konstruktor. Drží seznam větví a v Apply&Route fázi runneru je rozbalí do množiny aktivních uzlů příštího super-kroku.

```python
class Parallel:
    """Fan-out marker: aktivuje všechny větve v dalším super-kroku."""

    def __init__(self, *vertices: type[StateVertex] | StateVertex) -> None:
        self.vertices = vertices

    def expand(self, resolver: "VertexResolver") -> list[StateVertex]:
        """Rozbalí (a auto-instanciuje) všechny větve na konkrétní instance."""
        return [resolver.resolve(v) for v in self.vertices]
```

`Transition(Research, StdSignal.ok, Parallel(WriteIntro, WriteBody))` znamená: po doběhnutí `Research` se v dalším super-kroku spustí `WriteIntro` a `WriteBody` paralelně, oba se stejným snapshotem stavu.

### 2.3 Auto-instanciace tříd (singleton-per-class)

Když uživatel napíše do topologie třídu (`Research`), framework si ji zapamatuje a **při prvním použití auto-instanciuje s defaulty**. Stejnou instanci pak vrací při každém dalším odkazu na tutéž třídu. Z hlediska identity se tedy třídy v topologii chovají jako **singleton-per-class** (vzor Flyweight) — udržuje je interní `VertexResolver` v rámci jednoho `StateGraph`.

**Důsledek pro fan-in:** pokud dvě paralelní větve směřují stejným signálem na třídu `Review`, runner ve fázi Apply&Route vloží do `set()` **identickou instanci `Review`**, takže se v dalším super-kroku spustí jen jednou. Implicitní join tak funguje pro běžné případy bez další konfigurace, **díky tomu, že auto-instanciace je deterministická a sdílená v rámci grafu**.

Pokud uživatel chce explicitní kontrolu (např. dvě nezávislé instance téhož typu se samostatnou konfigurací), předá instance přímo:

```python
explorer_a = Explorer(seed=1)
explorer_b = Explorer(seed=2)
Transition(Plan, StdSignal.ok, Parallel(explorer_a, explorer_b))
```

### 2.4 Omezení implicitního joinu — varování při statické analýze

Set-based join funguje **spolehlivě jen v případě, kdy obě (či více) paralelních větví doběhnou v tomtéž super-kroku**. To je splněno typicky tehdy, když větve vzniknou ze stejného `Parallel(...)` fan-outu a obsahují **stejný počet** kroků.

Pokud topologie vede k tomu, že větve mají různou délku (např. jedna obsahuje cyklus), může cílový uzel běžet **vícekrát**, pokaždé nad odlišným snapshotem stavu. To není vada BSP, ale **vlastnost zvoleného (jednoduchého) join modelu**.

**Framework provede statickou analýzu topologie před prvním během** a na rizikové uzly upozorní `WARNING`em:
> *„Uzel `Review` má víc vstupních přechodů z větví různé hloubky. Může se spustit vícekrát. Pokud potřebuješ barrier semantics, použij explicitní `Join(WriteIntro, WriteBody)` (zatím neimplementováno) nebo zajistí symetrii větví."*

Explicitní `Join` (count-based barrier, který čeká, až dorazí signály ze všech očekávaných předchůdců) je naplánovaný jako **budoucí rozšíření**, ne MVP.

### 2.5 Příklad kompletního grafu

```python
from src.agentflow.statemachine import (
    StateGraph, Transition, Parallel, StdSignal, StdEnd, Context
)
from my_app.signals import CustomSignal
from my_app.nodes import Research, WriteIntro, WriteBody, Review

state_graph = StateGraph(
    start=Research,
    transitions=[
        Transition(Research,   StdSignal.ok,          Parallel(WriteIntro, WriteBody)),
        Transition(Research,   StdSignal.fail,        StdEnd),

        Transition(WriteIntro, StdSignal.done,        Review),
        Transition(WriteBody,  StdSignal.done,        Review),

        Transition(Review,     CustomSignal.approved, StdEnd),
        Transition(Review,     CustomSignal.rejected, Research),   # cyklus
    ],
)
```

*(Pro stručnost lze využít import aliasing: `from ... import Transition as T, Parallel as P`. Plné názvy jsou ale doporučené pro srozumitelnost a odstranění „magie".)*

## 3. Prováděcí model: Bulk Synchronous Parallel (BSP)

O vykonávání grafu se stará `StateGraphRunner`. Používá model **Bulk Synchronous Parallel (BSP)**, známý také jako Super-step model.

### 3.1 Proč BSP a ne běžný Fork-Join?

Naivní Fork-Join při narazení na `Parallel` odštěpí vlákna a běží nezávisle. V grafech s cykly a podmínkami to vede k *race conditions* nad sdíleným stavem.

**BSP řeší problém tím, že čas neplyne spojitě, ale v "tazích" (super-krocích).** Každý super-krok má tři fáze:

1. **Compute:** Všechny aktivní uzly dostanou **identickou „fotografii" stavu** a běží paralelně, zcela izolovaně. Nikdo stav neupravuje.
2. **Barrier (Synchronize):** Runner čeká, až doběhne i nejpomalejší uzel.
3. **Apply & Route:** Patche se přes per-field reducery sloučí do nové verze stavu (§1.1). Signály se přes topologii přemapují na **množinu** (`set()`) cílových uzlů, čímž se implicitně provede fan-in (§2.3, §2.4).

Tento přístup eliminuje race conditions a zjednodušuje fan-in pro symetrické větve.

### 3.2 Pseudokód realizace BSP

```python
import asyncio

class StateGraphRunner:
    def __init__(
        self,
        graph: StateGraph,
        context: Context,
        hooks: "RunnerHooks | None" = None,
    ) -> None:
        self.graph = graph
        self.context = context
        self.hooks = hooks or NoOpHooks()

    async def run(self, initial_state: State) -> State:
        current_state = initial_state
        active_nodes: list[StateVertex] = [self.graph.resolve_start()]
        step = 0

        await self.hooks.on_run_start(initial_state)

        while active_nodes:
            # Oddělíme End uzly: necháme je doběhnout, ale zařadíme je mimo cyklus
            end_nodes = [n for n in active_nodes if isinstance(n, End)]
            for end in end_nodes:
                await self._safe_run(end, current_state)
            active_nodes = [n for n in active_nodes if not isinstance(n, End)]
            if not active_nodes:
                break

            step += 1
            await self.hooks.on_super_step_start(step, current_state, active_nodes)

            # --- PHASE 1: COMPUTE (parallel) ---
            results = await asyncio.gather(
                *(self._safe_run(node, current_state) for node in active_nodes)
            )

            # --- PHASE 2 already happened (gather barrier) ---

            # --- PHASE 3A: APPLY (per-field reducers) ---
            patches = [patch for _, patch in results]
            current_state = self.graph.apply_patches(current_state, patches)

            # --- PHASE 3B: ROUTE (set-based implicit join) ---
            next_set: set[StateVertex] = set()
            for node, (signal, _) in zip(active_nodes, results):
                for target in self.graph.get_targets(node, signal):
                    next_set.update(self.graph.expand_target(target))   # rozbalí Parallel

            await self.hooks.on_super_step_end(step, current_state, next_set)
            active_nodes = list(next_set)

        await self.hooks.on_run_end(current_state)
        return current_state

    async def _safe_run(
        self, node: StateVertex, state: State
    ) -> tuple[EnumSignal, StatePatch]:
        """Volání run() s ošetřením výjimek → mapuje na (fail, prázdný patch)."""
        try:
            return await node.run(state, self.context)
        except Exception as exc:
            self.context.logger.exception("Vertex %s failed", type(node).__name__)
            await self.hooks.on_vertex_error(node, exc)
            return StdSignal.fail, StatePatch()
```

**Convenience sync entry-point:** pro CLI a skripty, které nechtějí řešit event loop, je k dispozici `runner.run_sync(state)` (interně `asyncio.run(self.run(state))`).

### 3.3 Hooks pro observability

Spouštěcí jádro je deklarativní, ale pro reálné použití potřebujeme **viditelnost do běhu**. `RunnerHooks` je rozhraní pro asynchronní callbacky volané v klíčových bodech:

```python
from typing import Protocol

class RunnerHooks(Protocol):
    async def on_run_start(self, state: State) -> None: ...
    async def on_super_step_start(
        self, step: int, state: State, active: list[StateVertex]
    ) -> None: ...
    async def on_vertex_error(self, node: StateVertex, exc: Exception) -> None: ...
    async def on_super_step_end(
        self, step: int, state: State, next_active: set[StateVertex]
    ) -> None: ...
    async def on_run_end(self, state: State) -> None: ...
```

Implementace, které je rozumné mít „v krabici":

- `NoOpHooks` — default; všechno je `pass`.
- `LoggingHooks` — strukturované logy přes `logging` (DEBUG pro detail, INFO pro milníky super-kroků).
- `RecorderHooks` — záznam celé historie super-kroků (active nodes, signály, patches, state diffs) pro testy a debugging.
- `LiveGraphHooks` — průběžně aktualizují `Vertex.attributes["active"] = True` v `Describable` grafu pro **živou vizualizaci běhu** v `GraphRenderer`.

Hooks jsou **volitelné** (default = no-op). Tím MVP zůstává jednoduché a kdo chce observability, dostane ji bez zásahu do jádra.

## 4. Conditional routing — `Router` jako vzor (ne nový framework koncept)

Routování podle **stavu** (ne jen podle signálu) řešíme **bez nového jazyka v topologii** — vrchol `Router(StateVertex)` jednoduše vyrobí různé signály podle stavu a topologie zůstává čistě signal-driven.

```python
class ReviewRouter(StateVertex):
    """Rozhoduje podle skóre, kam dál. Vrací jen signál, žádný patch."""

    async def run(self, state, ctx) -> tuple[EnumSignal, StatePatch]:
        if state.score > 0.8:
            return CustomSignal.approved,     StatePatch()
        if state.score > 0.5:
            return CustomSignal.needs_refine, StatePatch()
        return CustomSignal.rejected,         StatePatch()


# Topologie:
state_graph = StateGraph(
    start=Research,
    transitions=[
        Transition(Review,       StdSignal.done,            ReviewRouter),
        Transition(ReviewRouter, CustomSignal.approved,     StdEnd),
        Transition(ReviewRouter, CustomSignal.needs_refine, Refine),
        Transition(ReviewRouter, CustomSignal.rejected,     Research),
    ],
)
```

**Výhody tohoto přístupu:**
- Žádný nový framework koncept (`ConditionalTransition`, lambdy v topologii).
- Router je normální vrchol → integruje se s `Describable` (uzel s vícero výstupními hranami), je testovatelný, dokumentovatelný docstringem.
- V grafu je explicitně vidět **„zde se větví podle stavu"**.

**Konvence:** doporučená pojmenovací konvence je sufix `Router` (`ReviewRouter`, `RetryRouter`). V cookbooku (§9) bude tento vzor explicitně předveden jako recept.

## 5. Checkpointing — pluggable `CheckpointStore` Protocol

Reálné agentní workflow běží desítky vteřin až minuty. Bez checkpointingu znamená pád procesu restart od nuly a není možné implementovat human-in-the-loop pauzu.

### 5.1 Protocol

```python
from typing import Protocol

class CheckpointStore(Protocol):
    """Úložiště snapshotů stavu po každém super-kroku.

    Jeden run_id = jedna sekvence checkpointů indexovaná číslem super-kroku.
    """
    async def save(self, run_id: str, step: int, state: State) -> None: ...
    async def load(self, run_id: str, step: int) -> State: ...
    async def list_steps(self, run_id: str) -> list[int]: ...
    async def delete(self, run_id: str) -> None: ...
```

Runner volá `store.save(run_id, step, current_state)` na konci každého super-kroku (z `on_super_step_end` hooku nebo přímo z jádra — finální umístění rozhodneme při implementaci E070).

### 5.2 Implementace v MVP a později

| Implementace | Plán | Použití |
|---|---|---|
| `InMemoryCheckpointStore` | E070 MVP | testy, debug, single-process replay |
| `JsonFileCheckpointStore` | E070 MVP | jednoduchá persistence pro skripty (`./checkpoints/<run_id>/<step>.json`) |
| `SqliteCheckpointStore`   | E070 stretch | indexovaný query po run_id/step, atomické zápisy |

Postgres/Redis backendy nejsou součástí plánu — pro edukativní projekt overkill.

### 5.3 Pause/Resume API

Postavené nad `CheckpointStore`:

```python
state = await runner.run_until(initial_state, condition=lambda s: needs_human_review(s))
# … čekání na externí event (např. HTTP call /approve) …
final = await runner.resume(run_id="abc", from_step=4, state_overrides={...})
```

`run_until` přidá do hlavní smyčky předikát na pause-after. `resume` načte stav z `CheckpointStore` a pokračuje od daného super-kroku.

## 6. Async LLM refactor — vlastní Epic (E040)

Existující `LlmConnector.chat()` je **synchronní**. V MVP runneru (E010) se s tím vrcholy vyrovnávají voláním `await ctx.run_sync(connector.chat, ...)` (interně `asyncio.to_thread`).

**Plánovaný refactor:** v rámci Epicu **E040 (Async LLM refactor)**:
1. Přidat `async def achat(...)` do abstraktního `LlmConnector` rozhraní.
2. Implementovat ve všech konkrétních konektorech: `OpenAiConnector`, `AnthropicConnector`, Ollama varianta v `OpenAiConnector`.
3. Aktualizovat `ToolAgent` na async loop (nebo paralelní async variantu `AsyncToolAgent`).
4. Po dokončení migrace zůstává `ctx.run_sync` zachován pro uživatelské sync knihovny (tools, vlastní HTTP klienti, …).

**Rationale pro odložení do vlastního Epicu:** sahá to do celého `agentflow`, ne jen do statemachine podknihovny. Nechceme blokovat StateGraph MVP na refactoringu connectorů.

## 7. Testovací strategie

Vše v samostatném modulu `src/agentflow/statemachine/testing/`.

### 7.1 Stavební kameny

| Utility | Účel |
|---|---|
| `FakeVertex(signal, patch)` | Vrcholová zástavka, která vrací předdefinovaný výsledek; test topologie bez business logiky. |
| `FakeLlmConnector(responses=[...])` | Connector vracející předdefinovanou frontu odpovědí; bez sítě. |
| `FakeContext(**overrides)` | Tovární funkce — hotový `Context` s `FakeLlmConnector`, `MemoryHandler` loggerem atd. |
| `RecorderHooks` | Záznam celé historie super-kroků pro asserce (sdíleno s observability). |

### 7.2 pytest fixtury

```python
# conftest.py (src/agentflow/tests/statemachine/)
@pytest.fixture
def fake_ctx() -> Context: ...
@pytest.fixture
def recorded_runner(fake_ctx) -> tuple[StateGraphRunner, RecorderHooks]: ...
@pytest.fixture
def make_state_graph() -> Callable[..., StateGraph]: ...
```

### 7.3 Ukázkový test (cílový tvar)

```python
def test_research_loop_terminates_after_three_rejections(recorded_runner, fake_ctx):
    runner, recorder = recorded_runner
    fake_ctx.connector.queue_responses([
        "research_data_1",
        "intro_1", "body_1",
        "rejected",
        # …
    ])
    final_state = runner.run_sync(initial_state)

    history = recorder.history
    assert sum(1 for step in history if any(isinstance(n, Review) for n in step.active)) == 3
    assert isinstance(history[-1].active[0], StdEnd)
```

## 8. Navrhovaná struktura balíčku

Aby se framework čistě integroval do existujícího `agentflow`, doporučená struktura:

```
src/agentflow/statemachine/
├── __init__.py                  # public re-exporty
├── state.py                     # State helpers, StatePatch, reducer dispatch
├── signal.py                    # EnumSignal alias, StdSignal
├── context.py                   # Context dataclass + ctx.run_sync
├── vertex.py                    # StateVertex ABC, End, StdEnd
├── topology.py                  # Transition, Parallel, StateGraph
├── resolver.py                  # VertexResolver (singleton-per-class)
├── runner.py                    # StateGraphRunner s BSP smyčkou
├── hooks.py                     # RunnerHooks Protocol + NoOpHooks/LoggingHooks/RecorderHooks
├── checkpoint.py                # CheckpointStore Protocol + InMemory/JsonFile implementace
├── adapters/                    # Integrace s ToolBase/ToolAgent
│   ├── __init__.py
│   ├── tool_call_vertex.py      # ToolCallVertex (1 tool, žádný LLM)
│   ├── llm_turn_vertex.py       # LlmTurnVertex (1 chat turn, žádný loop)
│   └── tool_agent_vertex.py     # ToolAgentVertex (obal celého ToolAgent)
└── testing/
    ├── __init__.py
    ├── fakes.py                 # FakeVertex, FakeLlmConnector, FakeContext
    └── conftest_helpers.py      # fixture factories
```

**Pojmenovací konvence:** ponecháváme `StateVertex` (ne `StateNode`) z důvodu konzistence s briefem; kolizi s existujícím `agentflow.describable.Vertex` řešíme namespacem (`statemachine.StateVertex` vs `describable.Vertex`) a v public exportu `agentflow/__init__.py` rozhodneme, co re-exportovat (pravděpodobně **oba** pod plně kvalifikovaným jménem).

## 9. Integrace s existujícím `agentflow` (tools, agents)

Aby StateGraph nepřinesl paralelní svět a uměl spolupracovat s `ToolBase` / `ToolAgent`, dodáme tři adaptery:

| Adapter | Účel |
|---|---|
| `ToolCallVertex(tool: ToolBase, args_from_state: Callable, result_to_patch: Callable)` | Obal jednoho tool volání. Bez LLM. Užitečné pro deterministické kroky. |
| `LlmTurnVertex(messages_from_state, response_to_patch, *, tools=None)` | Jeden chat turn. Bez ReAct loopu. Pro jemnozrnnou orchestraci. |
| `ToolAgentVertex(agent: ToolAgent, question_from_state, answer_to_patch)` | Obal celého `ToolAgent` jako jediného vrcholu. Hrubá granularita, ale nejjednodušší migrace existujících agentů. |

Tyto adaptery budou součástí Epicu **E050 (Integration adapters)**.

## 10. Integrace s `describable` / `GraphRenderer`

Existující `describable.Graph` s `Vertex` + `Edge` (`label`, `attributes`) je **přesně to**, co StateGraph potřebuje k vizualizaci. Plán integrace v Epicu **E060**:

1. `StateGraph(Describable)` přepíše `get_graph()` → produkuje:
   - `Vertex` per registrovaný uzel (label = třída, description = item dict vrcholu),
   - `Edge` per `Transition` s `label=signal.name` a `attributes={"signal_class": ..., "is_parallel_branch": ...}`,
   - cluster vrchol per `Parallel(...)` přes `Vertex.children`.
2. **Live mód** — `LiveGraphHooks` mění `Vertex.attributes["active"] = True` během Compute fáze. `GraphRenderer` se rozšíří o styling podle `attributes` (např. zelená výplň pro aktivní uzel v daném super-kroku).
3. Snapshot stavu po každém super-kroku půjde zobrazit jako navigovatelný timeline (postaveno nad `RecorderHooks`).

## 11. Mimo MVP — explicitně odložené

- **Explicitní `Join(...)`** (count-based barrier) — zatím vystačí WARNING ze statické analýzy (§2.4).
- **Streaming LLM tokenů** uvnitř vrcholů — řešitelné jako rozšíření `LlmTurnVertex` po E040.
- **Distribuovaný BSP** (uzly v různých procesech/strojích) — out-of-scope.
- **Plnohodnotná retry/back-off politika** — uzel si ji řeší sám (typicky parametrem `__init__`).
