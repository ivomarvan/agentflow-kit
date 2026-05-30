---
apm_category: task-spec
apm_ref: E010.T060
apm_level: task
created_by: Planner
model: claude-opus-4-7
intended_for: Coder
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Task Specification: E010.T060 — Hooks: Protocol + NoOpHooks + LoggingHooks

## 1. Goal

Definovat `RunnerHooks` Protocol s minimálním rozsahem 5 callbacků (per brief §3.3) pro MVP observability.
Implementovat `NoOpHooks` (default — všechny metody jsou no-op) a `LoggingHooks` (strukturované
DEBUG/INFO logy přes `logging`). Plnohodnotná `RecorderHooks` s historií super-kroků patří do E030 —
zde jen rozhraní + 2 základní implementace, které T050 potřebuje jako default.

## 2. Inputs

- `src/agentflow/doc/project-progress/brief.md` — §3.3 (RunnerHooks, 5 callback metod).
- `src/agentflow/statemachine/signal.py` — vzor stylu kódu (T010).
- `pyproject.toml` — konfigurace mypy, pytest.
- `.cursor/rules/10-python.mdc` — Python coding standards.

## 3. Outputs

### 3.1 Modifikované soubory

- `src/agentflow/statemachine/hooks.py` — **kompletní implementace** (nahradit placeholder).
- `src/agentflow/statemachine/__init__.py` — přidat `RunnerHooks`, `NoOpHooks`, `LoggingHooks` do re-exportů.

### 3.2 Nové soubory

- `src/agentflow/tests/statemachine/test_hooks.py` — 3 unit testy.

### 3.3 Detaily obsahu

#### `hooks.py`

```python
"""RunnerHooks protocol and default observability implementations.

RunnerHooks defines asynchronous callbacks invoked at key points of the BSP
execution loop. NoOpHooks is the default (used when no hooks are provided).
LoggingHooks provides structured DEBUG/INFO logs for development use.
Full RecorderHooks with step history will be added in Epic E030.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.agentflow.statemachine.vertex import StateVertex


@runtime_checkable
class RunnerHooks(Protocol):
    """Async callback interface for observing StateGraphRunner execution.

    All methods are called by the runner at specific points in the BSP loop.
    Implementations must be awaitable (async def). The default implementation
    is NoOpHooks which does nothing for all callbacks.
    """

    async def on_run_start(self, state: object) -> None:
        """Called once before the BSP loop starts.

        Args:
            state: Initial state passed to runner.run().
        """
        ...

    async def on_super_step_start(
        self, step: int, state: object, active: list["StateVertex"]
    ) -> None:
        """Called at the beginning of each super-step (Compute phase).

        Args:
            step: Super-step counter (1-based).
            state: Current state snapshot.
            active: List of vertices about to be executed.
        """
        ...

    async def on_vertex_error(self, node: "StateVertex", exc: Exception) -> None:
        """Called when a vertex raises an unexpected exception.

        Args:
            node: The vertex that raised the exception.
            exc: The exception that was raised.
        """
        ...

    async def on_super_step_end(
        self, step: int, state: object, next_active: set["StateVertex"]
    ) -> None:
        """Called after Apply&Route phase, with updated state and next active nodes.

        Args:
            step: Super-step counter (same as on_super_step_start).
            state: New state after applying patches.
            next_active: Set of vertices scheduled for the next super-step.
        """
        ...

    async def on_run_end(self, state: object) -> None:
        """Called once after the BSP loop completes (End node reached).

        Args:
            state: Final state after the last super-step.
        """
        ...


class NoOpHooks:
    """Default no-op implementation of RunnerHooks — all callbacks do nothing.

    Used as the default when no hooks are provided to StateGraphRunner.
    Zero overhead: all methods immediately return None.
    """

    async def on_run_start(self, state: object) -> None:
        return None

    async def on_super_step_start(
        self, step: int, state: object, active: list["StateVertex"]
    ) -> None:
        return None

    async def on_vertex_error(self, node: "StateVertex", exc: Exception) -> None:
        return None

    async def on_super_step_end(
        self, step: int, state: object, next_active: set["StateVertex"]
    ) -> None:
        return None

    async def on_run_end(self, state: object) -> None:
        return None


class LoggingHooks:
    """RunnerHooks implementation that emits structured log records.

    Uses DEBUG for per-vertex detail and INFO for super-step milestones.
    Vertex errors are logged at ERROR level with full exception traceback.

    Args:
        name: Logger name; defaults to 'statemachine.runner'.
    """

    def __init__(self, name: str = "statemachine.runner") -> None:
        self._logger = logging.getLogger(name)

    async def on_run_start(self, state: object) -> None:
        self._logger.info("run_start: state_type=%s", type(state).__name__)

    async def on_super_step_start(
        self, step: int, state: object, active: list["StateVertex"]
    ) -> None:
        node_names = [type(n).__name__ for n in active]
        self._logger.debug(
            "super_step_start: step=%d active=%s", step, node_names
        )

    async def on_vertex_error(self, node: "StateVertex", exc: Exception) -> None:
        self._logger.error(
            "vertex_error: node=%s exc_type=%s exc=%s",
            type(node).__name__, type(exc).__name__, exc,
            exc_info=exc,
        )

    async def on_super_step_end(
        self, step: int, state: object, next_active: set["StateVertex"]
    ) -> None:
        node_names = [type(n).__name__ for n in next_active]
        self._logger.info(
            "super_step_end: step=%d next_active=%s", step, node_names
        )

    async def on_run_end(self, state: object) -> None:
        self._logger.info("run_end: final_state_type=%s", type(state).__name__)
```

**Poznámky k implementaci:**
- `@runtime_checkable` na `RunnerHooks` Protocol umožňuje `isinstance(hooks, RunnerHooks)` runtime check — užitečné pro validaci v runneru.
- `TYPE_CHECKING` import `StateVertex` zabraňuje circular importu (hooks.py nesmí importovat vertex.py za runtime).
- `NoOpHooks` **není** formální subclass `RunnerHooks` — splňuje Protocol strukturálně (duck typing). mypy to ověří.

#### `tests/statemachine/test_hooks.py` — 3 testy

```python
"""Unit tests for RunnerHooks, NoOpHooks, and LoggingHooks."""

import logging
import pytest

from src.agentflow.statemachine.hooks import NoOpHooks, LoggingHooks, RunnerHooks


@pytest.mark.unit
class TestNoOpHooks:
    def test_noop_hooks_callbacks_return_none(self) -> None:
        # All async callbacks on NoOpHooks must return None (fire-and-forget safe)
        import asyncio
        hooks = NoOpHooks()
        result = asyncio.run(hooks.on_run_start(object()))
        assert result is None

    def test_noop_hooks_satisfies_protocol(self) -> None:
        hooks = NoOpHooks()
        assert isinstance(hooks, RunnerHooks)


@pytest.mark.unit
class TestLoggingHooks:
    def test_logging_hooks_logs_at_super_step_start(self, caplog) -> None:
        import asyncio
        hooks = LoggingHooks()
        with caplog.at_level(logging.DEBUG, logger="statemachine.runner"):
            asyncio.run(hooks.on_super_step_start(1, object(), []))
        assert any("super_step_start" in r.message for r in caplog.records)

    def test_logging_hooks_logs_vertex_error(self, caplog) -> None:
        import asyncio

        class _FakeVertex:
            pass

        hooks = LoggingHooks()
        exc = ValueError("test error")
        with caplog.at_level(logging.ERROR, logger="statemachine.runner"):
            asyncio.run(hooks.on_vertex_error(_FakeVertex(), exc))  # type: ignore[arg-type]
        assert any(r.levelname == "ERROR" for r in caplog.records)
```

## 4. Context Bundle

### Read (Coder potřebuje)

| Soubor | Proč |
|--------|------|
| `src/agentflow/doc/project-progress/brief.md` | §3.3 (RunnerHooks — 5 metod). |
| `src/agentflow/statemachine/signal.py` | Vzor stylu kódu. |
| `pyproject.toml` | mypy, pytest. |
| `.cursor/rules/10-python.mdc` | Coding standards. |

### Do NOT modify

- `src/agentflow/statemachine/signal.py` (T010).
- `src/agentflow/statemachine/state.py` (T020).
- `src/agentflow/statemachine/context.py`, `vertex.py` (T030).
- `src/agentflow/llm/**`, `src/agentflow/agents/**`, `src/agentflow/tools/**`, `src/agentflow/describable/**`.
- `src/agentflow/doc/**` mimo `task-060-hooks/report.md` a `dod.md`.

### Interfaces from prior tasks

```python
# z T010:
from src.agentflow.statemachine.signal import StdSignal
# vertex.py z T030 (TYPE_CHECKING only — žádný runtime import)
```

### Interfaces poskytované tímto Taskem pro T050

```python
from src.agentflow.statemachine.hooks import RunnerHooks, NoOpHooks, LoggingHooks
```

## 5. Dependencies

- T010 (Package scaffolding & signals) — **dokončen** ✅
- T030 (Context, StateVertex) — nutný jen pro TYPE_CHECKING import `StateVertex` v type hints; implementace hooks.py nevyžaduje T030 runtime.

## 6. Test Specification

Soubor `src/agentflow/tests/statemachine/test_hooks.py` — 3 testy (viz sekce 3.3).

**Regresní suite:**
```bash
pytest src/agentflow/tests/statemachine/
mypy --strict --follow-imports=skip src/agentflow/statemachine/
ruff check src/agentflow/statemachine/ src/agentflow/tests/statemachine/
```

## 7. Definition of Done

Viz `dod.md` v tomto adresáři.

## 8. Recommended Coder model

**Composer-2.5 Fast** — strukturální task s Protocol pattern. Klíčové: `runtime_checkable`, `TYPE_CHECKING` pro forward reference, async no-op pattern.

## 9. Poznámky pro Coder

- `@runtime_checkable` je nutný pro `isinstance(hooks, RunnerHooks)` v T050 runneru.
- `TYPE_CHECKING` blok pro `StateVertex` — hooks.py nesmí importovat vertex.py za runtime (circular risk).
- `NoOpHooks` je čistá strukturální implementace — satisfies Protocol bez explicitní dědičnosti.
- mypy strict ověří, že `NoOpHooks` je kompatibilní s `RunnerHooks` Protocol.
- Testy používají `asyncio.run()` pro volání async callbacků (Python 3.10+ safe).
- Po dokončení: vyplnit `dod.md` + napsat `report.md`. Bez git commitu.
