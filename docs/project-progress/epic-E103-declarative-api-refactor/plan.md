# Epic E103 — Declarative API Refactor

**Goal:** Replace the subclassing/imperative API with a fully declarative, Pydantic-based
framework. The target state is described by `examples/showcase.wish.py` and demonstrated
by `examples/agents/06_smart_home_assistant.py`.

**Design reference:** `examples/showcase.wish.py` (notes section, requirements 1–10)

---

## Task List

### T103-01 — ReActState, ReActPatch, ReActSignal + Signal alias

**File:** `agentflow/statemachine/react.py` (new)
**Export from:** `agentflow/statemachine/__init__.py`

- `ReActState` — frozen dataclass with fields: `messages`, `last_tool_calls`, `final_answer`, `step`
- `ReActPatch` — frozen dataclass, same fields, all optional (empty defaults)
- `ReActSignal(Enum)` — signals: `tool_call`, `final_answer`, `max_steps`
- `Signal` alias — re-export `Enum` as `Signal` so user can write `class MySignal(Signal)`
- Update `agentflow/statemachine/__init__.py` exports

---

### T103-02 — Context: multi-connector/registry + RunStats + ctx.step/exceeded

**File:** `agentflow/statemachine/context.py` (modify)
**New file:** `agentflow/statemachine/run_stats.py`

#### RunStats
```python
@dataclass
class RunStats:
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    wall_time_ms: float = 0.0
    llm_calls: int = 0
    cache_hits: int = 0
```

#### Context additions (backward compat — keep `connector` and `tools`)
```python
@dataclass
class Context:
    connector: LlmConnector | None = None                   # deprecated, kept for compat
    tools: ToolRegistry | None = None                       # deprecated, kept for compat
    llm_connectors: dict[str, LlmConnectorBase] = field(default_factory=dict)
    tool_registries: dict[str, ToolRegistry] = field(default_factory=dict)
    stats: RunStats = field(default_factory=RunStats)
    step: int = 0
    logger: logging.Logger = ...
    run_id: str = ...
    event_bus: EventBus = ...

    def llm(self, key: str = "default") -> LlmConnectorBase:
        """Return LLM connector by key; fallback to 'connector' attr for compat."""

    def get_tools(self, key: str = "default") -> ToolRegistry:
        """Return tool registry by key; fallback to 'tools' attr for compat."""

    def exceeded(self, n: int) -> bool:
        return self.step >= n
```

**Note:** `ctx.tools()` clashes with existing `tools` field. Use method name `get_tools()` or
rename field to `_tools_registry`. Decision: rename field to `_tools` (private) and expose
via `get_tools()`. Keep `tools` as deprecated property.

**Runner update:** increment `ctx.step` after each super-step.

---

### T103-03 — StateGraph: `initialized_vertexes` parameter

**File:** `agentflow/statemachine/topology.py` (modify)

```python
class StateGraph(Describable):
    def __init__(
        self,
        start: type[StateVertex] | StateVertex,
        transitions: Sequence[Transition],
        initialized_vertexes: list[StateVertex] | None = None,
    ) -> None:
```

Logic in `VertexResolver.resolve()`: if the class of a requested vertex has an instance
in `initialized_vertexes`, return that instance instead of creating a new one.

Inject `initialized_vertexes` into the `VertexResolver` at `StateGraph.__init__` time.

---

### T103-04 — LlmConnectorBase: `achat_with_tools()`

**File:** `agentflow/llm/LlmConnectorBase.py` (modify)

```python
async def achat_with_tools(
    self,
    messages: list[dict[str, Any]],
    registry: ToolRegistry,
    max_rounds: int = 10,
    temperature: float = 0.2,
    logger: logging.Logger | None = None,
) -> ChatResponse:
    """Execute LLM with automatic tool-calling loop.

    Loop: call LLM → if response has tool_calls: execute each via registry,
    append tool result messages → repeat. Returns final plain-text ChatResponse.
    Stops when LLM returns no tool_calls or max_rounds is reached.
    """
```

Uses existing `ToolRegistry.execute(name, arguments)` API.
Logs each tool call at INFO level.

---

### T103-05 — StateVertex → Pydantic BaseModel

**File:** `agentflow/statemachine/vertex.py` (modify)

```python
from pydantic import BaseModel
from pydantic import ConfigDict

class StateVertex(BaseModel):
    model_config = ConfigDict(frozen=False, extra="allow", arbitrary_types_allowed=True)

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        raise NotImplementedError(f"{type(self).__name__}.run() must be implemented")
```

- Remove `ABC` dependency
- `End(StateVertex)` and `StdEnd(End)` updated accordingly
- `VertexResolver.resolve(v)`: if `v` is a class (not instance), call `v()` — this still
  works because `BaseModel()` creates an instance with defaults
- Existing subclasses in tests/examples that have explicit `__init__` keep working
  (Pydantic allows custom `__init__` via `model_config`)

**Backward compat test:** `class OldVertex(StateVertex): async def run(...): ...` must
still instantiate without arguments.

---

### T103-06 — Describable: get_config_schema / get_param_values / set_params + remove name

**File:** `agentflow/describable/describable.py` (modify)

```python
def get_config_schema(self) -> dict[str, Any]:
    """Return JSON Schema for scalar configurable parameters.
    If self is a Pydantic BaseModel: filter model_json_schema() to scalar types.
    Otherwise: build from get_type_hints(__init__, include_extras=True).
    """

def get_param_values(self) -> dict[str, Any]:
    """Return current values of all configurable scalar params."""

def set_params(self, **kwargs: Any) -> None:
    """Update configurable scalar params at runtime (for GUI Settings tab)."""
```

Remove `name` parameter from `Describable.__init__()` if it exists.
If `name` was used in graph building, replace with `type(self).__name__`.

---

### T103-07 — AgentApp: declarative constructor + run_and_stats()

**File:** `agentflow/app.py` (modify)

```python
class AgentApp(Describable):
    def __init__(
        self,
        *,
        doc: str | None = None,
        system_prompt: str = "",
        default_question: str = "",
        sample_prompts: list[str] | None = None,
        context: Context | None = None,
        state_graph: StateGraph | None = None,
    ) -> None:
```

- If `context` and `state_graph` provided: generic `run_workflow()` works without subclassing
- `run_and_stats(question: str) -> tuple[str | None, RunStats]`
- `cli()` uses `self.doc` if available
- Subclassing still works (backward compat): if subclass overrides `run_workflow()`, that
  is used instead

Generic `run_workflow()`:
1. `set_init_state(question)` → builds initial state from `system_prompt` + question
2. Creates `StateGraphRunner(self.state_graph, ctx)`  
3. Runs the runner, extracts result via `extract_result(final_state)`
4. Overridable sub-methods: `build_runner_context()`, `set_init_state()`, `extract_result()`

Default initial state: `ReActState` with system_prompt + question messages.
Default result extraction: `final_state.final_answer` if field exists, else `str(final_state)`.

---

### T103-08 — Update and add tests

**Scope:**
- `tests/agentflow/statemachine/test_vertex.py` — Pydantic BaseModel fields, no __init__
- `tests/agentflow/statemachine/test_context.py` — ctx.llm(), ctx.get_tools(), ctx.step, ctx.exceeded()
- `tests/agentflow/statemachine/test_topology.py` — initialized_vertexes
- `tests/agentflow/llm/test_achat_with_tools.py` (new) — tool loop 0, 1, 2 rounds
- `tests/agentflow/test_agent_app.py` — declarative constructor, run_and_stats
- Fix any broken existing tests

---

### T103-09 — Rewrite examples/agents/01-05 to new API

Rewrite each example to use:
- Class-level `Annotated[T, Field(...)]` in vertices (no `__init__`)
- `ctx.llm(key)` / `ctx.get_tools(key)` instead of `ctx.connector`
- Declarative `AgentApp(...)` constructor where applicable (or keep subclass for complex apps)
- `setup_pretty_logging()` and `run_and_stats()` where applicable
- Verify `06_smart_home_assistant.py` works as-is (no changes needed if API is correct)

---

### T103-10 — Evaluate and update examples/quickstart/

- `00_hello_world.py` — keep minimal, update to new API if trivial
- `01_brief_example.py` — likely needs ctx.llm() update
- `02_tool_agent_demo.py` — update to new API
- `03_live_graph_demo.py` — update to new API if needed
- `04_parallel_research_loop.py` — update to new API (complex, priority)
- `05_human_in_the_loop_demo.py` — update if possible

---

## Execution Order

```
T01 → T02 → T03 → T04 → T05 → T06 → T07 → T08 → T09 → T10
  parallel possible: T01, T03, T04 can run in parallel
  T05 depends on nothing (Pydantic addition)
  T06 can parallel T07
  T08 must follow T01–T07
  T09, T10 must follow T08
```

## Definition of Done

- [ ] `06_smart_home_assistant.py` runs without errors (with FakeLlmRegexConnector stub)
- [ ] `showcase.wish.py` structure is reflected in working `showcase.py` (new version)
- [ ] All existing tests pass
- [ ] New tests added for T01–T07
- [ ] Graph visualization works for all examples (graph, browser, gui commands)
