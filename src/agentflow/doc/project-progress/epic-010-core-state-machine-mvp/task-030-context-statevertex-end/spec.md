---
apm_category: task-spec
apm_ref: E010.T030
apm_level: task
created_by: Planner
model: claude-opus-4-7
intended_for: Coder
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Task Specification: E010.T030 — Context + StateVertex + End/StdEnd

## 1. Goal

Implementovat tři stavební kameny dle briefu §1.4–§1.6:

1. **`Context`** — typovaný dataclass s injektovanými sdílenými službami (LlmConnector, ToolRegistry,
   logger, run_id) a `async run_sync(fn, *args, **kwargs)` helperem pro blokující IO.
2. **`StateVertex`** — abstraktní bázová třída pro uzly grafu s metodou `async run(state, ctx)`.
3. **`End`** (marker subclass) a **`StdEnd`** (default konec) — terminální uzly.

Cílem je poskytnout rozhraní, na němž závisejí T040 (topology) a T050 (runner).

## 2. Inputs

- `src/agentflow/doc/project-progress/brief.md` — §1.4 (Context), §1.5 (StateVertex), §1.6 (End/StdEnd).
- `src/agentflow/doc/project-progress/spec.md` — TD-07 (async vrcholy, run_sync), TD-08 (End jako StateVertex).
- `src/agentflow/statemachine/signal.py` — `StdSignal` (použit v `StdEnd.run()`).
- `src/agentflow/llm/LlmConnector.py` — pro typ `Context.connector`.
- `src/agentflow/tools/ToolRegistry.py` — pro typ `Context.tools`.
- `pyproject.toml` — konfigurace mypy, pytest.
- `.cursor/rules/10-python.mdc` — Python coding standards.

## 3. Outputs

### 3.1 Modifikované soubory

- `src/agentflow/statemachine/context.py` — **kompletní implementace**.
- `src/agentflow/statemachine/vertex.py` — **kompletní implementace**.
- `src/agentflow/statemachine/__init__.py` — přidat `Context`, `StateVertex`, `End`, `StdEnd` do re-exportů.

### 3.2 Nové soubory

- `src/agentflow/tests/statemachine/test_context.py` — 3 unit testy.
- `src/agentflow/tests/statemachine/test_vertex_endings.py` — 3 unit testy.

### 3.3 Detaily obsahu

#### `context.py`

```python
"""Shared runtime services injected into every vertex run() call.

Context carries the LLM connector, tool registry, logger, and a unique run
identifier. It also exposes run_sync() to bridge blocking sync code into the
async BSP loop — used until Epic E040 converts LlmConnector to async-first.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.agentflow.llm.LlmConnector import LlmConnector
from src.agentflow.tools.ToolRegistry import ToolRegistry


@dataclass
class Context:
    """Shared services container injected into every StateVertex.run() call.

    Args:
        connector: LLM connector for all LLM calls within the graph run.
        tools: Optional tool registry; None if the graph uses no tools.
        logger: Logger instance; defaults to 'statemachine' logger.
        run_id: Unique identifier for this graph run; auto-generated if omitted.
    """
    connector: LlmConnector
    tools: ToolRegistry | None = None
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("statemachine")
    )
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    async def run_sync(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run a blocking sync callable from an async vertex without blocking the event loop.

        Wraps fn(*args, **kwargs) in asyncio.to_thread so the BSP event loop
        remains unblocked while waiting for slow sync I/O (LLM calls, tools).
        Remains useful after Epic E040 for user-supplied sync libraries.

        Args:
            fn: Synchronous callable to execute in a thread pool.
            *args: Positional arguments forwarded to fn.
            **kwargs: Keyword arguments forwarded to fn.

        Returns:
            Return value of fn(*args, **kwargs).
        """
        return await asyncio.to_thread(fn, *args, **kwargs)
```

#### `vertex.py`

```python
"""StateVertex ABC and End/StdEnd terminal nodes.

All user-defined graph nodes inherit from StateVertex. The runner identifies
the end of execution by isinstance(node, End) — no magic sentinels needed,
so custom end nodes (e.g. AnswerEnd) integrate naturally.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from src.agentflow.statemachine.signal import StdSignal

if TYPE_CHECKING:
    from src.agentflow.statemachine.context import Context


class StateVertex(ABC):
    """Abstract base class for all graph nodes.

    Each subclass implements run() which receives the current state snapshot
    and the shared context, then returns a routing signal + state patch.
    All constructor parameters MUST have default values to support
    auto-instantiation in Epic E020.
    """

    @abstractmethod
    async def run(self, state: object, ctx: "Context") -> tuple[object, object]:
        """Execute this vertex for one BSP super-step.

        Args:
            state: Current immutable state snapshot (frozen dataclass).
            ctx: Shared services (LLM connector, tools, logger, run_id).

        Returns:
            Tuple of (EnumSignal, StatePatch) — signal routes the next step,
            patch describes state mutations.
        """


class End(StateVertex):
    """Marker base class for terminal nodes.

    The runner detects end-of-run by isinstance(active_node, End).
    Subclass End to add custom termination logic (logging, notifications, cleanup).
    """

    @abstractmethod
    async def run(self, state: object, ctx: "Context") -> tuple[object, object]: ...


class StdEnd(End):
    """Default terminal node — does nothing, returns an empty patch.

    Use StdEnd when no custom end logic is needed. The runner will stop
    the BSP loop after StdEnd.run() completes.
    """

    async def run(self, state: object, ctx: "Context") -> tuple[object, object]:
        """Return done signal with empty patch to terminate the run.

        Args:
            state: Current state (ignored).
            ctx: Shared context (ignored).

        Returns:
            Tuple (StdSignal.done, empty StatePatch-compatible object).
        """
        # Import here to avoid circular: vertex.py <- state.py (StatePatch not yet defined)
        # StdEnd returns a minimal sentinel; T040 will wire proper StatePatch.
        return StdSignal.done, _EmptyPatch()


class _EmptyPatch:
    """Minimal sentinel patch returned by StdEnd before StatePatch is available."""
```

**Poznámka k circular importu:** `vertex.py` potřebuje `Context` (z `context.py`) jako typ argumentu
v `run()`. Ale `context.py` nesmí importovat `vertex.py`. Řešení: `if TYPE_CHECKING:` blok v `vertex.py`.
Pro `StatePatch` (definovaný v `state.py` v T020) je situace podobná. V T030 StdEnd vrátí
objekt-sentinelu `_EmptyPatch` místo skutečného `StatePatch` — tím se vyhneme kruhové závislosti
v tomto tasku. T050 (runner) a T080 (demo) budou využívat kompletní API a je `StatePatch` import bude
vyřešen přes `TYPE_CHECKING` nebo přímým importem (state.py je hotov po T020).

**Alternativa pro stricter mypy:** pokud mypy --strict hlásí chyby kvůli `_EmptyPatch`, Coder
rozhodne na místě: buď použít `tuple[Any, Any]` jako return type, nebo importovat StatePatch
z T020 přímo (T020 a T030 jsou paralelní — při spouštění T030 může T020 ještě neexistovat).
Pokud T020 není hotov, use `object` jako placeholder a po T020 update.

#### `tests/statemachine/test_context.py` — 3 testy

| # | Test name | Co ověřuje |
|---|-----------|------------|
| 1 | `test_context_run_sync_executes_sync_callable` | sync fn přes run_sync vrátí hodnotu. |
| 2 | `test_context_run_id_is_unique_per_instance` | Dvě instance mají různé run_id. |
| 3 | `test_context_default_logger_named_statemachine` | `ctx.logger.name == "statemachine"`. |

#### `tests/statemachine/test_vertex_endings.py` — 3 testy

| # | Test name | Co ověřuje |
|---|-----------|------------|
| 1 | `test_state_vertex_is_abstract` | `pytest.raises(TypeError)` při instanciaci StateVertex. |
| 2 | `test_std_end_returns_done_and_empty_patch` | `StdEnd().run(state, ctx)` vrátí `StdSignal.done`. |
| 3 | `test_end_subclass_detected_by_isinstance` | `isinstance(StdEnd(), End)` je True. |

## 4. Context Bundle

### Read (Coder potřebuje)

| Soubor | Proč |
|--------|------|
| `src/agentflow/doc/project-progress/brief.md` | §1.4–§1.6. |
| `src/agentflow/doc/project-progress/spec.md` | TD-07, TD-08. |
| `src/agentflow/statemachine/signal.py` | `StdSignal.done` pro StdEnd. |
| `src/agentflow/llm/LlmConnector.py` | Typ `Context.connector`. |
| `src/agentflow/tools/ToolRegistry.py` | Typ `Context.tools`. |
| `pyproject.toml` | mypy, pytest konfigurace. |
| `.cursor/rules/10-python.mdc` | Coding standards. |

### Do NOT modify

- `src/agentflow/statemachine/signal.py` (T010 hotov).
- `src/agentflow/statemachine/state.py` (T020 scope).
- `src/agentflow/llm/**`, `src/agentflow/agents/**`, `src/agentflow/tools/**`, `src/agentflow/describable/**`.
- `src/agentflow/doc/**` mimo `task-030-context-statevertex-end/report.md` a `dod.md`.

### Interfaces from prior tasks

```python
# z T010:
from src.agentflow.statemachine import EnumSignal, StdSignal
# T020 může nebo nemusí být dokončen — pokud ano, lze importovat StatePatch
```

### Interfaces poskytované tímto Taskem pro T040+

```python
from src.agentflow.statemachine import Context, StateVertex, End, StdEnd
```

## 5. Dependencies

- T010 (Package scaffolding & signals) — **dokončen** ✅

## 6. Test Specification

Soubory testů — viz sekce 3.3. Celkem 6 nových testů + 3 z T010 = min. 9 zelených.

**Regresní suite:**
```bash
pytest src/agentflow/tests/statemachine/
mypy --strict --follow-imports=skip src/agentflow/statemachine/
ruff check src/agentflow/statemachine/ src/agentflow/tests/statemachine/
```

## 7. Definition of Done

Viz `dod.md` v tomto adresáři.

## 8. Recommended Coder model

**Composer-2.5 Fast** — strukturální task, klíčové je správné řešení circular importu a TYPE_CHECKING.

## 9. Poznámky pro Coder

- `from __future__ import annotations` + `if TYPE_CHECKING: import Context` — standardní řešení kruhového importu pro type hints.
- `StateVertex` používá `object` jako typ `state` a `ctx` v abstractmethod signatuře — plné typy přijdou po T020+T030 integraci. Alternativně `Any`.
- `_EmptyPatch` je interní sentinel, nesmí být v `__all__`.
- `StdEnd` nemá `__init__` — auto-instanciace v E020 ji vytvoří bez argumentů. Ujisti se, že to funguje.
- Po dokončení: vyplnit `dod.md` + napsat `report.md`. Bez git commitu.
