---
apm_category: epic-plan
apm_ref: E096
apm_level: epic
created_by: Planner
model: claude-sonnet-4-6
intended_for: Coder
created_at: 2026-05-30
updated_at: 2026-05-30
approved_by: Human
approved_at: 2026-05-30
---

# Epic E096 — AgentApp foundation: rename + EventBus + Pydantic config schema

**Cíl:** Přejmenovat `ExampleApp` → `AgentApp`, zavést `EventBus` + `AgentEvent` jako
domain-event kanál pro vertex/tool → GUI komunikaci, přidat Pydantic config modely
pro klíčové třídy a implementovat `get_config_schema()` / `get_config()` / `set_config()`
API na `AgentApp`. Toto je základ pro E097 (FastAPI backend).

---

## Scope

| Oblast | Co se mění |
|--------|-----------|
| `agentflow/app.py` | Rename `ExampleApp` → `AgentApp`; `run_workflow() -> str \| None`; `sample_prompts` |
| `agentflow/__init__.py` | Export `AgentApp`; zachovat `ExampleApp` jako alias |
| `agentflow/events.py` (nový) | `AgentEvent` (Pydantic BaseModel), `EventBus`, `LoggingEventHandler` |
| `agentflow/statemachine/context.py` | Přidat `event_bus: EventBus` (optional field) |
| `agentflow/llm/LlmConfig.py` | Migrace na Pydantic `BaseModel` |
| `agentflow/llm/LlmConnector.py` | Přijmout Pydantic `LlmConfig`; doplnit `config_schema()` |
| Klíčové Describable třídy | `_config_params()` protocol pro introspekci parametrů |
| `agentflow/app.py` | `get_config_schema()`, `get_config()`, `set_config(path, value)` |
| Všechny příklady + testy | Nahradit `ExampleApp` → `AgentApp` |

---

## Task List

| Task | Název | Závisí na |
|------|-------|-----------|
| T010 | Rename ExampleApp → AgentApp + run_workflow return + sample_prompts | — |
| T020 | EventBus + AgentEvent + Context extension | T010 |
| T030 | Pydantic LlmConfig + config schema API na AgentApp | T010 |
| T040 | Update všechny příklady a testy | T010, T020, T030 |

---

## T010 — Rename ExampleApp → AgentApp

### Změny

**`agentflow/app.py`:**
- Přejmenovat třídu `ExampleApp` → `AgentApp`
- Docstring a všechny reference uvnitř souboru aktualizovat
- `run_workflow()` změní návratový typ: `async def run_workflow(self) -> str | None`
  - Vrací summary string zobrazený v GUI Chatu jako výsledek runů
  - `None` = "Completed." (GUI zobrazí fallback)
- Přidat `sample_prompts: list[str]` property (default vrací `[]`)
- Přidat `description: str` property (default: `type(self).__name__`) — title pro GUI
- Zachovat `cli()`, `run()` — `run()` vrátí co vrátí `run_workflow()`

**`agentflow/__init__.py`:**
- Přidat export `AgentApp`
- Zachovat `ExampleApp = AgentApp` alias pro backward compat + upozornění v docstringu

**Refaktoring příkladů (6 souborů):**
```
examples/quickstart/00_hello_world.py       HelloWorldApp(AgentApp)
examples/quickstart/01_brief_example.py     BriefExampleApp(AgentApp)
examples/quickstart/02_tool_agent_demo.py   ToolAgentDemoApp(AgentApp)
examples/quickstart/03_live_graph_demo.py   LiveGraphDemoApp(AgentApp)
examples/quickstart/04_parallel_research_loop.py  ParallelResearchLoopApp(AgentApp)
examples/quickstart/05_human_in_the_loop_demo.py  HumanInTheLoopApp(AgentApp)
examples/patterns/04_react_agent_statemachine.py  ReactAgentApp(AgentApp)
```

**Testy:**
- `tests/agentflow/test_example_app.py` → přejmenovat na `test_agent_app.py`
- Aktualizovat import a název třídy

### Definition of Done T010
- [ ] `from agentflow import AgentApp` funguje
- [ ] `from agentflow import ExampleApp` funguje (alias, deprecation warning v docstringu)
- [ ] 7 příkladů importuje `AgentApp`
- [ ] `run_workflow()` vrací `str | None`
- [ ] `sample_prompts` property na base třídě vrací `[]`
- [ ] 173+ testů zelených, ruff + mypy čisté

---

## T020 — EventBus + AgentEvent + Context extension

### Nový soubor `agentflow/events.py`

```python
from __future__ import annotations
from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from pydantic import BaseModel, Field

class AgentEvent(BaseModel):
    """Base for all domain events emitted by vertices and tools.

    Subclass to define application-specific events (e.g. ReservationEvent).
    The event_type field is used by the GUI to select the correct renderer.
    """
    event_type: str
    timestamp: datetime = Field(default_factory=datetime.now)
    run_id: str = ""

# Built-in framework events
class StepStartEvent(AgentEvent):
    event_type: str = "agentflow.step_start"
    vertex: str
    step: int

class StepEndEvent(AgentEvent):
    event_type: str = "agentflow.step_end"
    vertex: str
    step: int
    signal: str

class LogEvent(AgentEvent):
    event_type: str = "agentflow.log"
    level: str    # DEBUG / INFO / WARNING / ERROR
    message: str
    logger_name: str = ""

class RunCompleteEvent(AgentEvent):
    event_type: str = "agentflow.run_complete"
    result: str | None = None

class RunErrorEvent(AgentEvent):
    event_type: str = "agentflow.run_error"
    message: str

@runtime_checkable
class EventHandler(Protocol):
    async def on_event(self, event: AgentEvent) -> None: ...

class LoggingEventHandler:
    """Default handler — writes events to Python logging."""
    async def on_event(self, event: AgentEvent) -> None:
        import logging
        logging.getLogger("agentflow.events").debug(
            "event type=%s data=%s", event.event_type, event.model_dump()
        )

class EventBus:
    """Collects domain events, notifies all registered handlers.

    Always has LoggingEventHandler as default subscriber.
    """
    def __init__(self) -> None:
        self._handlers: list[EventHandler] = [LoggingEventHandler()]
        self._history: list[AgentEvent] = []

    def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    def unsubscribe(self, handler: EventHandler) -> None:
        self._handlers.remove(handler)

    async def emit(self, event: AgentEvent) -> None:
        self._history.append(event)
        for handler in self._handlers:
            await handler.on_event(event)

    @property
    def history(self) -> list[AgentEvent]:
        return list(self._history)
```

### Změny `agentflow/statemachine/context.py`

```python
from agentflow.events import EventBus

@dataclass
class Context:
    connector: LlmConnector
    tools: ToolRegistry | None = None
    logger: logging.Logger = field(...)
    run_id: str = field(...)
    event_bus: EventBus = field(default_factory=EventBus)  # ← nové
```

### Export z `agentflow/__init__.py`
- `AgentEvent`, `EventBus`, `StepStartEvent`, `StepEndEvent`, `LogEvent`, `RunCompleteEvent`, `RunErrorEvent`

### Testy `tests/agentflow/test_events.py`
- `EventBus` subscribe + emit + history
- `LoggingEventHandler` volán při emit
- `Context` má výchozí `EventBus`
- Vlastní `AgentEvent` subclass (ReservationEvent)

### Definition of Done T020
- [ ] `from agentflow import AgentEvent, EventBus` funguje
- [ ] `EventBus.emit()` notifikuje všechny handlery a ukládá do history
- [ ] `Context.event_bus` je součástí `Context` (optional, default `EventBus()`)
- [ ] Unit testy pro EventBus zelené
- [ ] ruff + mypy čisté

---

## T030 — Pydantic LlmConfig + config schema API

### Pydantic migrace `LlmConfig`

`LlmConfig` se migruje z `@dataclass` na `pydantic.BaseModel`. Všechny ostatní
konfigurační třídy (kde to dává smysl — tj. mají parametry konfigurovatelné uživatelem)
dostanou minimální `_config_params()` support.

**Přístup — 2 úrovně:**

1. **Pydantic BaseModel** pro datové config objekty (LlmConfig, případně budoucí ToolConfig):
   - `model_json_schema()` → JSON Schema zdarma
   - Validace vstupů při `set_config()`

2. **Lightweight `_config_params()`** pro třídy s `__init__` parametry (LlmConnector, ToolAgent):
   - Vrací `dict[str, ConfigParam]` s názvem, typem, hodnotou, popisem
   - Nenutí celou třídu přepisovat na Pydantic

```python
@dataclass
class ConfigParam:
    """Metadata for a single configurable parameter."""
    name: str
    type_hint: str          # "str", "float", "int", "bool", "Literal['a','b']"
    value: Any
    description: str = ""
    min_value: float | None = None
    max_value: float | None = None
    choices: list[Any] | None = None  # for enums / Literal
    required: bool = False
```

### `AgentApp.get_config_schema()` / `get_config()` / `set_config()`

```python
class AgentApp(Describable):
    def get_config_schema(self) -> dict:
        """Return JSON Schema of all configurable parameters (hierarchical).

        Schema is derived from Pydantic models (model_json_schema()) and
        _config_params() introspection on Describable children.
        """
        ...

    def get_config(self) -> dict:
        """Return current values of all configurable parameters (flat dot-path dict)."""
        ...

    def set_config(self, path: str, value: Any) -> None:
        """Set a single parameter by dot-path (e.g. 'connector.temperature').

        Raises:
            KeyError: Unknown parameter path.
            ValueError: Value fails Pydantic validation.
        """
        ...
```

Dot-path konvence: `"connector.model"`, `"graph.max_steps"`, `"agent.temperature"`.

### Definition of Done T030
- [ ] `LlmConfig` je `pydantic.BaseModel`, všechny existující testy zelené
- [ ] `AgentApp().get_config_schema()` vrací JSON Schema s alespoň `connector.*` parametry
- [ ] `AgentApp().get_config()` vrací dict s aktuálními hodnotami
- [ ] `AgentApp().set_config("connector.model", "gpt-4o")` změní hodnotu
- [ ] Unit testy pro config schema API
- [ ] ruff + mypy čisté

---

## T040 — Update příkladů a testů

- Nahradit `ExampleApp` → `AgentApp` ve všech příkladech (7 souborů již bylo v T010)
- Aktualizovat `run_workflow()` return type v příkladech kde je možné vrátit summary
- Přidat `sample_prompts` do 2-3 příkladů jako ukázku (BriefExampleApp, ParallelResearchLoopApp)
- Aktualizovat README.md — sekce "Hello World" zmínit AgentApp
- Aktualizovat `agentflow/statemachine/README.md` — EventBus dokumentace

### Definition of Done T040
- [ ] Všechny příklady importují `AgentApp`
- [ ] 2+ příklady mají `sample_prompts`
- [ ] 2+ příklady vrátí string z `run_workflow()`
- [ ] README aktualizováno
- [ ] 173+ testů zelených

---

## Epic E096 Definition of Done

- [ ] `from agentflow import AgentApp, EventBus, AgentEvent` funkční
- [ ] `ExampleApp` alias zachován (backward compat)
- [ ] `Context.event_bus: EventBus` dostupný ve vrcholech
- [ ] `LlmConfig` je Pydantic `BaseModel`
- [ ] `AgentApp.get_config_schema()` vrací JSON Schema
- [ ] Všechny příklady a testy aktualizovány
- [ ] 173+ testů zelených, ruff + mypy čisté

## Poznámky pro Codera

- `LlmConfig.from_env()` → zůstane jako classmethod, ale vrací Pydantic model
- `LlmConfig` pole která jsou `Optional` / mají default → `Field(default=..., description="...")`
- Pydantic v2 — používat `model_json_schema()` ne `schema()` (v1 API)
- `EventBus` v `Context` je `field(default_factory=EventBus)` — každý Context má vlastní bus
- Backward compat: `ExampleApp = AgentApp` v `agentflow/__init__.py` + komentář "# deprecated alias"
