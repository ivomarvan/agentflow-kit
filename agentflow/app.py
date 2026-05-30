"""AgentApp — base class for runnable agentflow applications.

AgentApp extends Describable so the full application composition
(LlmConnector, ToolRegistry, StateGraph) is visible as a single composite
graph via get_graph() / open_graph_browser() / etc.

Usage in an example script::

    from agentflow import AgentApp
    from agentflow.statemachine import StateGraph, StateGraphRunner, Context
    from agentflow.statemachine.testing import FakeLlmConnector

    class HelloApp(AgentApp):
        def __init__(self) -> None:
            super().__init__()
            self.connector = FakeLlmConnector()
            self.graph = StateGraph(start=..., transitions=[...])

        async def run_workflow(self) -> str | None:
            # Pass self.event_bus to Context so GUI can receive events
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
from typing import Any

from agentflow.describable.describable import Describable
from agentflow.events import EventBus


class AgentApp(Describable):
    """Base for runnable agentflow applications with full describe/visualize support.

    Subclasses configure all components (connector, registry, graph) as public
    Describable attributes in __init__ so the full composition tree is visible.
    The main workflow logic lives in run_workflow(), called by cli().

    GUI integration: pass ``self.event_bus`` to ``Context`` in ``run_workflow()``
    so that the GUI server can stream events to connected WebSocket clients::

        ctx = Context(connector=self.connector, event_bus=self.event_bus)

    Pattern: Template Method (GoF) — cli() orchestrates, run_workflow() specialises.
    """

    def __init__(self) -> None:
        super().__init__()
        self.event_bus: EventBus = EventBus()
        """Shared EventBus passed to Context in run_workflow() for GUI streaming."""
        self.current_prompt: str = ""
        """Last prompt set via run_workflow_with_prompt(); readable inside run_workflow()."""

    async def run_workflow(self) -> str | None:
        """Execute the main application workflow.

        Override in subclasses to implement the application logic.
        Called synchronously by run() and cli(default_command="run").

        Returns:
            Optional summary string shown in the GUI chat panel as the run result.
            Return None to display a default 'Completed.' fallback.

        Raises:
            NotImplementedError: If the subclass does not override this method.
        """
        raise NotImplementedError(f"{type(self).__name__}.run_workflow() not implemented")

    @property
    def sample_prompts(self) -> list[str]:
        """Return a list of example prompts shown in the GUI prompt selector.

        Override in subclasses to provide domain-specific example prompts.

        Returns:
            List of prompt strings.  Returns empty list by default.
        """
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

    def run(self, *args: Any, **kwargs: Any) -> str | None:
        """Synchronously execute run_workflow(); called by Describable.run_argparse().

        Returns:
            The return value of run_workflow() — a summary string or None.
        """
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
        from agentflow.llm.LlmConnector import LlmConnector

        for attr_name, attr_value in vars(self).items():
            if attr_name.startswith("_"):
                continue
            if isinstance(attr_value, LlmConnector):
                config = attr_value.config
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
        from agentflow.llm.LlmConnector import LlmConnector

        for attr_name, attr_value in vars(self).items():
            if attr_name.startswith("_"):
                continue
            if isinstance(attr_value, LlmConnector):
                config = attr_value.config
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

        from agentflow.llm.LlmConnector import LlmConnector

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

    def cli(self, doc: str | None = None, *, name: str = "") -> None:
        """Parse sys.argv and run, visualize, or serve GUI for this application.

        Intercepts the ``gui`` subcommand before delegating to
        ``run_argparse()``; all other commands are handled by the parent.

        Default command when no arguments given: run (executes run_workflow).

        Available commands::

            run              Execute run_workflow() (default)
            gui              Start local GUI server and open in browser
                             [--port PORT] [--host HOST] [--no-browser]
            browser          Open topology graph in the default browser
            graph-browser    Same as browser
            graph-html       Print/save standalone interactive HTML graph
            graph-svg        Print/save interactive SVG graph
            graph-svg-raw    Print/save raw SVG for embedding
            graph-dot        Print/save Graphviz DOT source
            graph-png        Save PNG graph file

        Args:
            doc: Module docstring (__doc__) used as the CLI description.
            name: Module name guard — pass __name__ to run only when the
                  script is the direct entry-point (not when imported).
        """
        import sys

        if name and name != "__main__":
            return

        if len(sys.argv) > 1 and sys.argv[1] == "gui":
            import argparse

            parser = argparse.ArgumentParser(
                description=doc or type(self).__name__,
                prog=sys.argv[0],
            )
            parser.add_argument("command", help="gui")
            parser.add_argument(
                "--port",
                type=int,
                default=None,
                help="Port (default: 8765, or AGENTFLOW_GUI_PORT env var)",
            )
            parser.add_argument("--host", default="127.0.0.1", help="Bind address")
            parser.add_argument(
                "--no-browser", action="store_true", help="Do not open the browser"
            )
            args = parser.parse_args()
            try:
                from agentflow.gui import serve
                from agentflow.gui.build import discover_and_build
            except ImportError:
                print(
                    "GUI not available. Install with: pip install agentflow[gui]",
                    file=sys.stderr,
                )
                sys.exit(1)
            from pathlib import Path
            app_script = Path(sys.argv[0]).resolve()
            discover_and_build(app_script=app_script)
            serve(self, port=args.port, host=args.host, open_browser=not args.no_browser)
        else:
            self.run_argparse(doc=doc, name=name, default_command="run")
