"""AgentApp — base class for runnable agentflow applications.

AgentApp extends Describable so the full application composition
(LlmConnector, ToolRegistry, StateGraph) is visible as a single composite
graph via get_graph() / open_graph_browser() / etc.

Declarative usage (no subclassing)::

    from agentflow import AgentApp
    from agentflow.statemachine import Context, StateGraph

    result, stats = AgentApp(
        doc=__doc__,
        context=Context(connector=...),
        state_graph=StateGraph(start=..., transitions=[...]),
    ).run_and_stats("Hello")

Subclass usage::

    from agentflow import AgentApp
    from agentflow.statemachine import StateGraph, StateGraphRunner, Context

    class HelloApp(AgentApp):
        def __init__(self) -> None:
            super().__init__()
            self.connector = FakeLlmConnector()
            self.graph = StateGraph(start=..., transitions=[...])

        async def run_workflow(self) -> str | None:
            ctx = Context(connector=self.connector, event_bus=self.event_bus)
            runner = StateGraphRunner(self.graph, ctx)
            final = await runner.run(MyState())
            return str(final)

    if __name__ == "__main__":
        HelloApp().cli(__doc__, name=__name__)

Pattern: Template Method (GoF) — cli() orchestrates, run_workflow() specialises.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from agentflow.describable.describable import Describable
from agentflow.events import EventBus

if TYPE_CHECKING:
    from agentflow.describable.graph import Graph
    from agentflow.statemachine.context import Context
    from agentflow.statemachine.run_stats import RunStats
    from agentflow.statemachine.topology import StateGraph


class AgentApp(Describable):
    """Base for runnable agentflow applications with full describe/visualize support.

    Can be used in two ways:

    1. **Declarative** (no subclassing) — pass ``context`` and ``state_graph`` to the
       constructor and call ``run_and_stats(question)``::

           result, stats = AgentApp(
               doc=__doc__,
               context=Context(connector=..., tools=...),
               state_graph=StateGraph(start=..., transitions=[...]),
           ).run_and_stats("Hello")

    2. **Subclass** (Template Method) — override ``run_workflow()`` in a subclass::

           class HelloApp(AgentApp):
               async def run_workflow(self) -> str | None:
                   ctx = Context(connector=self.connector, event_bus=self.event_bus)
                   runner = StateGraphRunner(self.graph, ctx)
                   return str(await runner.run(MyState()))

    GUI integration: pass ``self.event_bus`` to ``Context`` in ``run_workflow()``
    so that the GUI server can stream events to connected WebSocket clients.

    Pattern: Template Method (GoF) — cli() orchestrates, run_workflow() specialises.
    """

    def __init__(
        self,
        *,
        doc: str | None = None,
        system_prompt: str = "",
        default_question: str = "",
        sample_prompts: list[str] | None = None,
        context: Context | None = None,
        state_graph: StateGraph | None = None,
        initial_state_factory: Callable[[str], Any] | None = None,
    ) -> None:
        super().__init__()
        self.event_bus: EventBus = EventBus()
        """Shared EventBus passed to Context in run_workflow() for GUI streaming."""
        self.current_prompt: str = ""
        """Last prompt set via run_workflow_with_prompt(); readable inside run_workflow()."""
        self._doc = doc
        self._system_prompt = system_prompt
        self._default_question = default_question
        self._sample_prompts = sample_prompts
        self._context = context
        self._state_graph = state_graph
        self._initial_state_factory = initial_state_factory
        self._last_ctx: Context | None = None
        # Expose state_graph as self.graph so get_graph() can find it via vars(self)
        if state_graph is not None:
            self.graph = state_graph
        # Expose context as public attribute so Describable._build_vertex() includes it
        if context is not None:
            self.context = context

    def get_graph(self) -> Graph:
        """Build a composite graph: composition tree augmented with topology edges.

        Overrides ``Describable.get_graph()`` to also collect state-machine
        transition edges from any ``StateGraph`` attribute so that the full
        workflow topology is visible when rendering the application graph.

        Parallel fan-out edges are marked with ``attributes={"parallel": True}``
        by the topology builder; the renderer draws them as dashed blue arrows.

        Usage edges (``attributes={"usage": True}``) are added when a StateVertex
        declares ``connector`` or ``tools`` fields whose values match keys in the
        bound ``Context``.  The renderer draws them as dashed undirected lines to
        the corresponding LlmConnector / ToolRegistry cluster, labelled
        ``<Vertex>-<BackendClass>-<model>`` or ``<Vertex>-Tools: <key>``.

        Returns:
            ``Graph`` with composition vertices, state-machine transition edges,
            and vertex→resource usage edges.
        """
        from agentflow.describable.graph import Graph
        from agentflow.statemachine.topology import StateGraph

        base_graph = super().get_graph()
        extra_edges = []
        seen_graphs: set[int] = set()
        for attr_value in vars(self).values():
            if isinstance(attr_value, StateGraph) and id(attr_value) not in seen_graphs:
                seen_graphs.add(id(attr_value))
                extra_edges.extend(attr_value.get_graph().edges)
        extra_edges.extend(self._build_usage_edges())
        if not extra_edges:
            return base_graph
        return Graph(root=base_graph.root, edges=extra_edges)

    def _build_usage_edges(self) -> list:
        """Build dashed 'usage' edges from StateVertices to their LLM connector / tool registry.

        Inspects each non-terminal StateVertex for ``connector`` and ``tools`` fields
        (the standard Pydantic field names for Context lookup keys).  When the field
        value is a valid key in the bound Context's ``llm_connectors`` or
        ``tool_registries`` dict, a directed edge is added from the vertex node to the
        corresponding Context child cluster.

        The target vertex ID mirrors the path produced by
        ``Context._extra_describable_children()``:
          - LLM connector  → ``<root>.context.<key>``
          - Tool registry  → ``<root>.context.tools`` (default) or
                             ``<root>.context.tools_<key>`` (non-default)

        Returns:
            List of ``Edge`` objects with ``attributes={"usage": True}``.
        """
        if self._context is None or self._state_graph is None:
            return []

        from agentflow.describable.graph import Edge
        from agentflow.statemachine.vertex import End

        edges: list[Edge] = []
        nodes = self._state_graph._collect_topology_nodes()
        node_ids = self._state_graph._build_node_ids(nodes)

        root_id = type(self).__name__
        context_prefix = f"{root_id}.context"

        llm_keys: set[str] = set(self._context.llm_connectors.keys())
        reg_keys: set[str] = set(self._context.tool_registries.keys())

        for node in nodes:
            if isinstance(node, End):
                continue
            node_vertex_id = node_ids[id(node)]

            connector_val = getattr(node, "connector", None)
            if isinstance(connector_val, str) and connector_val in llm_keys:
                llm_connector = self._context.llm_connectors[connector_val]
                edges.append(Edge(
                    from_id=node_vertex_id,
                    to_id=f"{context_prefix}.{connector_val}",
                    label=AgentApp._usage_llm_edge_label(node_vertex_id, llm_connector),
                    attributes={"usage": True, "usage_type": "llm"},
                ))

            tools_val = getattr(node, "tools", None)
            if isinstance(tools_val, str) and tools_val in reg_keys:
                # Mirrors Context._extra_describable_children naming
                display = "tools" if tools_val == "default" else f"tools_{tools_val}"
                edges.append(Edge(
                    from_id=node_vertex_id,
                    to_id=f"{context_prefix}.{display}",
                    label=AgentApp._usage_tools_edge_label(node_vertex_id, tools_val),
                    attributes={"usage": True, "usage_type": "tools"},
                ))

        return edges

    @staticmethod
    def _usage_llm_edge_label(vertex_id: str, connector: Any) -> str:
        """Return the dashed-edge label for a StateVertex → LLM connector link.

        Format: ``<Vertex>-<BackendConnectorClass>-<model>``.

        Args:
            vertex_id: Topology node identifier (typically the vertex class name).
            connector: ``LlmConnector`` facade or concrete ``LlmConnectorBase`` instance.

        Returns:
            Human-readable edge label for graph rendering.
        """
        backend = getattr(connector, "_inner", connector)
        class_name = type(backend).__name__
        return f"{vertex_id}-{class_name}-{connector.config.model}"

    @staticmethod
    def _usage_tools_edge_label(vertex_id: str, registry_key: str) -> str:
        """Return the dashed-edge label for a StateVertex → ToolRegistry link.

        Format: ``<Vertex>-Tools: <registry-key>``.

        Args:
            vertex_id: Topology node identifier (typically the vertex class name).
            registry_key: Key into ``Context.tool_registries``.

        Returns:
            Human-readable edge label for graph rendering.
        """
        return f"{vertex_id}-Tools: {registry_key}"

    async def run_workflow(self) -> str | None:
        """Execute the main application workflow.

        When ``context`` and ``state_graph`` were passed to the constructor this
        method runs the graph automatically.  Override in subclasses to implement
        custom workflow logic.

        Returns:
            Optional summary string shown in the GUI chat panel as the run result.
            Returns None to display a default 'Completed.' fallback.

        Raises:
            NotImplementedError: If neither context+state_graph were supplied nor
                the method is overridden in a subclass.
        """
        if self._context is None or self._state_graph is None:
            raise NotImplementedError(
                f"{type(self).__name__}.run_workflow(): "
                "Either provide context and state_graph in the constructor, "
                "or override run_workflow() in a subclass."
            )
        from agentflow.statemachine.context import Context as _Context
        from agentflow.statemachine.runner import StateGraphRunner

        ctx = _Context(
            llm_connectors=self._context.llm_connectors,
            tool_registries=self._context.tool_registries,
            connector=self._context.connector,
            tools=self._context.tools,
            event_bus=self.event_bus,
        )
        self._last_ctx = ctx
        initial_state = self._build_initial_state(self.current_prompt)
        runner = StateGraphRunner(self._state_graph, ctx)
        final_state = await runner.run(initial_state)
        return self._extract_result(final_state)

    def _build_initial_state(self, question: str) -> Any:
        """Construct the initial state for the graph run.

        Uses ``initial_state_factory`` if provided; otherwise builds a default
        ``ReActState`` with the system prompt and user question.

        Args:
            question: User question / prompt for this run.

        Returns:
            Initial state object passed to ``StateGraphRunner.run()``.
        """
        if self._initial_state_factory is not None:
            return self._initial_state_factory(question)
        from agentflow.statemachine.react import ReActState

        msgs: list[dict[str, Any]] = []
        if self._system_prompt:
            msgs.append({"role": "system", "content": self._system_prompt})
        if question:
            msgs.append({"role": "user", "content": question})
        return ReActState(messages=tuple(msgs))

    def _extract_result(self, final_state: Any) -> str | None:
        """Extract a result string from the final graph state.

        Tries common field names in priority order; falls back to ``str(final_state)``.

        Args:
            final_state: State object returned by ``StateGraphRunner.run()``.

        Returns:
            Result string, or None if final_state is None.
        """
        for field_name in ("final_response", "final_answer", "result", "output"):
            val = getattr(final_state, field_name, None)
            if val:
                return str(val)
        return str(final_state) if final_state is not None else None

    def run_and_stats(self, question: str) -> tuple[str | None, RunStats]:
        """Run the workflow synchronously and return the result with token/timing stats.

        Convenience method for scripts that need a single-call entry point without
        setting up a GUI or CLI.  Internally calls ``run_workflow_with_prompt()``
        via ``asyncio.run()``.

        Args:
            question: User question / prompt to run the workflow with.

        Returns:
            Tuple of (result string or None, RunStats with token counts and wall time).
        """
        from agentflow.statemachine.run_stats import RunStats as _RunStats

        self._last_ctx = None
        start = time.monotonic()
        result = asyncio.run(self.run_workflow_with_prompt(question))
        elapsed_ms = (time.monotonic() - start) * 1000
        stats = _RunStats()
        if self._last_ctx is not None:
            stats = self._last_ctx.stats
        stats.wall_time_ms = elapsed_ms
        return result, stats

    @property
    def sample_prompts(self) -> list[str]:
        """Return a list of example prompts shown in the GUI prompt selector.

        Returns prompts passed to the constructor, or an empty list by default.
        Override in subclasses to provide domain-specific example prompts.

        Returns:
            List of prompt strings.
        """
        if self._sample_prompts is not None:
            return self._sample_prompts
        return []

    async def run_workflow_with_prompt(self, prompt: str) -> str | None:
        """Set current_prompt then execute run_workflow().

        Called by the GUI server so the prompt is available to subclasses
        via ``self.current_prompt`` inside ``run_workflow()``.

        Args:
            prompt: User-supplied prompt string.

        Returns:
            The return value of ``run_workflow()``.
        """
        self.current_prompt = prompt
        return await self.run_workflow()

    def run(self, question: str | None = None, **_kwargs: Any) -> str | None:
        """Synchronously execute run_workflow(); called by ``run_argparse`` ``run``.

        Args:
            question: When provided, sets ``current_prompt`` before the workflow runs.

        Returns:
            The return value of run_workflow() — a summary string or None.
        """
        if question is not None:
            self.current_prompt = question
        return asyncio.run(self.run_workflow())

    def get_config_schema(self) -> dict[str, Any]:
        """Return a hierarchical JSON Schema of all configurable parameters.

        Scans public attributes for LlmConnector instances and uses the
        Pydantic ``model_json_schema()`` on their underlying LlmConfig to
        build the schema.

        Returns:
            JSON-Schema-compatible dict with ``properties`` keyed by
            attribute name (e.g. ``{"connector": {...LlmConfig schema...}}``).
        """
        from pydantic import BaseModel

        schema: dict[str, Any] = {
            "type": "object",
            "title": type(self).__name__,
            "properties": {},
        }
        from agentflow.llm.LlmConnectorBase import LlmConnectorBase as LlmConnector

        for attr_name, attr_value in vars(self).items():
            if attr_name.startswith("_"):
                continue
            if isinstance(attr_value, LlmConnector):
                try:
                    config = attr_value.config
                except NotImplementedError:
                    continue  # FakeLlmConnector and similar stubs — skip gracefully
                if isinstance(config, BaseModel):
                    schema["properties"][attr_name] = config.model_json_schema()
        return schema

    def get_config(self) -> dict[str, Any]:
        """Return current values of all configurable parameters as a flat dot-path dict.

        Example return value::

            {
                "connector.backend": "ollama",
                "connector.model": "qwen2.5:1.5b",
                "connector.timeout": 120.0,
            }

        Returns:
            Dict mapping dot-path strings to current parameter values.
        """
        from pydantic import BaseModel

        result: dict[str, Any] = {}
        from agentflow.llm.LlmConnectorBase import LlmConnectorBase as LlmConnector

        for attr_name, attr_value in vars(self).items():
            if attr_name.startswith("_"):
                continue
            if isinstance(attr_value, LlmConnector):
                try:
                    config = attr_value.config
                except NotImplementedError:
                    continue  # FakeLlmConnector and similar stubs — skip gracefully
                if isinstance(config, BaseModel):
                    for field_name in type(config).model_fields:
                        result[f"{attr_name}.{field_name}"] = getattr(config, field_name)
        return result

    def set_config(self, path: str, value: Any) -> None:
        """Set a single configurable parameter by dot-path notation.

        Supports setting fields on LlmConnector's underlying LlmConfig.

        Args:
            path: Dot-path string in the form ``"child.param"``,
                  e.g. ``"connector.model"`` or ``"connector.timeout"``.
            value: New value to assign.  Must pass Pydantic validation.

        Raises:
            KeyError: If the path format is invalid or the child/param is unknown.
            ValueError: If the value fails Pydantic field validation.
        """
        from pydantic import BaseModel

        parts = path.split(".", 1)
        if len(parts) != 2:
            raise KeyError(
                f"Invalid config path: {path!r} — expected 'child.param' format"
            )
        child_name, param_name = parts
        child = getattr(self, child_name, None)
        if child is None:
            raise KeyError(f"No attribute {child_name!r} on {type(self).__name__}")

        from agentflow.llm.LlmConnectorBase import LlmConnectorBase as LlmConnector

        if isinstance(child, LlmConnector):
            config = child.config
            if not isinstance(config, BaseModel):
                raise KeyError(
                    f"{type(child).__name__}.config is not a Pydantic model"
                )
            if param_name not in type(config).model_fields:
                raise KeyError(
                    f"Unknown config field {param_name!r} on {type(config).__name__}"
                )
            setattr(config, param_name, value)
            return

        raise KeyError(
            f"Attribute {child_name!r} on {type(self).__name__} does not support set_config"
        )

    def _cli_start_gui(
        self,
        *,
        host: str = "127.0.0.1",
        port: int | None = None,
        no_browser: bool = False,
    ) -> None:
        """Start the AgentApp web GUI server (``gui`` subcommand).

        Args:
            host: Bind address for the HTTP server.
            port: TCP port; ``None`` uses 8765 or ``AGENTFLOW_GUI_PORT``.
            no_browser: When ``True``, do not open a browser tab automatically.

        Raises:
            SystemExit: When the optional ``agentflow[gui]`` extra is not installed.
        """
        import sys
        from pathlib import Path

        try:
            from agentflow.gui import serve
            from agentflow.gui.build import discover_and_build
        except ImportError:
            print(
                "GUI not available. Install with: pip install agentflow[gui]",
                file=sys.stderr,
            )
            sys.exit(1)
        app_script = Path(sys.argv[0]).resolve()
        discover_and_build(app_script=app_script)
        serve(self, port=port, host=host, open_browser=not no_browser)

    def cli(self, doc: str | None = None, *, name: str = "") -> None:
        """Parse ``sys.argv`` and run, visualize, or serve GUI for this application.

        Top-level commands (see ``Describable.run_argparse``)::

            run        [QUESTION...]  Execute ``run_workflow()``
            gui        [--host HOST] [--port PORT] [--no-browser]
            describe   [--format markdown|json|html] [-o FILE]
            graph      [--format …] [-o FILE]  |  graph --browser

        With no arguments, prints main ``--help`` and does not run the workflow.

        Args:
            doc: Module docstring (__doc__) used as the CLI description.
                 Falls back to the ``doc`` argument passed to the constructor.
            name: Module name guard — pass __name__ to run only when the
                  script is the direct entry-point (not when imported).
        """
        effective_doc = doc or self._doc
        default_q = self._default_question or None
        self.run_argparse(
            doc=effective_doc,
            name=name,
            default_question=default_q,
            title_tooltip=effective_doc or self.description,
            include_gui=True,
        )
