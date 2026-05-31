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
    obj.open_graph_browser(title="")     # None — renders HTML and opens browser
    obj.run()                            # str | None — no-op default; override in runnable objects
    obj.run_argparse(                    # unified CLI entry-point
        default_command="markdown"       #   "dict" | "markdown" | "html" |
                                         #   "graph-dot" | "graph-svg" | "graph-svg-raw" |
                                         #   "graph-html" | "graph-png" | "graph-browser" | "run"
    )

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

    def run_argparse(
        self,
        doc: str | None = None,
        *,
        name: str = "",
        default_question: str | None = None,
        default_command: str = "markdown",
        title: str = "",
        title_tooltip: str = "",
    ) -> None:
        """Parse ``sys.argv`` and execute the requested output command.

        Built-in commands::

            dict         [-o FILE]  Print / save JSON from get_description_dict().
            markdown     [-o FILE]  Print / save Markdown from get_description_markdown().
            html         [-o FILE]  Print / save HTML from get_description_html().
            graph-dot    [-o FILE]  Graphviz DOT source.
            graph-svg    [-o FILE]  Interactive SVG with hover tooltips.
            graph-svg-raw[-o FILE]  Raw SVG for document embedding.
            graph-html   [-o FILE]  Standalone interactive HTML page.
            graph-png    [-o FILE]  PNG file via Graphviz.
            graph-browser           Open graph diagram in the browser.
            run          [QUESTION] Call self.run([question]) and print the result.

        When no command is given, ``default_command`` is used.  Pass
        ``default_command="run"`` from top-level runnable objects (e.g. ToolAgent).

        When ``name`` is provided and differs from ``"__main__"``, the method
        returns immediately — the script was imported, not executed directly.
        Pass ``name=__name__`` to enforce this guard.

        When ``default_question`` is provided, the ``run`` subcommand gains an
        optional positional ``question`` argument that defaults to it.

        Args:
            doc: Module docstring (``__doc__``) used as the CLI description.
            name: Module name guard.  Pass ``__name__`` to run only when the
                  script is the entry-point; omit or pass ``""`` to always run.
            default_question: Default question for the ``run`` command.  When
                              set, the ``run`` subcommand forwards it to
                              ``self.run(question)``.
            default_command: Command used when none is provided on the CLI.
                             One of ``"dict"``, ``"markdown"``, ``"html"``, ``"run"``.
            title: Title shown in the graph HTML header.  Defaults to
                   ``self.name`` when empty.
            title_tooltip: Markdown shown as a tooltip when hovering the title
                           in the HTML/browser graph output.
        """
        if name and name != "__main__":
            return

        parser = argparse.ArgumentParser(
            description=doc,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            parents=[self._output_file_parser()],
        )
        subparsers = parser.add_subparsers(dest="command")

        for cmd_name in ("dict", "markdown", "html"):
            subparsers.add_parser(
                cmd_name,
                parents=[self._output_file_parser()],
                help=f"Output {cmd_name} description.",
            )

        subparsers.add_parser(
            "graph-dot",
            parents=[self._output_file_parser()],
            help="Render composition graph to Graphviz DOT source.",
        )
        subparsers.add_parser(
            "graph-svg",
            parents=[self._output_file_parser()],
            help="Render composition graph to interactive SVG (open in browser).",
        )
        subparsers.add_parser(
            "graph-svg-raw",
            parents=[self._output_file_parser()],
            help="Render composition graph to raw SVG (for embedding in documents).",
        )
        subparsers.add_parser(
            "graph-html",
            parents=[self._output_file_parser()],
            help="Render composition graph to standalone interactive HTML page.",
        )

        subparsers.add_parser(
            "graph-png",
            parents=[self._output_file_parser()],
            help="Render composition graph to PNG file.",
        )
        subparsers.add_parser(
            "graph-browser",
            help="Open interactive graph diagram in the default browser.",
        )
        subparsers.add_parser(
            "browser",
            help="Alias for graph-browser: open interactive graph diagram in the default browser.",
        )
        if default_question is not None:
            p_run = subparsers.add_parser("run", help="Run this object with a question.")
            p_run.add_argument(
                "question",
                nargs="?",
                default=default_question,
                help=f"Question to answer (default: {default_question!r}).",
            )
        else:
            subparsers.add_parser("run", help="Run this object (if supported).")

        args = parser.parse_args()
        if args.command is None:
            args.command = default_command

        out_file: str | None = getattr(args, "out_file", None)

        def _write(content: str) -> None:
            if out_file:
                Path(out_file).write_text(content, encoding="utf-8")
                print(f"Saved: {out_file}", file=sys.stderr)
            else:
                print(content)

        if args.command == "dict":
            _write(json.dumps(self.get_description_dict(), indent=2, ensure_ascii=False))
        elif args.command == "markdown":
            _write(self.get_description_markdown())
        elif args.command == "html":
            _write(self.get_description_html())
        elif args.command == "graph-dot":
            _write(self.get_graph_dot())
        elif args.command == "graph-svg":
            _write(self.get_graph_interactive_svg())
        elif args.command == "graph-svg-raw":
            _write(self.get_graph_svg())
        elif args.command == "graph-html":
            _write(self.get_graph_html(title=title, title_tooltip=title_tooltip))
        elif args.command == "graph-png":
            saved = self.get_graph_png(Path(out_file) if out_file else None)
            print(f"PNG saved: {saved}")
        elif args.command in ("graph-browser", "browser"):
            self.open_graph_browser(title=title, title_tooltip=title_tooltip)
        elif args.command == "run":
            if default_question is not None:
                question = getattr(args, "question", default_question)
                result = self.run(question)  # type: ignore[call-arg]
            else:
                result = self.run()
            if result is not None:
                print(f"\n{result}")

    # ------------------------------------------------------------------
    # Private — graph building
    # ------------------------------------------------------------------

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
        return Vertex(
            id=vertex_id,
            label=type(self).__name__,
            description=self.get_description_item_dict(),
            children=children,
        )

    # ------------------------------------------------------------------
    # Private static helpers — rendering implementation details
    # ------------------------------------------------------------------

    @staticmethod
    def _output_file_parser() -> argparse.ArgumentParser:
        """Return a reusable parser fragment for the optional ``-o`` output flag.

        Uses ``default=argparse.SUPPRESS`` so that the subparser's unset ``-o``
        does **not** overwrite the value already captured by the main parser.
        Without SUPPRESS, ``-o file command`` would lose ``file`` because the
        subparser resets ``out_file`` to its own ``None`` default.
        """
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument(
            "-o",
            "--out-file",
            dest="out_file",
            default=argparse.SUPPRESS,
            metavar="OUTPUT_FILE",
            help="Write output to OUTPUT_FILE instead of stdout.",
        )
        return parser

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

