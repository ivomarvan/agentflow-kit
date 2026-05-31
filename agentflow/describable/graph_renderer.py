"""GraphRenderer — converts a Graph to Graphviz DOT, SVG, PNG, HTML, and browser output.

Rendering pipeline::

    Graph ──► _build_dot() ──► DOT source + descriptions dict
                                      │                 │
                              Graphviz CLI       JS tooltip JSON
                                      │
                              SVG / PNG / HTML page

The HTML output uses:
  - Graphviz ``dot`` for deterministic, cluster-aware layout (no startup flicker).
  - ``marked.js`` from CDN for rich Markdown rendering inside the tooltip panel.
  - Pure SVG embedding — no additional JavaScript graph library needed.

Usage::

    from agentflow.describable.graph_renderer import GraphRenderer
    from agentflow.describable import Describable  # build your own Describable subclass

    graph = build_demo_agent().get_graph()
    print(GraphRenderer.to_dot(graph))
    GraphRenderer.open_browser(graph)
"""

from __future__ import annotations

import html as _html_stdlib
import json
import os
import re
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentflow.describable.graph import Edge, Graph, Vertex


# ---------------------------------------------------------------------------
# Colour palette for cluster depth levels (fillcolor, border_color)
# ---------------------------------------------------------------------------

_CLUSTER_PALETTE: list[tuple[str, str]] = [
    ("lemonchiffon", "goldenrod"),
    ("lightcyan",    "steelblue"),
    ("lavender",     "mediumpurple"),
    ("lightyellow",  "olivedrab"),
    ("mistyrose",    "firebrick"),
]

_LEAF_FILL   = "honeydew"
_LEAF_BORDER = "darkgreen"


class GraphRenderer:
    """Renders a ``Graph`` to various visual and text formats.

    All methods are static — no instance is needed.

    Public API::

        GraphRenderer.to_dot(graph)                   # str  — Graphviz DOT source (with rich tooltips)
        GraphRenderer.to_svg(graph)                   # str  — raw SVG, good for embedding in docs
        GraphRenderer.to_interactive_svg(graph)       # str  — SVG with embedded JS hover tooltips
        GraphRenderer.to_png(graph, path=None)        # Path — saved PNG file
        GraphRenderer.to_html(graph, title="")        # str  — standalone HTML page with tooltips
        GraphRenderer.open_browser(graph, title="")   # None — opens browser
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def to_dot(graph: Graph) -> str:
        """Return the Graphviz DOT source string for *graph*.

        Args:
            graph: The composition graph to render.

        Returns:
            Multi-line DOT source string.
        """
        dot, _ = GraphRenderer._build_dot(graph)
        return dot

    @staticmethod
    def to_svg(graph: Graph) -> str:
        """Render *graph* to an SVG string via the Graphviz ``dot`` tool.

        Args:
            graph: The composition graph to render.

        Returns:
            SVG XML string (includes the ``<svg>`` root element).

        Raises:
            ImportError: If the ``graphviz`` Python package is not installed.
        """
        gv = GraphRenderer._require_graphviz()
        dot, _ = GraphRenderer._build_dot(graph)
        return gv.Source(dot).pipe(format="svg").decode("utf-8")

    @staticmethod
    def to_png(graph: Graph, path: Path | None = None) -> Path:
        """Render *graph* to a PNG file.

        Args:
            graph: The composition graph to render.
            path: Output file path.  When ``None``, a temporary file is used.

        Returns:
            Path to the rendered PNG file.

        Raises:
            ImportError: If the ``graphviz`` Python package is not installed.
        """
        gv = GraphRenderer._require_graphviz()
        dot, _ = GraphRenderer._build_dot(graph)
        if path is None:
            tmp_dir = Path(tempfile.mkdtemp())
            path = tmp_dir / f"{graph.root.label}.png"
        result = Path(
            gv.Source(dot).render(
                filename=str(path.with_suffix("")),
                format="png",
                cleanup=True,
            )
        )
        return result

    @staticmethod
    def to_html(graph: Graph, title: str = "", title_tooltip: str = "") -> str:
        """Return a standalone interactive HTML page for *graph*.

        Graphviz generates the SVG layout.  JavaScript overlays rich Markdown
        tooltips on hover using ``marked.js`` from CDN.  Hovering over any
        vertex (leaf or cluster) shows its full attribute description.
        When ``title_tooltip`` is provided, hovering over the page title shows
        a rich Markdown tooltip with that content.

        Args:
            graph: The composition graph to render.
            title: Page title shown in the browser tab and the header bar.
                   Defaults to the root vertex label.
            title_tooltip: Markdown shown as a tooltip when hovering the title.
                           When empty, no header tooltip is attached.

        Returns:
            Complete self-contained HTML string (no external files needed).

        Raises:
            ImportError: If the ``graphviz`` Python package is not installed.
        """
        gv = GraphRenderer._require_graphviz()
        dot, descs = GraphRenderer._build_dot(graph)
        svg = gv.Source(dot, format="svg").pipe().decode("utf-8")
        page_title = title or graph.root.label
        title_tt_json = json.dumps(title_tooltip if title_tooltip else None, ensure_ascii=False)
        return (
            _HTML_TEMPLATE
            .replace("%%TITLE%%",          _html_stdlib.escape(page_title))
            .replace("%%SVG%%",            svg)
            .replace("%%DESCRIPTIONS%%",   json.dumps(descs, ensure_ascii=False))
            .replace("%%TITLE_TOOLTIP%%",  title_tt_json)
        )

    @staticmethod
    def to_interactive_svg(graph: Graph) -> str:
        """Render *graph* to a self-contained interactive SVG with hover tooltips.

        Graphviz generates the layout; the SVG is then post-processed to inject
        a ``<foreignObject>`` tooltip panel, inline CSS, and a ``<script>`` block
        that attaches Markdown descriptions to SVG groups.  The result can be
        saved as a ``.svg`` file and opened directly in any modern browser.

        A minimal inline Markdown renderer is embedded as fallback.
        ``marked.js`` is loaded from CDN on-demand for richer rendering (requires
        internet access when the file is opened).

        Args:
            graph: The composition graph to render.

        Returns:
            Interactive SVG string.

        Raises:
            ImportError: If the ``graphviz`` Python package is not installed.
        """
        gv  = GraphRenderer._require_graphviz()
        dot, descs = GraphRenderer._build_dot(graph)
        raw_svg = gv.Source(dot, format="svg").pipe().decode("utf-8")
        return GraphRenderer._inject_svg_interactivity(raw_svg, descs)

    @staticmethod
    def open_browser(graph: Graph, title: str = "", title_tooltip: str = "") -> None:
        """Render *graph* as HTML and open it in the default web browser.

        Saves an HTML file to a user-accessible directory and opens it via
        ``file://`` URL.  The directory is chosen for maximum compatibility
        with sandboxed browsers (e.g. Firefox installed as a snap package):

        1. ``$XDG_RUNTIME_DIR/agentflow/graphs/`` — ``/run/user/<UID>/…``,
           accessible to the snap sandbox without AppArmor restrictions.
        2. ``$HOME/.local/share/agentflow/graphs/`` — XDG_DATA_HOME fallback.

        The file name is derived from the graph root label and is overwritten
        on each invocation so no stale files accumulate.

        Args:
            graph: The composition graph to render.
            title: Forwarded to ``to_html()``.
            title_tooltip: Forwarded to ``to_html()``.
        """
        xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", "")
        if xdg_runtime:
            cache_dir = Path(xdg_runtime) / "agentflow" / "graphs"
        else:
            cache_dir = Path.home() / ".local" / "share" / "agentflow" / "graphs"
        cache_dir.mkdir(parents=True, exist_ok=True)

        content   = GraphRenderer.to_html(graph, title=title, title_tooltip=title_tooltip)
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", graph.root.label)
        out = cache_dir / f"{safe_name}.html"
        out.write_text(content, encoding="utf-8")
        os.chmod(out, 0o644)
        webbrowser.open(out.as_uri())

    # ------------------------------------------------------------------
    # Private — DOT building
    # ------------------------------------------------------------------

    @staticmethod
    def _build_dot(graph: Graph) -> tuple[str, dict[str, str]]:
        """Build the DOT source and the descriptions dict for tooltip rendering.

        Returns:
            Tuple of ``(dot_source, {dot_id: markdown_string})``.
            The ``dot_id`` keys match the ``<title>`` text of the corresponding
            SVG group elements so that the JavaScript tooltip logic can look
            them up.
        """
        lines: list[str] = [
            "digraph {",
            "  rankdir=LR",
            "  compound=true",
            '  node [fontname="Helvetica" fontsize=11]',
            '  edge [fontname="Helvetica" fontsize=9 color=gray40]',
        ]
        descs: dict[str, str] = {}
        GraphRenderer._render_vertex(graph.root, lines, descs, depth=0)
        for edge in graph.edges:
            lines.append(f"  {GraphRenderer._edge_to_dot(edge)}")
        lines.append("}")
        return "\n".join(lines), descs

    @staticmethod
    def _render_vertex(
        v: Vertex,
        lines: list[str],
        descs: dict[str, str],
        depth: int,
    ) -> str:
        """Recursively render one vertex to DOT lines.

        Leaf vertices (no children) become regular DOT nodes.
        Non-leaf vertices become ``subgraph cluster_*`` blocks with an
        invisible anchor node inside so that explicit edges can connect to
        them (Graphviz edges cannot target a cluster directly).

        Args:
            v: Vertex to render.
            lines: List to append DOT statements to (mutated in place).
            descs: Dict populated with ``{dot_id: markdown}`` for tooltips.
            depth: Nesting depth — controls indentation and colour palette.

        Returns:
            DOT id of this vertex: leaf node id or the cluster's anchor id.
        """
        pad  = "  " * (depth + 1)   # outer indent (inside digraph / parent cluster)
        ipad = "  " * (depth + 2)   # inner indent (inside this cluster)
        safe    = GraphRenderer._safe_id(v.id)
        md      = GraphRenderer._vertex_to_md(v)
        tooltip = GraphRenderer._vertex_to_dot_tooltip(v)

        if not v.children:
            node_attrs = (
                f'label="{v.label}" '
                f'tooltip="{tooltip}" '
                f'shape=box style="rounded,filled" '
                f'fillcolor={_LEAF_FILL} color={_LEAF_BORDER}'
            )
            if v.attributes.get("active", False):
                node_attrs = (
                    f'label="{v.label}" '
                    f'tooltip="{tooltip}" '
                    f'shape=box style="rounded,filled" '
                    f'fillcolor="#90EE90" color={_LEAF_BORDER}'
                )
            lines.append(f"{pad}{safe} [{node_attrs}]")
            descs[safe] = md
            return safe

        cluster_id = f"cluster_{safe}"
        anchor_id  = f"_a_{safe}"
        fill, border = GraphRenderer._cluster_colors(depth)
        descs[cluster_id] = md
        lines.append(f"{pad}subgraph {cluster_id} {{")
        lines.append(f'{ipad}label="{v.label}"')
        lines.append(f'{ipad}style="rounded,filled"')
        lines.append(f"{ipad}fillcolor={fill}")
        lines.append(f"{ipad}color={border}")
        lines.append(f'{ipad}tooltip="{tooltip}"')
        # Invisible anchor — gives edges a concrete target node.
        lines.append(
            f"{ipad}{anchor_id} [label=\"\" style=invis width=0.01 height=0.01]"
        )
        for child in v.children:
            GraphRenderer._render_vertex(child, lines, descs, depth + 1)
        lines.append(f"{pad}}}")
        return anchor_id

    @staticmethod
    def _edge_to_dot(edge: Edge) -> str:
        """Render an explicit edge to a single DOT statement.

        Parallel fan-out edges (``edge.attributes["parallel"] == True``) are
        rendered as dashed blue arrows to visually distinguish them from plain
        sequential transitions.

        Args:
            edge: The edge to render.

        Returns:
            DOT statement string (no trailing newline).
        """
        from_id = GraphRenderer._safe_id(edge.from_id)
        to_id   = GraphRenderer._safe_id(edge.to_id)
        attrs: list[str] = []
        if edge.label:
            attrs.append(f'label="{edge.label}"')
        if not edge.directed:
            attrs.append("dir=none")
        if edge.attributes.get("parallel"):
            attrs.extend(["style=dashed", 'color="#1976d2"', "penwidth=2"])
        attr_str = f" [{', '.join(attrs)}]" if attrs else ""
        arrow    = "->" if edge.directed else "--"
        return f"{from_id} {arrow} {to_id}{attr_str}"

    # ------------------------------------------------------------------
    # Private — colour helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cluster_colors(depth: int) -> tuple[str, str]:
        """Return ``(fillcolor, border_color)`` for a cluster at *depth*."""
        return _CLUSTER_PALETTE[depth % len(_CLUSTER_PALETTE)]

    # ------------------------------------------------------------------
    # Private — DOT attribute helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _vertex_to_dot_tooltip(v: Vertex) -> str:
        """Build the ``tooltip`` attribute value for a DOT node or cluster.

        Returns a multi-line plain-text summary with nested dicts and lists
        expanded recursively (2-space indent per level), shown by Graphviz-aware
        viewers (e.g. xdot) and embedded as ``<title>`` in raw SVG output.

        Newlines are encoded as ``\\n`` (DOT escape). Double-quotes and
        backslashes are escaped so the value is safe inside a DOT double-quoted
        attribute.

        Args:
            v: Vertex whose description is rendered.

        Returns:
            Escaped DOT attribute value string (no surrounding quotes).
        """
        lines: list[str] = [v.label]
        for key, value in v.description.items():
            if key == "_type":
                continue
            lines.extend(GraphRenderer._dot_kv(key, value, indent=0))
        return GraphRenderer._dot_attr_escape("\n".join(lines))

    @staticmethod
    def _dot_kv(key: str, value: Any, indent: int) -> list[str]:
        """Recursively render a key/value pair as indented plain-text lines.

        Mirrors ``_md_kv`` but produces plain text instead of Markdown, suitable
        for DOT ``tooltip`` attribute values and SVG ``<title>`` elements.

        Args:
            key: Attribute name.
            value: Attribute value (scalar, dict, or list).
            indent: Number of 2-space indent levels.

        Returns:
            List of plain-text lines (no trailing newlines).
        """
        prefix = "  " * indent
        if isinstance(value, dict):
            result = [f"{prefix}{key}:"]
            for k, v in value.items():
                result.extend(GraphRenderer._dot_kv(k, v, indent + 1))
            return result
        if isinstance(value, list):
            result = [f"{prefix}{key}:"]
            for item in value:
                if isinstance(item, dict):
                    for k, v in item.items():
                        result.extend(GraphRenderer._dot_kv(k, v, indent + 1))
                else:
                    result.append(f"{prefix}  - {item}")
            return result
        text = str(value)
        if len(text) > 120:
            text = text[:117] + "…"
        return [f"{prefix}{key}: {text}"]

    @staticmethod
    def _dot_attr_escape(text: str) -> str:
        """Escape *text* for use inside a DOT double-quoted attribute value.

        Escapes backslashes and double-quotes, then converts Python newlines to
        the DOT ``\\n`` escape (rendered as newlines by Graphviz viewers and in
        SVG ``<title>`` elements).

        Args:
            text: Raw string to escape.

        Returns:
            Escaped string safe for ``attribute="<here>"``.
        """
        return (
            text
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
        )

    # ------------------------------------------------------------------
    # Private — interactive SVG injection
    # ------------------------------------------------------------------

    @staticmethod
    def _inject_svg_interactivity(svg_str: str, descs: dict[str, str]) -> str:
        """Post-process a Graphviz SVG string to add interactive hover tooltips.

        Injects before ``</svg>``:
        - A ``<defs>`` block with a drop-shadow filter and tooltip CSS.
        - A ``<g id="gv-tt">`` tooltip panel using ``<foreignObject>`` with an
          HTML div so that marked.js (or the inline fallback renderer) can
          render Markdown with full formatting.
        - A ``<script>`` block that attaches descriptions to SVG groups via
          ``<title>`` matching, then shows/hides/moves the tooltip on mouse
          events.  Converts screen coordinates to SVG coordinates so the panel
          follows the cursor correctly regardless of zoom or pan.

        Args:
            svg_str: Raw SVG string from Graphviz.
            descs: Mapping ``{dot_node_or_cluster_id: markdown_string}``.

        Returns:
            Modified SVG string with embedded interactivity.
        """
        descs_json = json.dumps(descs, ensure_ascii=False)
        injection = _SVG_INJECTION_TEMPLATE.replace("%%DESCRIPTIONS%%", descs_json)
        return svg_str.replace("</svg>", injection + "\n</svg>", 1)

    # ------------------------------------------------------------------
    # Private — tooltip Markdown helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _vertex_to_md(v: Vertex) -> str:
        """Convert a vertex to a Markdown string used as the HTML tooltip.

        Args:
            v: Source vertex.

        Returns:
            Markdown string with the vertex label, id, and description entries.
        """
        lines: list[str] = [f"## {v.label}"]
        if v.id != v.label:
            lines.append(f"*`{v.id}`*")
        lines.append("")
        for key, value in v.description.items():
            if key == "_type":
                continue
            lines.extend(GraphRenderer._md_kv(key, value, indent=0))
        return "\n".join(lines)

    @staticmethod
    def _md_kv(key: str, value: Any, indent: int) -> list[str]:
        """Recursively render a key/value pair as indented Markdown list items.

        Args:
            key: Attribute name.
            value: Attribute value (scalar, dict, or list).
            indent: Number of 2-space indent levels.

        Returns:
            List of Markdown lines.
        """
        prefix = "  " * indent
        if isinstance(value, dict):
            result = [f"{prefix}- **{key}**:"]
            for k, v in value.items():
                result.extend(GraphRenderer._md_kv(k, v, indent + 1))
            return result
        if isinstance(value, list):
            result = [f"{prefix}- **{key}**:"]
            for item in value:
                if isinstance(item, dict):
                    for k, v in item.items():
                        result.extend(GraphRenderer._md_kv(k, v, indent + 1))
                else:
                    result.append(f"{prefix}  - {item}")
            return result
        return [f"{prefix}- **{key}**: {value}"]

    # ------------------------------------------------------------------
    # Private — utility
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_id(vertex_id: str) -> str:
        """Sanitise a vertex path-ID to a valid Graphviz node identifier.

        Replaces all non-alphanumeric characters with underscores.

        Args:
            vertex_id: Raw vertex ID (may contain dots, brackets, …).

        Returns:
            DOT-safe identifier string.
        """
        return re.sub(r"[^a-zA-Z0-9]", "_", vertex_id).strip("_") or "node"

    @staticmethod
    def _require_graphviz() -> Any:
        """Import and return the ``graphviz`` module, or raise a clear ImportError.

        Raises:
            ImportError: When the ``graphviz`` Python package is absent.
        """
        try:
            import graphviz  # type: ignore[import]
            return graphviz
        except ImportError:
            raise ImportError(
                "The 'graphviz' Python package is required for visual output.\n"
                "  uv add graphviz          (or: pip install graphviz)\n"
                "Also ensure the system 'dot' executable is on PATH:\n"
                "  Ubuntu/Debian: sudo apt install graphviz\n"
                "  macOS:         brew install graphviz"
            ) from None


# ---------------------------------------------------------------------------
# SVG interactivity injection — inserted just before </svg>
# ---------------------------------------------------------------------------
#
# Placeholder:
#   %%DESCRIPTIONS%%  → JSON {dot_node_or_cluster_id: markdown_string}
#
# Strategy:
#   - A <defs> block adds a drop-shadow filter + <style> for the tooltip div.
#   - <g id="gv-tt"> holds a <rect> background and a <foreignObject> that
#     contains a fully styled HTML <div> — allowing rich Markdown rendering.
#   - The <script> block:
#     1. Reads each <g>'s first <title> child; matches the text to descs JSON.
#     2. Attaches _md to matched groups; removes all <title> elements so the
#        browser's native grey tooltip box is suppressed everywhere.
#     3. On mouseover, walks up the DOM to find the innermost group with _md,
#        renders Markdown into the tooltip div, and positions the panel.
#     4. getSVGPoint() converts screen coordinates to SVG document coordinates
#        so positioning works correctly at any zoom / pan level.
#     5. Tries to load marked.js from CDN after setup; falls back to an inline
#        mini-renderer (bold, italic, code, h2, h3, lists) if CDN fails.

_SVG_INJECTION_TEMPLATE = """\
<defs>
  <filter id="gv-tt-shadow" x="-10%" y="-10%" width="130%" height="130%">
    <feDropShadow dx="0" dy="3" stdDeviation="5" flood-opacity="0.20"/>
  </filter>
</defs>
<g id="gv-tt" display="none">
  <rect id="gv-tt-bg" width="390" height="430" rx="7" ry="7"
        fill="white" stroke="#1976d2" stroke-width="1.5"
        filter="url(#gv-tt-shadow)"/>
  <foreignObject width="390" height="430">
    <div xmlns="http://www.w3.org/1999/xhtml">
      <style type="text/css">
        #gv-tt-inner {
          font-family: Arial, sans-serif; font-size: 13px; line-height: 1.6;
          padding: 12px 14px; box-sizing: border-box; overflow-y: auto;
          height: 430px; border-left: 4px solid #1976d2;
        }
        #gv-tt-inner h2 {
          font-size: 1em; font-weight: bold; color: #1976d2;
          margin: 0 0 5px 0; border-bottom: 1px solid #eee; padding-bottom: 3px;
        }
        #gv-tt-inner h3  { font-size: 0.9em; color: #444; margin: 4px 0 2px; }
        #gv-tt-inner code {
          background: #f0f4f8; padding: 1px 4px; border-radius: 3px; font-size: 0.88em;
        }
        #gv-tt-inner strong { color: #222; }
        #gv-tt-inner em     { color: #666; }
        #gv-tt-inner ul, #gv-tt-inner ol { padding-left: 1.3em; margin: 3px 0; }
        #gv-tt-inner li  { margin: 2px 0; }
        #gv-tt-inner p   { margin: 2px 0; }
      </style>
      <div id="gv-tt-inner"></div>
    </div>
  </foreignObject>
</g>
<script type="text/javascript"><![CDATA[
(function () {
  "use strict";
  var descs = %%DESCRIPTIONS%%;
  var TT_W = 390, TT_H = 430, PAD = 12;

  // Inline mini Markdown renderer — fallback when marked.js is unavailable.
  function miniMd(text) {
    function esc(s) {
      return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
    var lines = esc(text).split("\n");
    var out = "";
    for (var i = 0; i < lines.length; i++) {
      var l = lines[i];
      if (/^## /.test(l))  { out += "<h2>" + l.slice(3) + "</h2>"; continue; }
      if (/^### /.test(l)) { out += "<h3>" + l.slice(4) + "</h3>"; continue; }
      // list items — capture leading spaces to compute indent depth
      var liMatch = l.match(/^( *)- (.*)/);
      if (liMatch) {
        var depth = liMatch[1].length;
        var item = liMatch[2]
          .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
          .replace(/\*([^*]+)\*/g, "<em>$1</em>")
          .replace(/`([^`]+)`/g, "<code>$1</code>");
        out += "<li style='margin-left:" + depth + "px'>" + item + "</li>";
        continue;
      }
      if (l.trim() === "") { out += "<br>"; continue; }
      var p = l
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/\*([^*]+)\*/g, "<em>$1</em>")
        .replace(/`([^`]+)`/g, "<code>$1</code>");
      out += "<p style='margin:2px 0'>" + p + "</p>";
    }
    return out;
  }

  var svg = (document.documentElement.tagName.toUpperCase() === "SVG")
    ? document.documentElement
    : document.querySelector("svg");
  if (!svg) return;

  var ttG     = document.getElementById("gv-tt");
  var ttInner = document.getElementById("gv-tt-inner");

  // Attach descriptions to <g> elements; remove all <title> elements so the
  // browser shows no native grey tooltip anywhere in the diagram.
  var allGroups = svg.querySelectorAll("g");
  for (var gi = 0; gi < allGroups.length; gi++) {
    var g = allGroups[gi];
    var titleEl = null;
    for (var ci = 0; ci < g.childNodes.length; ci++) {
      var node = g.childNodes[ci];
      if (node.nodeType === 1 && node.tagName === "title") { titleEl = node; break; }
    }
    if (!titleEl) continue;
    var key = titleEl.textContent.trim();
    if (descs[key]) { g._md = descs[key]; g.style.cursor = "pointer"; }
    g.removeChild(titleEl);
  }

  // Remove xlink:title from <a> elements: Graphviz tooltip= DOT attribute
  // generates these, causing a second native grey tooltip alongside the custom panel.
  var allAnchors = svg.querySelectorAll("a");
  for (var ai = 0; ai < allAnchors.length; ai++) {
    allAnchors[ai].removeAttribute("xlink:title");
    allAnchors[ai].removeAttribute("title");
  }

  function getSVGPoint(e) {
    try {
      var pt = svg.createSVGPoint();
      pt.x = e.clientX; pt.y = e.clientY;
      return pt.matrixTransform(svg.getScreenCTM().inverse());
    } catch (ex) {
      return { x: e.clientX, y: e.clientY };
    }
  }

  function renderMd(md) {
    return (typeof marked !== "undefined") ? marked.parse(md) : miniMd(md);
  }

  function positionTooltip(e) {
    var pt  = getSVGPoint(e);
    var vb  = svg.viewBox.baseVal;
    var maxX = (vb && vb.width  > 0) ? vb.x + vb.width  : 4000;
    var minY = (vb) ? vb.y : 0;
    var maxY = (vb && vb.height > 0) ? vb.y + vb.height : 4000;
    var tx = (pt.x + PAD + TT_W < maxX) ? pt.x + PAD : pt.x - TT_W - PAD;
    var ty = Math.max(minY, Math.min(pt.y, maxY - TT_H));
    ttG.setAttribute("transform", "translate(" + tx + "," + ty + ")");
  }

  svg.addEventListener("mouseover", function (e) {
    var el = e.target;
    while (el && el.tagName !== "svg" && el.tagName !== "SVG") {
      if (el._md) {
        ttInner.innerHTML = renderMd(el._md);
        ttG.setAttribute("display", "block");
        positionTooltip(e);
        return;
      }
      el = el.parentElement;
    }
    ttG.setAttribute("display", "none");
  });

  svg.addEventListener("mousemove", function (e) {
    if (ttG.getAttribute("display") === "none") return;
    positionTooltip(e);
  });

  svg.addEventListener("mouseleave", function () {
    ttG.setAttribute("display", "none");
  });

  // Attempt to load marked.js from CDN for richer Markdown rendering.
  // Falls back silently to miniMd() if CDN is unreachable.
  (function () {
    try {
      var s = document.createElement("script");
      s.type = "text/javascript";
      s.src  = "https://cdn.jsdelivr.net/npm/marked@9/marked.min.js";
      (document.head || document.documentElement).appendChild(s);
    } catch (e) { /* CDN unavailable — miniMd() remains active */ }
  }());
}());
]]></script>"""


# ---------------------------------------------------------------------------
# HTML template for interactive graph with Markdown tooltips
# ---------------------------------------------------------------------------
#
# Placeholders:
#   %%TITLE%%         → HTML-escaped page title (used in <title> and <h1>)
#   %%SVG%%           → inline SVG string from Graphviz
#   %%DESCRIPTIONS%%  → JSON {dot_node_or_cluster_id: markdown_string}
#
# JavaScript strategy:
#   1. Each <g> element in the SVG has a <title> child whose text equals the
#      Graphviz node/cluster ID.  We look up that ID in the descriptions JSON.
#   2. If found, we attach the Markdown string to the element as _md and
#      remove the native <title> to suppress the browser's grey tooltip box.
#   3. On mouseover we walk up the DOM to find the innermost group with _md
#      and render it with marked.js from CDN.
#   4. Tooltip follows the mouse; smart repositioning keeps it on screen.

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>%%TITLE%%</title>
  <script src="https://cdn.jsdelivr.net/npm/marked@9/marked.min.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; font-family: Arial, sans-serif; }
    body { display: flex; flex-direction: column; background: #f0f2f5; }
    #header {
      padding: 10px 20px; background: white;
      border-bottom: 1px solid #ddd; flex-shrink: 0;
    }
    #header h1 { font-size: 1.1rem; color: #2c3e50; font-weight: 600; }
    #svg-wrap {
      flex: 1; min-height: 0; overflow: auto;
      display: flex; align-items: flex-start; justify-content: center;
      padding: 24px;
    }
    #svg-wrap svg { max-width: none; height: auto; }
    #tt {
      display: none; position: fixed; z-index: 1000;
      max-width: 400px; max-height: 72vh; overflow-y: auto;
      background: white; border-radius: 8px; padding: 16px;
      box-shadow: 0 6px 28px rgba(0,0,0,.22);
      border-left: 4px solid #1976d2;
      font-size: 13px; line-height: 1.6; pointer-events: none;
    }
    #tt h1, #tt h2, #tt h3 { font-weight: bold; margin: 0.5em 0 0.2em; color: #1976d2; }
    #tt h1 { font-size: 1.05rem; border-bottom: 1px solid #eee; padding-bottom: 4px; }
    #tt h2 { font-size: 0.95rem; color: #333; }
    #tt h3 { font-size: 0.9rem;  color: #555; }
    #tt code { background: #f0f4f8; padding: 1px 5px; border-radius: 3px; font-size: 0.88em; }
    #tt pre  { background: #f0f4f8; padding: 8px; border-radius: 4px; margin: 6px 0; overflow-x: auto; }
    #tt pre code { background: none; padding: 0; }
    #tt ul, #tt ol { padding-left: 1.4em; margin: 3px 0; }
    #tt li { margin: 2px 0; }
    #tt p  { margin: 4px 0; }
    #tt em { color: #666; }
    #tt strong { color: #222; }
    #tt table { border-collapse: collapse; width: 100%; margin: 6px 0; }
    #tt td, #tt th { padding: 3px 8px; border: 1px solid #ddd; font-size: 0.9em; }
    #tt th { background: #f0f4f8; font-weight: 600; }
  </style>
</head>
<body>
  <div id="header"><h1 id="hdr-title">%%TITLE%%</h1></div>
  <div id="svg-wrap">%%SVG%%</div>
  <div id="tt"></div>
  <script>
    const descs = %%DESCRIPTIONS%%;
    const tt = document.getElementById("tt");

    // Attach Markdown descriptions to SVG groups by matching their <title>.
    // Remove <title> to suppress the browser's native grey tooltip box.
    document.querySelectorAll("#svg-wrap svg g").forEach(function(g) {
      const tel = g.querySelector(":scope > title");
      if (!tel) return;
      const key = tel.textContent.trim();
      const md = descs[key];
      if (md) { g._md = md; g.style.cursor = "pointer"; }
      tel.remove();
    });

    // Remove xlink:title from <a> elements: Graphviz tooltip= DOT attribute
    // generates these, causing a second native grey tooltip to appear.
    document.querySelectorAll("#svg-wrap svg a").forEach(function(a) {
      a.removeAttribute("xlink:title");
      a.removeAttribute("title");
    });

    // Optional header tooltip — shown when hovering the page title.
    const titleTt = %%TITLE_TOOLTIP%%;
    if (titleTt) {
      const hdrEl = document.getElementById("hdr-title");
      if (hdrEl) {
        hdrEl.style.cursor = "help";
        hdrEl.addEventListener("mouseover", function() {
          tt.innerHTML = (typeof marked !== "undefined")
            ? marked.parse(titleTt)
            : "<pre>" + titleTt.replace(/</g, "&lt;") + "</pre>";
          tt.style.display = "block";
        });
        hdrEl.addEventListener("mousemove", function(e) {
          const x = e.clientX + 18, y = e.clientY + 8;
          const w = tt.offsetWidth || 420;
          tt.style.left = (x + w > window.innerWidth ? e.clientX - w - 4 : x) + "px";
          tt.style.top  = Math.max(8, y) + "px";
        });
        hdrEl.addEventListener("mouseleave", function() {
          tt.style.display = "none";
        });
      }
    }

    // On hover: find the innermost group with a description and show tooltip.
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
      const w = tt.offsetWidth || 420;
      tt.style.left = (x + w > window.innerWidth ? e.clientX - w - 4 : x) + "px";
      tt.style.top  = Math.max(8, y) + "px";
    });

    document.getElementById("svg-wrap").addEventListener("mouseleave", function() {
      tt.style.display = "none";
    });
  </script>
</body>
</html>
"""
