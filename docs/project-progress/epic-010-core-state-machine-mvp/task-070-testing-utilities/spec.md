---
apm_category: task-spec
apm_ref: E010.T070
apm_level: task
created_by: Planner
model: claude-opus-4-7
intended_for: Coder
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Task Specification: E010.T070 — Testing utilities

## 1. Goal

Postavit `src/agentflow/statemachine/testing/` modul s testovacími pomůckami:
- **`FakeVertex`** — konfigurovatelný StateVertex vracející předdefinovaný signál+patch; čítač volání.
- **`FakeLlmConnector`** — minimální LlmConnector subclass s frontou odpovědí.
- **`make_fake_context(**overrides)`** — factory funkce pro vytvoření `Context` bez reálného LLM.
- **pytest fixtury** v `fixtures.py`.

Tyto utility jsou závislé na T050 (potřebují `StateVertex`), ale T050 závisí na T070 (potřebuje `FakeVertex` pro testy). Závislost je tedy **vzájemná** — Coder implementuje T070 jako samotný modul s unit testy, a T050 ho pak použije. Coder T070 nemůže importovat `StateGraphRunner` z T050.

## 2. Inputs

- `src/agentflow/doc/project-progress/brief.md` — §7 (testovací strategie, FakeVertex, FakeLlmConnector, FakeContext).
- T010–T060 deliverables (signal, state, context, vertex, hooks).
- `src/agentflow/llm/LlmConnector.py` — abstract base pro `FakeLlmConnector`.
- `src/agentflow/llm/ChatResponse.py` — návratový typ chat() metody.
- `pyproject.toml` — konfigurace pytest.
- `.cursor/rules/10-python.mdc` — coding standards.

## 3. Outputs

### 3.1 Nové soubory

```
src/agentflow/statemachine/testing/
├── __init__.py
├── fakes.py
└── fixtures.py

src/agentflow/tests/statemachine/
└── test_testing_utilities.py
```

### 3.2 Modifikované soubory

- `src/agentflow/statemachine/__init__.py` — **neměnit** (testing submodul se importuje přímo z `statemachine.testing`).

### 3.3 Detaily obsahu

#### `testing/__init__.py`

```python
"""Testing utilities for agentflow.statemachine.

Import from this package in tests:
    from src.agentflow.statemachine.testing import FakeVertex, make_fake_context
    from src.agentflow.statemachine.testing.fixtures import fake_ctx
"""

from src.agentflow.statemachine.testing.fakes import (
    FakeVertex,
    FakeLlmConnector,
    make_fake_context,
)

__all__ = ["FakeVertex", "FakeLlmConnector", "make_fake_context"]
```

#### `testing/fakes.py`

```python
"""Fake implementations for deterministic testing of state machine graphs.

FakeVertex, FakeLlmConnector, and make_fake_context allow tests to run
state graphs without real LLM calls or complex vertex logic.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from src.agentflow.statemachine.context import Context
from src.agentflow.statemachine.vertex import StateVertex
from src.agentflow.llm.LlmConnector import LlmConnector
# import ChatResponse for return type of chat()


class FakeVertex(StateVertex):
    """Configurable stub vertex that returns a preset signal and patch.

    Counts how many times run() was called — useful for asserting
    fan-out/fan-in behavior and cycle termination.

    Args:
        signal: The EnumSignal value to return from run().
        patch: The patch object to return from run().
        name: Optional display name for debugging.
        call_count: Mutable list used as a shared counter (pass same list
                    across multiple fakes to aggregate counts).
    """

    def __init__(
        self,
        signal: Any,
        patch: Any,
        *,
        name: str | None = None,
        call_count: list[int] | None = None,
    ) -> None:
        self._signal = signal
        self._patch = patch
        self._name = name or type(self).__name__
        self._call_count = call_count if call_count is not None else []
        self.calls: int = 0  # per-instance call counter

    async def run(self, state: Any, ctx: Any) -> tuple[Any, Any]:
        """Return the configured signal and patch, increment call counter.

        Args:
            state: Current state (ignored).
            ctx: Context (ignored).

        Returns:
            Tuple of (signal, patch) as configured in __init__.
        """
        self.calls += 1
        if self._call_count is not None:
            self._call_count.append(1)
        return self._signal, self._patch

    def __repr__(self) -> str:
        return f"FakeVertex(name={self._name!r}, calls={self.calls})"


class FakeLlmConnector(LlmConnector):
    """Deterministic LlmConnector that returns responses from a preset queue.

    Use queue_responses() to configure the sequence of responses before running.
    Raises RuntimeError when the queue is exhausted — prevents silent test failures.
    """

    def __init__(self) -> None:
        self._queue: deque[str] = deque()

    def queue_responses(self, responses: list[str]) -> None:
        """Enqueue a list of string responses to be returned by chat() in order.

        Args:
            responses: Ordered list of response strings. Each call to chat()
                       consumes the next response.
        """
        self._queue.extend(responses)

    def chat(self, messages: Any, **kwargs: Any) -> Any:
        """Return the next queued response as a ChatResponse.

        Args:
            messages: Ignored (fake connector).
            **kwargs: Ignored.

        Returns:
            ChatResponse with the next queued string as content.

        Raises:
            RuntimeError: When the response queue is empty.
        """
        if not self._queue:
            raise RuntimeError(
                "FakeLlmConnector queue is empty — call queue_responses() before running."
            )
        content = self._queue.popleft()
        # Return a minimal ChatResponse-compatible object
        # Import ChatResponse and wrap content
        from src.agentflow.llm.ChatResponse import ChatResponse  # type: ignore[attr-defined]
        return ChatResponse(content=content)


def make_fake_context(**overrides: Any) -> Context:
    """Factory for a Context with FakeLlmConnector and sensible defaults.

    Args:
        **overrides: Any Context field to override
                     (connector, tools, logger, run_id).

    Returns:
        Context instance suitable for use in tests without real LLM calls.
    """
    import logging
    defaults: dict[str, Any] = {
        "connector": FakeLlmConnector(),
        "logger": logging.getLogger("statemachine.test"),
        "run_id": "test-run-id",
    }
    defaults.update(overrides)
    return Context(**defaults)
```

**Poznámka k `FakeLlmConnector`:** Pokud `ChatResponse` má jiný konstruktor, Coder přizpůsobí volání
přečtením `src/agentflow/llm/ChatResponse.py`. Pokud `LlmConnector.chat()` má konkrétní signaturu,
Coder musí odpovídat. Pokud `LlmConnector` je abstract a `chat()` je abstractmethod, `FakeLlmConnector`
musí implementovat všechny abstractmethods.

#### `testing/fixtures.py`

```python
"""pytest fixtures for statemachine tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from src.agentflow.statemachine.context import Context
from src.agentflow.statemachine.testing.fakes import FakeVertex, make_fake_context
from src.agentflow.statemachine.topology import StateGraph, Transition
from src.agentflow.statemachine.signal import StdSignal
from src.agentflow.statemachine.vertex import StdEnd


@pytest.fixture
def fake_ctx() -> Context:
    """Pytest fixture providing a Context with FakeLlmConnector."""
    return make_fake_context()


@pytest.fixture
def make_state_graph() -> Callable[..., StateGraph]:
    """Factory fixture for building simple StateGraph instances in tests.

    Returns:
        Callable that accepts (start, transitions_list) and returns StateGraph.
    """
    def _factory(start: Any, transitions: list[Any]) -> StateGraph:
        return StateGraph(start=start, transitions=transitions)
    return _factory
```

#### `tests/statemachine/test_testing_utilities.py` — 5 testů

| # | Test name | Co ověřuje |
|---|-----------|------------|
| 1 | `test_fake_vertex_returns_configured_signal_and_patch` | FakeVertex vrátí nastavený signál+patch. |
| 2 | `test_fake_vertex_counts_calls` | `vertex.calls` se inkrementuje per volání. |
| 3 | `test_fake_llm_connector_returns_queued_responses_in_order` | FakeLlmConnector vrátí odpovědi v pořadí. |
| 4 | `test_fake_llm_connector_raises_when_queue_empty` | `RuntimeError` při prázdné frontě. |
| 5 | `test_make_fake_context_provides_default_logger_and_run_id` | Context má logger + run_id. |

## 4. Context Bundle

### Read (Coder potřebuje)

| Soubor | Proč |
|--------|------|
| `src/agentflow/doc/project-progress/brief.md` | §7 (testing strategie). |
| `src/agentflow/statemachine/vertex.py` | `StateVertex` ABC (T030). |
| `src/agentflow/statemachine/context.py` | `Context` dataclass (T030). |
| `src/agentflow/statemachine/signal.py` | `StdSignal` (T010). |
| `src/agentflow/statemachine/state.py` | `apply_patches`, `UNSET` (T020). |
| `src/agentflow/statemachine/hooks.py` | `NoOpHooks` (T060). |
| `src/agentflow/llm/LlmConnector.py` | Abstract base pro FakeLlmConnector. |
| `src/agentflow/llm/ChatResponse.py` | Return type chat(). |
| `.cursor/rules/10-python.mdc` | Coding standards. |

### Do NOT modify

- Cokoli mimo `src/agentflow/statemachine/testing/` a `src/agentflow/tests/statemachine/test_testing_utilities.py`.
- Hotové tasky: `signal.py`, `state.py`, `context.py`, `vertex.py`, `hooks.py`.
- `src/agentflow/doc/**` mimo `task-070-testing-utilities/report.md` a `dod.md`.

### Interfaces from prior tasks

```python
from src.agentflow.statemachine.vertex import StateVertex    # T030
from src.agentflow.statemachine.context import Context       # T030
from src.agentflow.statemachine.signal import StdSignal      # T010
from src.agentflow.statemachine.state import apply_patches   # T020
from src.agentflow.llm.LlmConnector import LlmConnector      # existující agentflow
```

### Interfaces poskytované tímto Taskem pro T050

```python
from src.agentflow.statemachine.testing import FakeVertex, FakeLlmConnector, make_fake_context
from src.agentflow.statemachine.testing.fixtures import fake_ctx, make_state_graph  # pytest fixtures
```

## 5. Dependencies

- T010 ✅ (signal)
- T020 ✅ (state)
- T030 ✅ (context, vertex)
- T060 ✅ (hooks)

## 6. Test Specification

5 testů v `test_testing_utilities.py` — viz sekce 3.3.

**Regresní suite:**
```bash
pytest src/agentflow/tests/statemachine/
mypy --strict --follow-imports=skip src/agentflow/statemachine/
ruff check src/agentflow/statemachine/ src/agentflow/tests/statemachine/
```

## 7. Definition of Done

Viz `dod.md` v tomto adresáři.

## 8. Recommended Coder model

**Composer-2.5 Fast** — utility třídy, jednoduché implementace bez komplexní logiky.

## 9. Poznámky pro Coder

- Přečti `src/agentflow/llm/LlmConnector.py` a `src/agentflow/llm/ChatResponse.py` — zjisti přesnou signaturu `chat()` a konstruktor `ChatResponse`.
- `FakeLlmConnector` musí implementovat **všechny** abstractmethods z `LlmConnector`.
- `fixtures.py` není conftest.py — fixtury jsou v něm definovány, ale musí být importovány v `conftest.py` nebo explicitně v testech. Nejjednodušší: přidat `from src.agentflow.statemachine.testing.fixtures import *` do `src/agentflow/tests/statemachine/conftest.py` (vytvoř ho pokud neexistuje).
- `testing/` je produkční modul (ne test modul) — umístěn v `src/agentflow/statemachine/`, ne v `tests/`.
- Po dokončení: vyplnit `dod.md` + napsat `report.md`. Bez git commitu.
