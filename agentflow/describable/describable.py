"""Describable — base class for self-describing objects.

Objects that inherit from ``Describable`` gain the ability to report their
own structure through a common interface, with no dependency on agent or LLM
logic whatsoever.

Public interface::

    obj.get_description_item_dict()      # dict — this object only, no composed parts
    obj.get_description_item_markdown()  # str  — derived from the item dict
    obj.get_description_item_html()      # str  — derived from the item dict
    obj.get_description_dict()           # dict — full tree including composed parts
    obj.get_description_markdown()       # str  — derived from the full dict
    obj.get_description_html()           # str  — derived from the full dict
    obj.get_graph()                      # Graph — composition tree (data only)
    obj.get_graph_dot()                  # str  — Graphviz DOT source (with plain-text tooltips)
    obj.get_graph_svg()                  # str  — raw SVG, suitable for embedding in documents
    obj.get_graph_interactive_svg()      # str  — SVG with embedded JS hover tooltips
    obj.get_graph_png(path=None)         # Path — PNG file via Graphviz dot tool
    obj.get_graph_html(title="")         # str  — standalone HTML page with hover tooltips
    obj.open_graph_browser(title="")     # None — renders HTML and opens browser (API)
    obj.run()                            # str | None — no-op default; override in runnable objects
    obj.run_argparse(doc=__doc__, name=__name__)   # CLI entry-point (see below)

CLI (``run_argparse`` / ``AgentApp.cli()``)::

    script.py -h
    script.py run [QUESTION...]
    script.py gui [--host HOST] [--port PORT] [--no-browser]   # AgentApp only
    script.py describe [--format markdown|json|html] [-o|--output FILE]
    script.py graph [--format dot|svg|svg-raw|html|png] [-o|--output FILE]
    script.py graph --browser

    With no arguments, prints main help and exits (no implicit run).

Subclassing contract::

    class MyClass(Describable):
        def __init__(self, param: str, child: OtherDescribable) -> None:
            super().__init__()    # sets self.name = type(self).__name__, self.description = __doc__
            self.param = param    # public scalar  → appears in get_description_item_dict()
            self.child = child    # Describable    → becomes a child vertex in get_graph()

    # Override _get_own_attributes() when scalars are stored privately:
    class MyClass(Describable):
        def __init__(self, secret: str) -> None:
            super().__init__()
            self._secret = secret    # private — skipped by default introspection

        def _get_own_attributes(self) -> dict[str, Any]:
            d = super()._get_own_attributes()
            d["secret"] = self._secret   # explicitly expose it
            return d
"""

from __future__ import annotations

import argparse
import html
import inspect
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentflow.describable.graph import Graph, Vertex


def _patch_subcommand_help_on_error(parser: argparse.ArgumentParser) -> None:
    """Make *parser* print its full help (not only usage) on argparse errors."""

    def error(message: str) -> None:
        parser.print_usage(sys.stderr)
        sys.stderr.write(f"{parser.prog}: error: {message}\n\n")
        parser.print_help(sys.stderr)
        raise SystemExit(2)

    parser.error = error  # type: ignore[method-assign]


class _SubcommandHelpArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that prints full help on any parse error."""

    def error(self, message: str) -> None:
        """Print usage, the error message, and help; exit with code 2."""
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: error: {message}\n\n")
        self.print_help(sys.stderr)
        raise SystemExit(2)


_DESCRIBE_FORMATS: tuple[str, ...] = ("markdown", "json", "html")
_GRAPH_FORMATS: tuple[str, ...] = ("dot", "svg", "svg-raw", "html", "png")

_CLI_HELP_SECTIONS: tuple[str, ...] = ("positional arguments:", "options:")


class Describable:
    """Base class for objects that can describe their own structure.

    Sets ``self.name`` (from the class name) and ``self.description`` (from
    the class docstring) in ``__init__``.

    Subclasses **must** call ``super().__init__()`` to ensure these attributes
    are always present.

    ``get_description_item_dict()`` describes **this object only** — scalar
    attributes and inline data structures, but not nested ``Describable``
    components.

    ``get_description_dict()`` builds on the item dict and adds recursively
    serialised composed parts (nested ``Describable`` instances and lists of
    them).
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialise common identity attributes.

        Sets ``self.name`` to the class name and ``self.description`` to the
        class docstring.  Subclasses may override ``self.name`` after calling
        ``super().__init__()``.

        Accepts and forwards ``**kwargs`` to support cooperative multiple
        inheritance (e.g. when combined with Pydantic ``BaseModel`` — kwargs
        are forwarded to ``BaseModel.__init__`` for field initialisation).

        Args:
            **kwargs: Forwarded to the next class in the MRO.
        """
        # Use object.__setattr__ to bypass Pydantic's __setattr__ when this
        # class is combined with BaseModel via multiple inheritance — Pydantic
        # has not yet initialised __pydantic_extra__ at this point in the MRO.
        object.__setattr__(self, "name", type(self).__name__)
        object.__setattr__(self, "description", inspect.getdoc(type(self)) or "")
        super().__init__(**kwargs)

    # ------------------------------------------------------------------
    # Hook — override in subclasses to customise which attrs are described
    # ------------------------------------------------------------------

    def _get_own_attributes(self) -> dict[str, Any]:
        """Return a dict of this object's own scalar public attributes.

        Called by ``get_description_item_dict()`` to collect the attributes
        that describe this object without its composed parts.

        The default implementation reads all public instance attributes
        (those not prefixed with ``_``) and skips ``Describable`` instances
        and homogeneous lists of ``Describable`` objects.

        Override in subclasses that store relevant scalars privately (e.g.
        ``self._system_prompt``) so they still appear in the description.

        Returns:
            Dict mapping attribute name → value, excluding nested
            ``Describable`` instances.
        """
        result: dict[str, Any] = {}
        for key, value in vars(self).items():
            if key.startswith("_"):
                continue
            if isinstance(value, Describable):
                continue
            if isinstance(value, list) and value and all(
                isinstance(item, Describable) for item in value
            ):
                continue
            result[key] = value
        return result

    # ------------------------------------------------------------------
    # Public — description methods
    # ------------------------------------------------------------------

    def get_description_item_dict(self) -> dict[str, Any]:
        """Return a dict describing this object only, without composed parts.

        Delegates to ``_get_own_attributes()`` for attribute values.
        Subclasses customise what appears here by overriding
        ``_get_own_attributes()``.

        Returns:
            Dict with a ``"_type"`` key (class name) plus inline entries.
        """
        result: dict[str, Any] = {"_type": type(self).__name__}
        result.update(self._get_own_attributes())
        return result

    def get_description_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict describing this object and its parts.

        Starts from ``get_description_item_dict()`` and adds recursively
        serialised nested ``Describable`` components found in ``vars(self)``.

        Returns:
            Dict with ``"_type"`` plus inline and composed entries.
        """
        result = self.get_description_item_dict()
        for key, value in vars(self).items():
            if key.startswith("_"):
                continue
            if isinstance(value, Describable):
                result[key] = value.get_description_dict()
            elif isinstance(value, list):
                components = [
                    item.get_description_dict()
                    for item in value
                    if isinstance(item, Describable)
                ]
                if components:
                    result[key] = components
        return result

    def get_description_item_markdown(self) -> str:
        """Return Markdown for this object only, derived from get_description_item_dict().

        Nested dict values are expanded hierarchically down to scalars.

        Returns:
            Multi-line Markdown string.
        """
        return self._item_dict_to_markdown(self.get_description_item_dict())

    def get_description_item_html(self) -> str:
        """Return a standalone HTML page for this object only.

        Nested dict values are expanded hierarchically down to scalars.

        Returns:
            Complete self-contained HTML string.
        """
        body = self._item_dict_to_html(self.get_description_item_dict())
        return self._wrap_html_page(body)

    def get_description_markdown(self) -> str:
        """Return a Markdown-formatted description derived from get_description_dict().

        Returns:
            Multi-line Markdown string.
        """
        return self._dict_to_markdown(self.get_description_dict(), level=1)

    def get_description_html(self) -> str:
        """Return a standalone HTML page describing this object's full structure.

        Uses collapsible ``<details>/<summary>`` elements for nested objects.

        Returns:
            Complete self-contained HTML string.
        """
        body = self._dict_to_html(self.get_description_dict())
        return self._wrap_html_page(body)

    # ------------------------------------------------------------------
    # Public — runtime configuration (GUI Settings tab)
    # ------------------------------------------------------------------

    def get_config_schema(self) -> dict[str, Any]:
        """Return a JSON Schema dict for all scalar configurable parameters.

        For Pydantic BaseModel instances delegates to ``model_json_schema()``
        and filters to scalar types only.  For non-Pydantic instances builds
        the schema from ``__init__`` type hints via ``_schema_from_init()``.

        Returns:
            JSON Schema dict; empty dict if no configurable params found.
        """
        from pydantic import BaseModel

        if isinstance(self, BaseModel):
            schema = self.model_json_schema()
            props = schema.get("properties", {})
            scalar_types = {"string", "integer", "number", "boolean"}
            filtered = {
                k: v
                for k, v in props.items()
                if isinstance(v, dict) and v.get("type") in scalar_types
            }
            return {**schema, "properties": filtered}
        return self._schema_from_init()

    def _schema_from_init(self) -> dict[str, Any]:
        """Build a minimal JSON Schema from ``__init__`` type hint annotations.

        Inspects the ``__init__`` signature and type hints of this class,
        mapping Python scalar types to JSON Schema types.  Parameters of
        complex types (lists, dicts, custom classes) are silently skipped.

        Returns:
            JSON Schema dict with ``"type": "object"`` and ``"properties"``
            for each discovered scalar parameter; empty dict if none found.
        """
        import inspect
        from typing import get_args, get_origin, get_type_hints

        from pydantic.fields import FieldInfo

        sig = inspect.signature(type(self).__init__)
        try:
            hints = get_type_hints(type(self).__init__, include_extras=True)
        except Exception:
            return {}

        type_map: dict[type, str] = {
            int: "integer",
            float: "number",
            str: "string",
            bool: "boolean",
        }

        properties: dict[str, Any] = {}
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "args", "kwargs"):
                continue
            hint = hints.get(param_name)
            if hint is None:
                continue
            origin = get_origin(hint)
            args = get_args(hint)
            base_type = args[0] if origin is not None and args else hint
            json_type = type_map.get(base_type)
            if json_type is None:
                continue
            prop: dict[str, Any] = {"type": json_type}
            if param.default is not inspect.Parameter.empty:
                prop["default"] = param.default
            if origin is not None:
                for meta in args[1:]:
                    if isinstance(meta, FieldInfo) and meta.description:
                        prop["description"] = meta.description
            properties[param_name] = prop

        if not properties:
            return {}
        return {"type": "object", "properties": properties}

    def get_param_values(self) -> dict[str, Any]:
        """Return current values of all configurable scalar parameters.

        Returns:
            Dict mapping parameter name to current attribute value.
        """
        schema = self.get_config_schema()
        params = schema.get("properties", {})
        return {
            name: getattr(self, name)
            for name in params
            if hasattr(self, name)
        }

    def set_params(self, **kwargs: Any) -> None:
        """Update configurable scalar parameters at runtime.

        Used by the GUI Settings tab to apply user edits without recreating
        the object.  Unknown keys are logged as warnings and ignored; valid
        keys are applied via ``setattr``.

        Args:
            **kwargs: Parameter names and new values.

        Raises:
            Nothing — invalid keys are warned, not raised.
        """
        import logging

        schema = self.get_config_schema()
        valid_keys = set(schema.get("properties", {}).keys())
        _log = logging.getLogger(__name__)
        for key, value in kwargs.items():
            if key not in valid_keys:
                _log.warning(
                    "set_params: unknown parameter %r (valid: %s)", key, sorted(valid_keys)
                )
                continue
            setattr(self, key, value)

    def get_graph(self) -> Graph:
        """Build a composition Graph rooted at this object.

        The base implementation creates vertices from introspection only — no
        edges are added.  Subclasses may override to add semantic edges
        (data-flow, call relationships, state transitions, …) after calling
        ``super().get_graph()``.

        Returns:
            ``Graph`` with a root ``Vertex`` and an empty edge list.
        """
        from agentflow.describable.graph import Graph  # lazy import — keeps module standalone
        root = self._build_vertex(type(self).__name__)
        return Graph(root=root)

    def get_graph_dot(self) -> str:
        """Return the Graphviz DOT source for this object's composition graph.

        Returns:
            Multi-line DOT source string.
        """
        from agentflow.describable.graph_renderer import GraphRenderer
        return GraphRenderer.to_dot(self.get_graph())

    def get_graph_svg(self) -> str:
        """Render this object's composition graph to a raw SVG string.

        The raw SVG is suitable for embedding in documents or presentations.
        For a browser-ready file with interactive hover tooltips use
        ``get_graph_interactive_svg()`` instead.

        Returns:
            SVG XML string (no embedded JavaScript).

        Raises:
            ImportError: If the ``graphviz`` Python package is not installed.
        """
        from agentflow.describable.graph_renderer import GraphRenderer
        return GraphRenderer.to_svg(self.get_graph())

    def get_graph_interactive_svg(self) -> str:
        """Render this object's composition graph to a self-contained interactive SVG.

        The SVG file can be saved and opened directly in a browser.  Hovering
        over any vertex or cluster shows a rich Markdown tooltip identical to
        the HTML output.  A minimal fallback renderer is embedded inline;
        ``marked.js`` is loaded from CDN when the file is opened in a browser.

        Returns:
            Interactive SVG string with embedded JavaScript and CSS.

        Raises:
            ImportError: If the ``graphviz`` Python package is not installed.
        """
        from agentflow.describable.graph_renderer import GraphRenderer
        return GraphRenderer.to_interactive_svg(self.get_graph())

    def get_graph_png(self, path: Path | None = None) -> Path:
        """Render this object's composition graph to a PNG file.

        Args:
            path: Output file path.  When ``None``, a temporary file is used.

        Returns:
            Path to the rendered PNG file.

        Raises:
            ImportError: If the ``graphviz`` Python package is not installed.
        """
        from agentflow.describable.graph_renderer import GraphRenderer
        return GraphRenderer.to_png(self.get_graph(), path=path)

    def get_graph_html(self, title: str = "", title_tooltip: str = "") -> str:
        """Return a standalone interactive HTML page for this object's graph.

        Args:
            title: Page title.  Defaults to ``self.name``.
            title_tooltip: Markdown shown as tooltip when hovering the title.

        Returns:
            Complete self-contained HTML string with hover tooltips.

        Raises:
            ImportError: If the ``graphviz`` Python package is not installed.
        """
        from agentflow.describable.graph_renderer import GraphRenderer
        return GraphRenderer.to_html(
            self.get_graph(), title=title or type(self).__name__, title_tooltip=title_tooltip
        )

    def open_graph_browser(self, title: str = "", title_tooltip: str = "") -> None:
        """Render this object's graph as HTML and open it in the default browser.

        Args:
            title: Forwarded to ``get_graph_html()``.
            title_tooltip: Forwarded to ``get_graph_html()``.
        """
        from agentflow.describable.graph_renderer import GraphRenderer
        GraphRenderer.open_browser(
            self.get_graph(), title=title or type(self).__name__, title_tooltip=title_tooltip
        )

    # ------------------------------------------------------------------
    # Public — execution and CLI
    # ------------------------------------------------------------------

    def run(self) -> str | None:
        """Execute this object and return a result string.

        The base implementation is a deliberate no-op — override in subclasses
        that represent a runnable top-level component (e.g. ``ToolAgent``).

        Returns:
            Result string, or ``None`` when not implemented.
        """
        return None

    def _cli_start_gui(
        self,
        *,
        host: str = "127.0.0.1",
        port: int | None = None,
        no_browser: bool = False,
    ) -> None:
        """Start the local web GUI (stub — override in ``AgentApp``).

        Args:
            host: Bind address for the HTTP server.
            port: TCP port; ``None`` uses implementation default / env.
            no_browser: When ``True``, do not open a browser tab automatically.
        """
        _ = (host, port, no_browser)
        print("GUI is not available for this object.", file=sys.stderr)
        sys.exit(1)

    def run_argparse(
        self,
        doc: str | None = None,
        *,
        name: str = "",
        default_question: str | None = None,
        title: str = "",
        title_tooltip: str = "",
        include_gui: bool = False,
    ) -> None:
        """Parse ``sys.argv`` and execute the requested CLI command.

        Top-level commands::

            run        [QUESTION...]  Run this object once (no implicit default).
            gui        [--host HOST] [--port PORT] [--no-browser]
            describe   [--format markdown|json|html] [-o FILE]
            graph      [--format dot|svg|svg-raw|html|png] [-o FILE]
            graph      --browser

        With no arguments, prints main ``--help`` and exits without running anything.

        Subclasses may register extra commands via ``_add_argparse_commands(subparsers)``
        and dispatch them in ``_handle_argparse_command(args)``.

        Args:
            doc: Module docstring (``__doc__``) used as the CLI description.
            name: Module name guard.  Pass ``__name__`` to run only when the
                  script is the entry-point; omit or pass ``""`` to always run.
            default_question: When set, ``run`` with no ``QUESTION`` uses this value.
            title: Title shown in graph HTML output.  Defaults to ``self.name``.
            title_tooltip: Markdown tooltip for the graph HTML title.
            include_gui: When ``True``, register the ``gui`` subcommand.
        """
        if name and name != "__main__":
            return

        root_prog = Path(sys.argv[0]).name
        command_entries: list[tuple[str, str, argparse.ArgumentParser]] = []

        parser = _SubcommandHelpArgumentParser(
            prog=root_prog,
            description=doc,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        subparsers = parser.add_subparsers(dest="command")

        p_run = subparsers.add_parser(
            "run",
            help="Run this object once from the command line.",
        )
        p_run.prog = f"{root_prog} run"
        p_run.add_argument(
            "question",
            nargs="*",
            metavar="QUESTION",
            help="Optional prompt passed to run() (words joined with spaces).",
        )
        command_entries.append((
            "run",
            "Run this object once from the command line.",
            p_run,
        ))

        if include_gui:
            p_gui = subparsers.add_parser(
                "gui",
                help="Start the local web GUI server and open it in the browser.",
            )
            p_gui.prog = f"{root_prog} gui"
            p_gui.add_argument(
                "--host",
                default="127.0.0.1",
                help="Bind address (default: 127.0.0.1).",
            )
            p_gui.add_argument(
                "--port",
                type=int,
                default=None,
                help="TCP port (default: 8765 or AGENTFLOW_GUI_PORT env var).",
            )
            p_gui.add_argument(
                "--no-browser",
                action="store_true",
                help="Do not open the browser automatically.",
            )
            command_entries.append((
                "gui",
                "Start the local web GUI server and open it in the browser.",
                p_gui,
            ))

        p_describe = subparsers.add_parser(
            "describe",
            help="Print or save a description of this object.",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        p_describe.prog = f"{root_prog} describe"
        _patch_subcommand_help_on_error(p_describe)
        p_describe.add_argument(
            "--format",
            choices=_DESCRIBE_FORMATS,
            default="markdown",
            help="Output format (default: markdown).",
        )
        self._add_output_arguments(p_describe)
        command_entries.append((
            "describe",
            "Print or save a description of this object.",
            p_describe,
        ))

        p_graph = subparsers.add_parser(
            "graph",
            help="Render, save, or open the composition graph.",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        p_graph.prog = f"{root_prog} graph"
        _patch_subcommand_help_on_error(p_graph)
        p_graph.add_argument(
            "--browser",
            action="store_true",
            help="Open the interactive graph in the default browser.",
        )
        p_graph.add_argument(
            "--format",
            choices=_GRAPH_FORMATS,
            default="html",
            help="Graph output format when not using --browser (default: html).",
        )
        self._add_output_arguments(p_graph)
        command_entries.append((
            "graph",
            "Render, save, or open the composition graph.",
            p_graph,
        ))

        if hasattr(self, "_add_argparse_commands"):
            self._add_argparse_commands(subparsers)
            self._append_extra_cli_command_entries(subparsers, command_entries, root_prog)

        parser.epilog = self._build_cli_command_reference(command_entries)

        if len(sys.argv) == 1:
            parser.print_help()
            sys.exit(0)

        args = parser.parse_args()
        if args.command is None:
            parser.print_help()
            sys.exit(2)

        if args.command == "run":
            self._cli_run(args, default_question=default_question)
        elif args.command == "gui":
            self._cli_start_gui(
                host=args.host,
                port=args.port,
                no_browser=args.no_browser,
            )
        elif args.command == "describe":
            self._cli_describe(args)
        elif args.command == "graph":
            self._cli_graph(args, title=title, title_tooltip=title_tooltip)
        elif hasattr(self, "_handle_argparse_command"):
            self._handle_argparse_command(args)
        else:
            parser.error(f"unknown command {args.command!r}")

    def _cli_run(
        self,
        args: argparse.Namespace,
        *,
        default_question: str | None,
    ) -> None:
        """Dispatch the ``run`` subcommand."""
        parts: list[str] = getattr(args, "question", [])
        if parts:
            question = " ".join(parts)
            result = self.run(question)  # type: ignore[call-arg]
        elif default_question is not None:
            result = self.run(default_question)  # type: ignore[call-arg]
        else:
            result = self.run()
        if result is not None:
            print(f"\n{result}")

    def _cli_describe(self, args: argparse.Namespace) -> None:
        """Dispatch the ``describe`` subcommand."""
        fmt: str = args.format
        if fmt == "json":
            content = json.dumps(self.get_description_dict(), indent=2, ensure_ascii=False)
        elif fmt == "html":
            content = self.get_description_html()
        else:
            content = self.get_description_markdown()
        self._cli_write_output(content, getattr(args, "output_file", None))

    def _cli_graph(
        self,
        args: argparse.Namespace,
        *,
        title: str,
        title_tooltip: str,
    ) -> None:
        """Dispatch the ``graph`` subcommand."""
        if args.browser:
            self.open_graph_browser(title=title, title_tooltip=title_tooltip)
            return

        output_file: str | None = getattr(args, "output_file", None)
        fmt: str = args.format
        if fmt == "dot":
            self._cli_write_output(self.get_graph_dot(), output_file)
        elif fmt == "svg":
            self._cli_write_output(self.get_graph_interactive_svg(), output_file)
        elif fmt == "svg-raw":
            self._cli_write_output(self.get_graph_svg(), output_file)
        elif fmt == "html":
            self._cli_write_output(
                self.get_graph_html(title=title, title_tooltip=title_tooltip),
                output_file,
            )
        elif fmt == "png":
            saved = self.get_graph_png(Path(output_file) if output_file else None)
            print(f"PNG saved: {saved}", file=sys.stderr)

    @staticmethod
    def _cli_write_output(content: str, output_file: str | None) -> None:
        """Write *content* to *output_file* or stdout."""
        if output_file:
            Path(output_file).write_text(content, encoding="utf-8")
            print(f"Saved: {output_file}", file=sys.stderr)
        else:
            print(content)

    @staticmethod
    def _append_extra_cli_command_entries(
        subparsers: argparse._SubParsersAction,
        command_entries: list[tuple[str, str, argparse.ArgumentParser]],
        root_prog: str,
    ) -> None:
        """Register subcommands added by ``_add_argparse_commands`` in the help epilog."""
        known = {name for name, _, _ in command_entries}
        help_by_dest = {
            action.dest: action.help
            for action in getattr(subparsers, "_choices_actions", ())
            if getattr(action, "help", None)
        }
        for cmd_name, sub_parser in subparsers.choices.items():
            if cmd_name in known:
                continue
            sub_parser.prog = f"{root_prog} {cmd_name}"
            summary = help_by_dest.get(cmd_name) or cmd_name
            command_entries.append((cmd_name, summary, sub_parser))

    @staticmethod
    def _extract_help_argument_sections(help_text: str) -> list[str]:
        """Return ``positional arguments`` / ``options`` blocks from argparse help text."""
        lines = help_text.splitlines()
        result: list[str] = []
        i = 0
        while i < len(lines):
            if lines[i] in _CLI_HELP_SECTIONS:
                result.append(lines[i])
                i += 1
                while i < len(lines):
                    if (
                        lines[i]
                        and not lines[i].startswith((" ", "\t"))
                        and lines[i].endswith(":")
                        and lines[i] not in _CLI_HELP_SECTIONS
                    ):
                        break
                    if (
                        lines[i] == ""
                        and i + 1 < len(lines)
                        and lines[i + 1]
                        and not lines[i + 1].startswith((" ", "\t"))
                    ):
                        break
                    result.append(lines[i])
                    i += 1
            else:
                i += 1
        return result

    @staticmethod
    def _build_cli_command_reference(
        entries: list[tuple[str, str, argparse.ArgumentParser]],
    ) -> str:
        """Build an epilog listing every subcommand with its full argument grammar."""
        out: list[str] = ["", "commands (full syntax):", ""]
        for cmd_name, summary, sub_parser in entries:
            out.append(f"  {cmd_name}")
            out.append(f"    {summary}")
            for section_line in Describable._extract_help_argument_sections(
                sub_parser.format_help(),
            ):
                out.append(f"    {section_line}")
            out.append("")
        while out and out[-1] == "":
            out.pop()
        return "\n".join(out)

    @staticmethod
    def _add_output_arguments(parser: argparse.ArgumentParser) -> None:
        """Add ``-o`` / ``--output`` to a subcommand parser (not the root parser)."""
        parser.add_argument(
            "-o",
            "--output",
            dest="output_file",
            metavar="FILE",
            help="Write output to FILE instead of stdout.",
        )

    # ------------------------------------------------------------------
    # Private — graph building
    # ------------------------------------------------------------------

    @staticmethod
    def _class_source_location(cls: type) -> tuple[str, int]:
        """Return the absolute source file path and class definition line for *cls*.

        Args:
            cls: Class whose definition location is resolved.

        Returns:
            Tuple of ``(absolute_path, line_number)``.  Both are empty/zero when
            the location cannot be determined (built-ins, REPL-defined classes, …).
        """
        try:
            source_path = Path(inspect.getfile(cls)).resolve()
            line_number = inspect.getsourcelines(cls)[1]
            return str(source_path), line_number
        except (TypeError, OSError):
            return "", 0

    def _build_vertex(self, vertex_id: str) -> Vertex:
        """Recursively build a Vertex for this object and all owned Describables.

        Traverses ``vars(self)`` to find public ``Describable`` attributes and
        lists of ``Describable`` objects, then recurses into each.

        Args:
            vertex_id: Unique identifier for this vertex — a dot-separated
                       path from the root, e.g. ``"ToolAgent.connector.config"``.

        Returns:
            ``Vertex`` with description from ``get_description_item_dict()``
            and children built from public ``Describable`` attributes.
        """
    def _extra_describable_children(self) -> dict[str, Describable]:
        """Return additional Describable children that are not public attributes.

        Override this in subclasses to expose private attributes (e.g. injected
        dependencies stored under ``self._cache``) as nested boxes in the graph.

        The default implementation returns an empty dict — no extra children.

        Returns:
            Dict mapping display name → Describable child instance.
        """
        return {}

    def _build_vertex(self, vertex_id: str) -> Vertex:
        """Recursively build a Vertex for this object and all owned Describables.

        Traverses ``vars(self)`` to find public ``Describable`` attributes and
        lists of ``Describable`` objects, then recurses into each.  Also calls
        ``_extra_describable_children()`` to include private dependencies that
        the subclass explicitly wishes to expose.

        Args:
            vertex_id: Unique identifier for this vertex — a dot-separated
                       path from the root, e.g. ``"ToolAgent.connector.config"``.

        Returns:
            ``Vertex`` with description from ``get_description_item_dict()``
            and children built from public ``Describable`` attributes and
            any extras returned by ``_extra_describable_children()``.
        """
        from agentflow.describable.graph import Vertex  # lazy import — keeps module standalone
        children: list[Vertex] = []
        for key, value in vars(self).items():
            if key.startswith("_"):
                continue
            if isinstance(value, Describable):
                children.append(value._build_vertex(f"{vertex_id}.{key}"))
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, Describable):
                        children.append(item._build_vertex(f"{vertex_id}.{key}[{i}]"))
        for key, value in self._extra_describable_children().items():
            children.append(value._build_vertex(f"{vertex_id}.{key}"))
        source_file, source_line = Describable._class_source_location(type(self))
        return Vertex(
            id=vertex_id,
            label=type(self).__name__,
            description=self.get_description_item_dict(),
            children=children,
            source_file=source_file,
            source_line=source_line,
        )

    # ------------------------------------------------------------------
    # Private static helpers — rendering implementation details
    # ------------------------------------------------------------------


    @staticmethod
    def _wrap_html_page(body: str) -> str:
        """Wrap an HTML fragment in a minimal standalone page shell."""
        return (
            "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
            "<style>"
            "body{font-family:sans-serif;padding:1.5em;max-width:800px}"
            "details{margin-left:1.5em;margin-top:0.2em}"
            "summary{cursor:pointer;font-weight:bold}"
            "ul{margin:0.2em 0 0.2em 1.2em;padding:0;list-style:disc}"
            "li{margin:0.15em 0}"
            "</style></head><body>"
            + body
            + "</body></html>"
        )

    @staticmethod
    def _is_component_dict(value: Any) -> bool:
        """Return True when *value* is a serialised nested Describable component."""
        return isinstance(value, dict) and "_type" in value

    @staticmethod
    def _item_dict_to_markdown(d: dict[str, Any]) -> str:
        """Render an item dict as Markdown with hierarchical plain-dict expansion."""
        type_name = d.get("_type", "Object")
        lines: list[str] = [f"# {type_name}"]

        for key, value in d.items():
            if key == "_type":
                continue
            lines.extend(Describable._markdown_lines_for_value(key, value, indent=0))

        return "\n".join(lines)

    @staticmethod
    def _markdown_lines_for_value(key: str, value: Any, indent: int) -> list[str]:
        """Render one key/value pair as Markdown lines."""
        prefix = "  " * indent
        lines: list[str] = []

        if isinstance(value, dict) and not Describable._is_component_dict(value):
            lines.append(f"{prefix}- **{key}**:")
            lines.extend(Describable._markdown_lines_for_dict(value, indent + 1))
        elif isinstance(value, list):
            lines.append(f"{prefix}- **{key}**:")
            for item in value:
                if isinstance(item, dict) and not Describable._is_component_dict(item):
                    lines.extend(Describable._markdown_lines_for_dict(item, indent + 1))
                else:
                    lines.append(f"{prefix}  - {item}")
        else:
            lines.append(f"{prefix}- **{key}**: {value}")

        return lines

    @staticmethod
    def _markdown_lines_for_dict(d: dict[str, Any], indent: int) -> list[str]:
        """Render a plain dict's entries as indented Markdown lines."""
        lines: list[str] = []
        for key, value in d.items():
            lines.extend(Describable._markdown_lines_for_value(key, value, indent))
        return lines

    @staticmethod
    def _item_dict_to_html(d: dict[str, Any]) -> str:
        """Render an item dict as HTML with hierarchical plain-dict expansion."""
        type_name = Describable._esc_html(str(d.get("_type", "Object")))
        items: list[str] = []

        for key, value in d.items():
            if key == "_type":
                continue
            items.append(Describable._html_for_value(key, value))

        inner_html = f"<ul>{''.join(items)}</ul>" if items else ""
        return f"<details open><summary>{type_name}</summary>{inner_html}</details>"

    @staticmethod
    def _html_for_value(key: str, value: Any) -> str:
        """Render one key/value pair as an HTML list item."""
        safe_key = Describable._esc_html(key)

        if isinstance(value, dict) and not Describable._is_component_dict(value):
            inner = "".join(
                Describable._html_for_value(sub_key, sub_value)
                for sub_key, sub_value in value.items()
            )
            return f"<li><b>{safe_key}</b>:<ul>{inner}</ul></li>"

        if isinstance(value, list):
            inner = "".join(
                f"<li>{Describable._html_for_plain_value(item)}</li>" for item in value
            )
            return f"<li><b>{safe_key}</b>:<ul>{inner}</ul></li>"

        return f"<li><b>{safe_key}</b>: {Describable._esc_html(value)}</li>"

    @staticmethod
    def _html_for_plain_value(value: Any) -> str:
        """Render a list element or scalar for HTML output."""
        if isinstance(value, dict) and not Describable._is_component_dict(value):
            inner = "".join(
                Describable._html_for_value(sub_key, sub_value)
                for sub_key, sub_value in value.items()
            )
            return f"<ul>{inner}</ul>"
        return Describable._esc_html(value)

    @staticmethod
    def _esc_html(value: Any) -> str:
        """Escape a scalar value for safe HTML text content."""
        return html.escape(str(value))

    @staticmethod
    def _dict_to_markdown(d: dict[str, Any], level: int) -> str:
        """Render a full description dict as Markdown with nested headings.

        Args:
            d: Dict produced by ``get_description_dict()``.
            level: Current heading depth (1 = ``#``, 2 = ``##``, …, capped at 6).

        Returns:
            Markdown string.
        """
        type_name = d.get("_type", "Object")
        hashes = "#" * min(level, 6)
        lines: list[str] = [f"{hashes} {type_name}"]

        for key, value in d.items():
            if key == "_type":
                continue
            if Describable._is_component_dict(value):
                lines.append(f"\n**{key}**:\n")
                lines.append(Describable._dict_to_markdown(value, level + 1))
            elif isinstance(value, list) and value and all(
                Describable._is_component_dict(item) for item in value
            ):
                lines.append(f"\n**{key}**:")
                for item in value:
                    lines.append("")
                    lines.append(Describable._dict_to_markdown(item, level + 1))
            else:
                lines.extend(Describable._markdown_lines_for_value(key, value, indent=0))

        return "\n".join(lines)

    @staticmethod
    def _dict_to_html(d: dict[str, Any]) -> str:
        """Render a full description dict as a collapsible HTML ``<details>`` tree.

        Args:
            d: Dict produced by ``get_description_dict()``.

        Returns:
            HTML fragment string (no ``<html>`` wrapper).
        """
        type_name = Describable._esc_html(str(d.get("_type", "Object")))
        items: list[str] = []

        for key, value in d.items():
            if key == "_type":
                continue
            if Describable._is_component_dict(value):
                items.append(
                    f"<li><b>{Describable._esc_html(key)}</b>: "
                    f"{Describable._dict_to_html(value)}</li>"
                )
            elif isinstance(value, list) and value and all(
                Describable._is_component_dict(item) for item in value
            ):
                inner = "".join(
                    f"<li>{Describable._dict_to_html(item)}</li>" for item in value
                )
                items.append(f"<li><b>{Describable._esc_html(key)}</b>:<ul>{inner}</ul></li>")
            else:
                items.append(Describable._html_for_value(key, value))

        inner_html = f"<ul>{''.join(items)}</ul>" if items else ""
        return f"<details open><summary>{type_name}</summary>{inner_html}</details>"

