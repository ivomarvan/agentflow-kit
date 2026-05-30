# Epic E095 — ExampleApp: Unified CLI + Composite Visualization

**Cíl:** Každý příklad v `examples/` podporuje `python script.py` (run), `-h` (help),
`graph-browser` (graf v browseru) a ostatní grafické výstupy. Celá aplikace je nakonfigurována
jako `ExampleApp(Describable)` objekt — vizualizace ukáže `LlmConnector`, `ToolRegistry`
i `StateGraph` topology jako jeden kompozitní graf.

---

## Scope

| Oblast | Co se mění |
|--------|-----------|
| `agentflow/app.py` (nový) | `ExampleApp` base class (Describable + async run_workflow + cli()) |
| `agentflow/cli.py` | Přidat `browser` alias pro `graph-browser` do `run_argparse()` |
| `agentflow/statemachine/topology.py` | Override `StateGraph._build_vertex()` — exponuje topology vrcholy jako děti |
| `agentflow/__init__.py` | Export `ExampleApp` |
| `examples/quickstart/01–05` | Refaktoring na `ExampleApp` DI vzor |
| `examples/patterns/04_react_agent_statemachine.py` | Refaktoring na `ExampleApp` |
| `examples/quickstart/00_hello_world.py` (nový) | README Hello World jako spustitelný ExampleApp |
| `docs/examples/hello_world_graph.svg` (nový) | Pre-generovaný SVG graf Hello Worldu |
| `README.md` | Vložit graph SVG pod Hello World sekci |

---

## Task List

| Task | Název | Závisí na |
|------|-------|-----------|
| T010 | Framework: ExampleApp + StateGraph._build_vertex + cli alias | — |
| T020 | Refaktoring příkladů quickstart 01-05 + patterns 04 | T010 |
| T030 | Hello World skript + generování SVG + README embed | T010 |

---

## T010 — Framework

### `agentflow/app.py` — nová třída

```python
class ExampleApp(Describable):
    """Base for runnable example applications with full describe/visualize support.

    Configure all components (connector, registry, graph) as public Describable
    attributes in __init__. Implement run_workflow() with the main logic.
    Use cli() as the if __name__ == "__main__" entry-point.

    Pattern: Template Method (GoF) — cli() orchestrates, run_workflow() specialises.
    """

    async def run_workflow(self) -> None:
        """Execute the main example workflow. Must be overridden by subclass."""
        raise NotImplementedError

    def run(self) -> str | None:
        """Synchronous wrapper for run_workflow(); called by Describable.run_argparse()."""
        import asyncio
        asyncio.run(self.run_workflow())
        return None

    def cli(self, doc: str | None = None, *, name: str = "") -> None:
        """Parse sys.argv and run or visualize this application.

        Default command: run. Commands: run, graph-browser, graph-html,
        graph-svg, graph-svg-raw, graph-dot, graph-png, browser (alias).
        """
        self.run_argparse(doc=doc, name=name, default_command="run")
```

### `agentflow/cli.py` — browser alias

V `Describable.run_argparse()` přidat `browser` jako alias/subparser pro `graph-browser`
tak aby `script.py browser` fungovalo stejně jako `script.py graph-browser`.
(Nejjednodušší: before `parser.parse_args()` zkontrolovat `sys.argv` a substituovat.)

Nebo přidat 'browser' jako extra subparser s `nargs='?'` který deleguje na `graph-browser`.

### `agentflow/statemachine/topology.py` — `StateGraph._build_vertex()`

Override musí exponovat topology vrcholy jako děti vertexu StateGraph v composite tree.
Přečíst `StateGraph.get_graph()` a použít jeho výstup:

```python
def _build_vertex(self, vertex_id: str) -> "Vertex":
    """Expose topology nodes as children when embedded in a parent Describable."""
    from agentflow.describable.graph import Vertex
    topology = self.get_graph()   # existing topology graph
    # The topology Graph has vertices; expose them as children of this vertex
    return Vertex(
        id=vertex_id,
        label=type(self).__name__,
        description=self.get_description_item_dict(),
        children=list(topology.root.children),  # adjust to actual Graph structure
    )
```

### Export

Přidat do `agentflow/__init__.py`: `from agentflow.app import ExampleApp`

### Tests

- `tests/agentflow/test_example_app.py` — smoke test: subclass `ExampleApp`, volat `run()`, ověřit `get_graph()` vrací netriviální graf
- Existující `test_state_graph_describable.py` — přidat test který ověří, že `StateGraph` vnořený v nadřazeném `Describable` exponuje topology vrcholy jako děti (ne prázdný list)

---

## T020 — Refaktoring příkladů

Pro každý příklad, vzor refaktoringu:

**PŘED:**
```python
def build_graph() -> StateGraph: ...
def run_demo() -> FinalState: ...

if __name__ == "__main__":
    final = run_demo()
    print(final)
```

**PO:**
```python
from agentflow import ExampleApp

class BriefExampleApp(ExampleApp):
    """Parallel research graph: Research → Parallel(Write*) → Review → loop."""

    def __init__(self) -> None:
        super().__init__()
        self.connector = FakeLlmConnector()
        self.graph = StateGraph(start=Research, transitions=[...])

    async def run_workflow(self) -> None:
        ctx = Context(connector=self.connector)
        runner = StateGraphRunner(self.graph, ctx, hooks=LoggingHooks())
        final = runner.run_sync(DemoState())
        print(f"Done: iteration={final.iteration}")

if __name__ == "__main__":
    BriefExampleApp().cli(__doc__, name=__name__)
```

**Příklady k refaktoringu:**

| Soubor | Třída | Connector | Registry | Graph |
|--------|-------|-----------|----------|-------|
| `quickstart/01_brief_example.py` | `BriefExampleApp` | `FakeLlmConnector` | — | StateGraph |
| `quickstart/02_tool_agent_demo.py` | `ToolAgentDemoApp` | `FakeLlmConnector` | — | StateGraph + ToolAgent |
| `quickstart/03_live_graph_demo.py` | `LiveGraphDemoApp` | `FakeLlmConnector` | — | StateGraph + LiveGraphHooks |
| `quickstart/04_parallel_research_loop.py` | `ParallelResearchApp` | `FakeLlmConnector` | — | StateGraph |
| `quickstart/05_human_in_the_loop_demo.py` | `HumanInTheLoopApp` | `FakeLlmConnector` | — | StateGraph |
| `patterns/04_react_agent_statemachine.py` | `ReactAgentApp` | `LlmConnector.create(env)` | `ToolRegistry([Calculator])` | StateGraph |

Každý příklad: aktualizovat docstring `Run with:` sekci.

---

## T030 — Hello World + README

### `examples/quickstart/00_hello_world.py`

Implementuje Hello World z README jako ExampleApp:

```python
"""Minimal agentflow hello world: Uppercase → Done.

The simplest possible StateGraph — no LLM calls, pure state transformation.
Uses FakeLlmConnector.
"""
from agentflow import ExampleApp
...

class HelloWorldApp(ExampleApp):
    def __init__(self) -> None:
        super().__init__()
        self.connector = FakeLlmConnector()
        self.graph = StateGraph(start=Uppercase, transitions=[...])

    async def run_workflow(self) -> None:
        ...
        print(final.text)  # HELLO

if __name__ == "__main__":
    HelloWorldApp().cli(__doc__, name=__name__)
```

### Generování SVG

Spustit:
```bash
uv run python examples/quickstart/00_hello_world.py graph-svg-raw -o docs/examples/hello_world_graph.svg
```

SVG musí být commitnuté (ne v nogit_data) — zobrazí se přímo v GitHub README.

### README.md update

Pod Hello World code block (za ukázkou kódu) přidat:

```markdown
Graph topology of this example:

![Hello World graph](docs/examples/hello_world_graph.svg)
```

---

## Definition of Done (Epic Level)

- [ ] `ExampleApp` exportován z `agentflow` jako veřejný symbol
- [ ] `StateGraph` vnořený v ExampleApp exponuje topology vrcholy ve vizualizaci
- [ ] `script.py` (no args) — spustí workflow
- [ ] `script.py -h` — vypíše __doc__ + dostupné příkazy
- [ ] `script.py graph-browser` — otevře interaktivní graf v browseru
- [ ] `script.py browser` — stejné (alias)
- [ ] Všech 6 příkladů refaktorováno na ExampleApp DI vzor
- [ ] `docs/examples/hello_world_graph.svg` commitnutý
- [ ] README.md zobrazuje graph SVG pod Hello World sekcí
- [ ] `uv run pytest -q` zelený (170+ testů)
