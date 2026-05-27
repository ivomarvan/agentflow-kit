"""Describable — composable multi-format self-description interface.

Every significant library component (ToolBase, LlmConnector, ToolAgent, …)
inherits from ``Describable`` and implements three abstract methods:

  - ``get_markdown()``            → human-readable documentation string
  - ``get_json()``                → JSON-serializable configuration dict
  - ``get_graphviz_fragment()``   → DOT language building block

Parents compose their description by calling these methods on their children:
  - ToolAgent calls connector.get_graphviz_fragment() and tool.get_graphviz_fragment()
  - Results are wired together inside the agent's own cluster subgraph

Output methods:

  obj.get_dot()             # Graphviz DOT source string (requires system graphviz)
  obj.get_svg()             # SVG string (requires graphviz)
  obj.get_png()             # save to PNG file (requires graphviz)
  obj.get_html()            # interactive vis.js HTML (CDN — no extra Python package)
  obj.open_browser()        # open interactive HTML in the default browser

The HTML output uses vis.js and marked.js loaded from CDN.  Hover over any
node to see a rich Markdown tooltip with the component's full description.
The diagram supports zoom, pan, and drag.

CLI integration via run_argparse():

  Every Describable subclass can expose a full CLI by calling
  run_argparse() from its module's ``if __name__ == "__main__":`` block.
  The base implementation handles all output commands.  Subclasses extend
  via the _add_argparse_commands() / _handle_argparse_command() hooks.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import tempfile
import webbrowser
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Graph building blocks
# ---------------------------------------------------------------------------


@dataclass
class GraphContext:
    """Mutable state threaded through the get_graphviz_fragment() call tree.

    Tracks allocated DOT node IDs so that every node is unique within a
    single ``get_dot()`` call — even when the same component (e.g. a shared
    tool) appears in multiple places.

    Also accumulates Cytoscape.js node and edge data during the same traversal
    so that a single call to ``get_graphviz_fragment()`` populates *both* the
    Graphviz DOT output and the interactive HTML network.  Call ``add_node()``
    and ``add_edge()`` inside ``get_graphviz_fragment()`` implementations
    alongside the corresponding DOT statements.

    Containment (parent-child):  Call ``set_parent(child_id, parent_id)`` after
    the child has been registered via ``add_node()`` to establish a visual
    compound-node relationship in Cytoscape.
    """

    _counters: dict[str, int] = field(default_factory=dict)
    cy_nodes: list[dict[str, Any]] = field(default_factory=list)
    cy_edges: list[dict[str, Any]] = field(default_factory=list)
    # Flat {dot_node_id: markdown} lookup used by get_html() for SVG tooltips.
    # Populated automatically by add_node(); callers may also write directly
    # (e.g. ToolAgent registers its DOT cluster IDs here).
    descriptions: dict[str, str] = field(default_factory=dict)

    def alloc_id(self, base: str) -> str:
        """Allocate a unique DOT node identifier derived from *base*.

        Replaces non-alphanumeric characters with underscores; appends a
        numeric suffix when the same base is allocated more than once.

        Args:
            base: Human-readable base name (e.g. ``"calculator"``).

        Returns:
            A DOT-safe identifier string unique within this context.
        """
        safe = re.sub(r"[^a-zA-Z0-9]", "_", base).strip("_") or "node"
        n = self._counters.get(safe, 0)
        self._counters[safe] = n + 1
        return safe if n == 0 else f"{safe}_{n}"

    def add_node(
        self,
        node_id: str,
        label: str,
        description_md: str = "",
        node_class: str = "default",
        parent_id: str | None = None,
    ) -> None:
        """Register a node for Cytoscape.js interactive rendering.

        Must be called inside ``get_graphviz_fragment()`` alongside the
        corresponding DOT node statement.  Duplicate IDs are silently skipped
        — the first registration wins (handles shared components).

        Args:
            node_id: Must match the DOT node ID allocated with ``alloc_id()``.
            label: Display label shown inside the shape.
            description_md: Markdown shown as a rich tooltip on hover.
            node_class: CSS class applied in Cytoscape (``"agent"``, ``"tool"``,
                        ``"llm"``, ``"registry"``, …).  Controls shape and colour.
            parent_id: When set, this node is visually contained inside the
                       compound node with that ID.
        """
        if any(n["data"]["id"] == node_id for n in self.cy_nodes):
            return  # shared component registered by multiple parents — skip
        data: dict[str, Any] = {"id": node_id, "label": label, "_md": description_md}
        if parent_id is not None:
            data["parent"] = parent_id
        self.cy_nodes.append({"data": data, "classes": node_class})
        # Also populate flat lookup used for SVG tooltips in get_html()
        if description_md:
            self.descriptions[node_id] = description_md

    def set_parent(self, node_id: str, parent_id: str) -> None:
        """Set (or override) the parent compound node of an already-registered node.

        Use this when a parent component needs to adopt nodes registered
        by its children (e.g. ``ToolAgent`` adopts nodes created by the
        connector and tools).

        Args:
            node_id: ID of the node whose parent to set.
            parent_id: ID of the compound (container) node.
        """
        for node in self.cy_nodes:
            if node["data"]["id"] == node_id:
                node["data"]["parent"] = parent_id
                return

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        label: str = "",
        dashes: bool = False,
        edge_type: str = "data",
    ) -> None:
        """Register a directed edge for Cytoscape.js interactive rendering.

        Args:
            from_id: Source node ID.
            to_id: Target node ID.
            label: Optional label shown along the edge.
            dashes: When ``True``, renders as a dashed line.
            edge_type: ``"data"`` (default) for data-flow edges;
                       ``"structure"`` for structural/composition edges.
        """
        classes = edge_type
        if dashes:
            classes += " dashed"
        self.cy_edges.append({
            "data": {"source": from_id, "target": to_id, "label": label},
            "classes": classes,
        })


@dataclass
class GraphFragment:
    """DOT language building block returned by ``get_graphviz_fragment()``.

    ``dot_statements`` contains raw DOT lines (node definitions, edge
    definitions, nested ``subgraph cluster_*`` blocks).  The parent
    collects these from its children and assembles them into its own
    cluster.

    Args:
        dot_statements: List of raw DOT language statements.
        root_id: Primary DOT node ID of this component — the ID a parent
                 should connect *to* when drawing an edge to this fragment.
    """

    dot_statements: list[str]
    root_id: str


# ---------------------------------------------------------------------------
# DOT helpers
# ---------------------------------------------------------------------------


def _esc(text: str) -> str:
    """Escape a string for use inside a double-quoted DOT attribute value."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _esc_html(text: str) -> str:
    """Escape text for safe insertion as HTML text content."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _dot_node(node_id: str, label: str, tooltip: str = "", **attrs: str) -> str:
    """Build a DOT node statement with common attributes.

    Args:
        node_id: Unique DOT identifier.
        label: Display label (\\n allowed for newlines).
        tooltip: Tooltip text (visible on hover in SVG/browser).
        **attrs: Additional DOT attributes (shape, fillcolor, …).

    Returns:
        Single-line DOT node statement string.
    """
    parts = [f'label="{_esc(label)}"']
    if tooltip:
        parts.append(f'tooltip="{_esc(tooltip)}"')
    for k, v in attrs.items():
        parts.append(f'{k}="{_esc(v)}"')
    return f'{node_id} [{", ".join(parts)}]'


# ---------------------------------------------------------------------------
# Describable ABC
# ---------------------------------------------------------------------------


class Describable(ABC):
    """ABC for objects that can describe themselves in multiple formats.

    Subclasses must implement the three abstract methods.  All rendering
    convenience methods (``get_dot``, ``get_svg``, ``get_png``, ``get_html``,
    ``open_browser``) are provided as concrete methods that compose on top of
    the abstract ``get_graphviz_fragment()``.
    """

    # ------------------------------------------------------------------
    # Abstract — subclasses MUST implement
    # ------------------------------------------------------------------

    @abstractmethod
    def get_markdown(self) -> str:
        """Return a Markdown-formatted description of this component.

        Returns:
            Multi-line Markdown string.
        """
        ...

    @abstractmethod
    def get_json(self) -> dict[str, Any]:
        """Return a JSON-serializable configuration dict.

        Returns:
            Dict that can be passed to ``json.dumps()``.
        """
        ...

    @abstractmethod
    def get_graphviz_fragment(self, ctx: GraphContext) -> GraphFragment:
        """Return a DOT language fragment for this component.

        Implementations should:
          1. Allocate node IDs via ``ctx.alloc_id()``.
          2. Recursively call ``get_graphviz_fragment(ctx)`` on sub-components.
          3. Collect all ``dot_statements`` and optionally wrap them in a
             ``subgraph cluster_*`` block.
          4. Return a ``GraphFragment`` with all statements and the ``root_id``
             that a parent should connect edges to.

        Args:
            ctx: Mutable context for unique ID allocation — must be threaded
                 through to all child ``get_graphviz_fragment()`` calls.

        Returns:
            ``GraphFragment`` with DOT statements and root node ID.
        """
        ...

    # ------------------------------------------------------------------
    # Concrete output methods — provided for free by inheriting Describable
    # ------------------------------------------------------------------

    def get_dot(self) -> str:
        """Return a complete Graphviz DOT source string for this component.

        Returns:
            Multi-line DOT string, ready to pass to ``graphviz.Source()``.
        """
        ctx = GraphContext()
        frag = self.get_graphviz_fragment(ctx)
        body = "\n  ".join(frag.dot_statements)
        return (
            "digraph {\n"
            '  rankdir=LR\n'
            '  node [fontname="Helvetica" fontsize=11]\n'
            '  edge [fontname="Helvetica" fontsize=9 color=gray40]\n'
            f"  {body}\n"
            "}"
        )

    def get_svg(self) -> str:
        """Render to SVG string using the graphviz system tool.

        Requires:
          - ``graphviz`` Python package (``pip install graphviz``)
          - Graphviz system tools (``apt install graphviz`` or ``brew install graphviz``)

        Returns:
            SVG XML string (includes ``<svg>`` root element).

        Raises:
            ImportError: If the ``graphviz`` Python package is not installed.
            graphviz.backend.execute.ExecutableNotFound: If the system dot
                executable is not on PATH.
        """
        gv = _require_graphviz()
        src = gv.Source(self.get_dot())
        return src.pipe(format="svg").decode("utf-8")

    def get_png(self, path: Path | None = None) -> Path:
        """Render to a PNG file.

        Args:
            path: Output file path.  When ``None``, a temporary file is created.

        Returns:
            Path to the rendered PNG file.

        Raises:
            ImportError: If the ``graphviz`` Python package is not installed.
        """
        gv = _require_graphviz()
        if path is None:
            tmp_dir = Path(tempfile.mkdtemp())
            name = getattr(self, "name", type(self).__name__)
            path = tmp_dir / f"{re.sub(r'[^a-zA-Z0-9_-]', '_', name)}.png"
        src = gv.Source(self.get_dot())
        # render() adds the format extension; pass the stem path
        out = src.render(
            filename=str(path.with_suffix("")),
            format="png",
            cleanup=True,
        )
        result = Path(out)
        logger.info("PNG saved: %s", result)
        return result

    def get_html(
        self,
        *,
        page_title: str = "",
        page_tooltip_html: str = "",
    ) -> str:
        """Return a standalone interactive HTML page using inline Graphviz SVG.

        Layout is generated by Graphviz (deterministic, no startup flicker).
        Tooltips are rendered by JavaScript: the ``<title>`` of each SVG group
        is looked up in a JSON descriptions dict and displayed as parsed Markdown
        (via marked.js from CDN).  No extra Python packages beyond ``graphviz``.

        Args:
            page_title: Text shown in the browser tab and ``<h1>`` header.
                        Defaults to ``self.name`` (or the class name).
            page_tooltip_html: Plain text for the ``<h1>`` native browser tooltip.
                               Defaults to *page_title*.

        Returns:
            Complete self-contained HTML string.
        """
        gv = _require_graphviz()
        # One traversal: builds DOT statements AND populates ctx.descriptions
        ctx = GraphContext()
        frag = self.get_graphviz_fragment(ctx)
        body = "\n  ".join(frag.dot_statements)
        dot_src = (
            "digraph {\n"
            "  rankdir=LR\n"
            '  node [fontname="Helvetica" fontsize=11]\n'
            '  edge [fontname="Helvetica" fontsize=9 color=gray40]\n'
            f"  {body}\n"
            "}"
        )
        svg = gv.Source(dot_src, format="svg").pipe().decode("utf-8")
        if not page_title:
            page_title = getattr(self, "name", type(self).__name__)
        descriptions_json = json.dumps(ctx.descriptions, ensure_ascii=False, indent=2)
        return (
            _SVG_HTML_TEMPLATE
            .replace("%%TITLE%%", _esc_html(page_title))
            .replace("%%HEADER_TOOLTIP%%", page_tooltip_html or page_title)
            .replace("%%SVG%%", svg)
            .replace("%%DESCRIPTIONS%%", descriptions_json)
        )

    def open_browser(
        self,
        *,
        page_title: str = "",
        page_tooltip_html: str = "",
    ) -> None:
        """Render the interactive diagram and open it in the default web browser.

        Saves a temporary HTML file and passes its ``file://`` URL to the
        system browser.

        Args:
            page_title: Forwarded to ``get_html()``.
            page_tooltip_html: Forwarded to ``get_html()``.
        """
        html = self.get_html(
            page_title=page_title, page_tooltip_html=page_tooltip_html
        )
        name = getattr(self, "name", type(self).__name__)
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        tmp = Path(tempfile.mktemp(suffix=f"_{safe_name}.html"))
        tmp.write_text(html, encoding="utf-8")
        url = tmp.as_uri()
        logger.info("Opening browser: %s", url)
        webbrowser.open(url)

    # ------------------------------------------------------------------
    # Optional run() — override in «runnable» subclasses (e.g. ToolAgent)
    # ------------------------------------------------------------------

    def run(self, question: str) -> str:
        """Execute this object with a question and return the answer.

        The base implementation raises ``NotImplementedError``.  Override in
        subclasses that support conversational execution (e.g. ``ToolAgent``).

        Args:
            question: Free-text question or instruction.

        Returns:
            Answer string.

        Raises:
            NotImplementedError: If the subclass does not support ``run()``.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support run(). "
            "Override this method in a runnable subclass."
        )

    # ------------------------------------------------------------------
    # Argparse hooks — override in subclasses to add extra CLI commands
    # ------------------------------------------------------------------

    def _add_argparse_commands(self, subparsers: Any) -> None:
        """Register extra argparse subcommands for this class.

        Called by ``run_argparse()`` before ``parse_args()``.  Override to
        add class-specific subcommands (e.g. ``ping`` on ``LlmConnector``).

        Args:
            subparsers: The ``_SubParsersAction`` returned by
                        ``parser.add_subparsers()``.
        """

    def _handle_argparse_command(self, args: Any) -> None:
        """Handle a subcommand registered by ``_add_argparse_commands()``.

        Called by ``run_argparse()`` when the parsed command is not one of
        the built-in Describable commands.  Override together with
        ``_add_argparse_commands()``.

        Args:
            args: The ``argparse.Namespace`` from ``parse_args()``.
        """
        print(f"Unknown command: {args.command!r}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # run_argparse() — unified CLI entry-point for any Describable object
    # ------------------------------------------------------------------

    def run_argparse(
        self,
        doc: str | None = None,
        *,
        name: str = "",
        default_question: str | None = None,
        log_level: int = logging.INFO,
    ) -> None:
        """Parse ``sys.argv`` and execute the requested output command.

        Designed to be called at the bottom of a module's
        ``if __name__ == "__main__":`` block (or unconditionally with
        ``name=__name__``).  When ``name != "__main__"`` the method returns
        immediately — safe to call at import time.

        Built-in commands (always available):
          describe              Print Markdown description (no LLM call).
          json                  Print JSON configuration (no LLM call).
          graphviz              Print Graphviz DOT source (no LLM call).
          svg [-o FILE]         Render to SVG (stdout or save to FILE).
          png [-o FILE]         Render to PNG file (default: temp file).
          html [-o FILE]        Save interactive HTML diagram (default: temp file).
          browser               Open interactive HTML diagram in browser.

        Optional command (enabled when ``default_question`` is provided):
          run [Q]     Call ``self.run(Q)`` and print the answer.
                      Defaults to ``default_question`` when Q is omitted.

        Default command: ``run`` (when ``default_question`` is provided),
        otherwise ``describe``.

        Subclasses extend the CLI via the two hooks:
          _add_argparse_commands(subparsers)    — register extra commands
          _handle_argparse_command(args)         — dispatch extra commands

        Args:
            doc: Module ``__doc__`` string used as the parser description.
            name: Pass ``__name__`` from the calling module.  The method
                  exits immediately when ``name != "__main__"``.
            default_question: If provided, enables the ``run`` command and
                              sets its default question string.
            log_level: Root logging level (e.g. ``logging.DEBUG``).
                       Can be overridden to ``DEBUG`` at runtime with ``-v``.
        """
        if name != "__main__":
            return

        logging.basicConfig(
            level=log_level,
            format="%(levelname)s %(name)s: %(message)s",
            stream=sys.stderr,
        )

        parser = argparse.ArgumentParser(
            description=doc,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument(
            "--verbose", "-v",
            action="store_true",
            help="Enable DEBUG logging (overrides log_level).",
        )
        subparsers = parser.add_subparsers(dest="command")

        # Optional "run" command — only when caller supplies default_question
        if default_question is not None:
            p_run = subparsers.add_parser(
                "run", help="Run the agent with a question."
            )
            p_run.add_argument(
                "question",
                nargs="?",
                default=default_question,
                help=f"Question to ask (default: {default_question!r}).",
            )

        # Built-in Describable output commands
        subparsers.add_parser(
            "describe", help="Print Markdown description (no LLM call)."
        )
        subparsers.add_parser(
            "json", help="Print JSON configuration (no LLM call)."
        )
        subparsers.add_parser(
            "graphviz", help="Print Graphviz DOT source (no LLM call)."
        )
        p_svg = subparsers.add_parser("svg", help="Render diagram to SVG.")
        p_svg.add_argument(
            "-o", "--output-file", metavar="FILE",
            help="Save SVG to FILE.  Omit to print SVG to stdout.",
        )
        p_png = subparsers.add_parser("png", help="Render diagram to PNG file.")
        p_png.add_argument(
            "-o", "--output-file", metavar="FILE",
            help="Output file path (default: auto-generated temp file).",
        )
        subparsers.add_parser(
            "browser", help="Open interactive HTML diagram in the default browser."
        )
        p_html = subparsers.add_parser(
            "html", help="Save interactive HTML diagram to FILE."
        )
        p_html.add_argument(
            "-o", "--output-file", metavar="FILE",
            help="Output file path (default: auto-generated temp file).",
        )

        # Hook: subclasses add their own commands here
        self._add_argparse_commands(subparsers)

        args = parser.parse_args()

        if args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)

        # Default command when none is given
        if args.command is None:
            args.command = "run" if default_question is not None else "describe"

        # Page metadata for HTML / browser output — script filename + timestamp
        from datetime import datetime
        _script = Path(sys.argv[0])
        _ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        _page_title = f"{_script.name} ({_ts})"
        _page_tooltip = (
            f"Generated: {_ts} | Path: {_script.resolve()}"
        )

        # Dispatch built-in commands
        if args.command == "run":
            question = getattr(args, "question", None) or default_question or ""
            print(self.run(question))

        elif args.command == "describe":
            print(self.get_markdown())

        elif args.command == "json":
            print(json.dumps(self.get_json(), indent=2, ensure_ascii=False))

        elif args.command == "graphviz":
            print(self.get_dot())

        elif args.command == "svg":
            svg = self.get_svg()
            out_file = getattr(args, "output_file", None)
            if out_file:
                Path(out_file).write_text(svg, encoding="utf-8")
                print(f"SVG saved: {out_file}")
            else:
                print(svg)

        elif args.command == "png":
            out_file = getattr(args, "output_file", None)
            saved = self.get_png(Path(out_file) if out_file else None)
            print(f"PNG saved: {saved}")

        elif args.command == "browser":
            self.open_browser(
                page_title=_page_title, page_tooltip_html=_page_tooltip
            )

        elif args.command == "html":
            html_content = self.get_html(
                page_title=_page_title, page_tooltip_html=_page_tooltip
            )
            out_file = getattr(args, "output_file", None)
            if out_file:
                Path(out_file).write_text(html_content, encoding="utf-8")
                print(f"HTML saved: {out_file}")
            else:
                name = getattr(self, "name", type(self).__name__)
                safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
                tmp = Path(tempfile.mktemp(suffix=f"_{safe_name}.html"))
                tmp.write_text(html_content, encoding="utf-8")
                print(f"HTML saved: {tmp}")

        else:
            # Delegate to subclass hook
            self._handle_argparse_command(args)


# ---------------------------------------------------------------------------
# SVG + JavaScript interactive HTML template
# ---------------------------------------------------------------------------

# Layout: Graphviz (perfect cluster/containment rendering, no startup flicker).
# Tooltips: JavaScript reads SVG <title> elements, matches against the
#           descriptions dict, and renders Markdown via marked.js from CDN.
#
# Placeholders:
#   %%TITLE%%          → HTML-escaped page title
#   %%HEADER_TOOLTIP%% → plain text for <h1> native browser tooltip
#   %%SVG%%            → inline SVG string from graphviz
#   %%DESCRIPTIONS%%   → JSON object {dot_node_id: markdown_string}
_SVG_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>%%TITLE%%</title>
  <script src="https://cdn.jsdelivr.net/npm/marked@9/marked.min.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; overflow: hidden; font-family: Arial, sans-serif; }
    body { display: flex; flex-direction: column; background: #f0f2f5; }
    #header {
      padding: 10px 20px; background: white; border-bottom: 1px solid #ddd; flex-shrink: 0;
    }
    #header h1 {
      font-size: 1.05rem; color: #2c3e50; font-weight: 600; cursor: default; display: inline;
    }
    #header h1:hover { color: #1a6ea8; }
    #svg-wrap {
      flex: 1; min-height: 0; overflow: auto;
      display: flex; align-items: center; justify-content: center; padding: 20px;
    }
    #svg-wrap svg { max-width: 100%; height: auto; }
    /* Tooltip */
    #tt {
      display: none; position: fixed; z-index: 1000;
      max-width: 460px; max-height: 72vh; overflow-y: auto;
      background: white; border-radius: 8px; padding: 16px;
      box-shadow: 0 6px 28px rgba(0,0,0,.22);
      font-size: 13px; line-height: 1.6; pointer-events: none;
    }
    #tt h1, #tt h2, #tt h3 { font-size: 1rem; font-weight: bold; margin: 0.7em 0 0.3em; color: #2c3e50; }
    #tt h1 { font-size: 1.1rem; border-bottom: 1px solid #eee; padding-bottom: 4px; }
    #tt code { background: #f0f4f8; padding: 1px 5px; border-radius: 3px; font-size: 0.88em; }
    #tt pre code { background: none; padding: 0; }
    #tt pre { background: #f0f4f8; padding: 8px; border-radius: 4px; overflow-x: auto; margin: 8px 0; font-size: 0.88em; }
    #tt table { border-collapse: collapse; width: 100%; margin: 8px 0; }
    #tt td, #tt th { padding: 4px 8px; border: 1px solid #ddd; font-size: 0.9em; }
    #tt th { background: #f0f4f8; font-weight: 600; }
    #tt ul, #tt ol { padding-left: 1.3em; margin: 4px 0; }
    #tt p { margin: 5px 0; }
    #tt p:first-child { margin-top: 0; }
  </style>
</head>
<body>
  <div id="header"><h1 title="%%HEADER_TOOLTIP%%">%%TITLE%%</h1></div>
  <div id="svg-wrap">%%SVG%%</div>
  <div id="tt"></div>
  <script>
    const descs = %%DESCRIPTIONS%%;
    const tt = document.getElementById("tt");

    // Attach description to each SVG group whose <title> matches our dict,
    // then remove <title> to suppress the native browser gray-box SVG tooltip.
    document.querySelectorAll("#svg-wrap svg g").forEach(function(g) {
      const tel = g.querySelector(":scope > title");
      if (tel) {
        const md = descs[tel.textContent.trim()];
        if (md) { g._md = md; g.style.cursor = "pointer"; }
        tel.remove(); // native tooltip gone; our custom tooltip takes over
      }
    });

    // On hover: walk up DOM to find innermost group with a description
    // (child node tooltip wins over parent cluster tooltip)
    document.getElementById("svg-wrap").addEventListener("mouseover", function(e) {
      let el = e.target;
      while (el && el.id !== "svg-wrap") {
        if (el._md) {
          tt.innerHTML = (typeof marked !== "undefined")
            ? marked.parse(el._md)
            : "<pre>" + el._md.replace(/</g, "&lt;") + "</pre>";
          tt.style.display = "block";
          return;
        }
        el = el.parentElement;
      }
      tt.style.display = "none";
    });

    document.getElementById("svg-wrap").addEventListener("mousemove", function(e) {
      if (tt.style.display === "none") return;
      const x = e.clientX + 18, y = e.clientY + 8;
      tt.style.left = (x + 480 > window.innerWidth ? e.clientX - 478 : x) + "px";
      tt.style.top = Math.max(8, y) + "px";
    });

    document.getElementById("svg-wrap").addEventListener("mouseleave", function() {
      tt.style.display = "none";
    });
  </script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _require_graphviz() -> Any:
    """Import and return the graphviz module, or raise a helpful ImportError."""
    try:
        import graphviz  # type: ignore[import]
        return graphviz
    except ImportError:
        raise ImportError(
            "The 'graphviz' Python package is required for visual output.\n"
            "Install it with:\n"
            "  uv add graphviz          (or: pip install graphviz)\n"
            "Also ensure the system 'dot' executable is installed:\n"
            "  Ubuntu/Debian: sudo apt install graphviz\n"
            "  macOS:         brew install graphviz"
        ) from None
