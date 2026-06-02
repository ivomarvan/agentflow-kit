"""GraphRenderer — converts a Graph to Graphviz DOT, SVG, PNG, HTML, and browser output.

Rendering pipeline::

    Graph ──► _build_dot() ──► DOT source + vertex/edge description dicts
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
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentflow.describable.graph import Edge, Graph, Vertex

from agentflow.describable.tooltip_timing import HIDE_MS, IDLE_MS, OFFSET_X, OFFSET_Y

_HTML_TIMING_JS = (
    f"const IDLE_MS = {IDLE_MS}, HIDE_MS = {HIDE_MS}, "
    f"OFFSET_X = {OFFSET_X}, OFFSET_Y = {OFFSET_Y};"
)
_SVG_TIMING_JS = f"var IDLE_MS = {IDLE_MS}, HIDE_MS = {HIDE_MS};"


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

_USAGE_EDGE_LLM_STROKE = "#7b2fa8"
_USAGE_EDGE_TOOLS_STROKE = "#1a7a43"

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
        GraphRenderer.open_browser(graph, title="")   # None — opens browser (with_title=True)
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
        dot, _, _ = GraphRenderer._build_dot(graph)
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
        dot, _, _ = GraphRenderer._build_dot(graph)
        return GraphRenderer._render_svg_from_dot(dot)

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
        dot, _, _ = GraphRenderer._build_dot(graph)
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
    def _assemble_interactive_html(
        *,
        page_title: str,
        svg: str,
        descs: dict[str, str],
        edge_descs: dict[str, str],
        title_tooltip: str,
        with_title: bool,
    ) -> str:
        """Fill ``_HTML_TEMPLATE`` placeholders for one interactive graph page.

        Args:
            page_title: Document ``<title>`` and optional header ``<h1>`` text.
            svg: Inline SVG from Graphviz.
            descs: Vertex/cluster tooltip Markdown map.
            edge_descs: Usage-edge tooltip Markdown map.
            title_tooltip: Header hover Markdown (only when ``with_title``).
            with_title: Include the visible page header bar.

        Returns:
            Complete HTML document string.
        """
        escaped_title = _html_stdlib.escape(page_title)
        header = (
            f'  <div id="header"><h1 id="hdr-title">{escaped_title}</h1></div>\n'
            if with_title
            else ""
        )
        title_tt_json = json.dumps(
            title_tooltip if (with_title and title_tooltip) else None,
            ensure_ascii=False,
        )
        return (
            _HTML_TEMPLATE
            .replace("%%TITLE%%", escaped_title)
            .replace("%%HEADER%%", header)
            .replace("%%SVG%%", svg)
            .replace("%%DESCRIPTIONS%%", json.dumps(descs, ensure_ascii=False))
            .replace("%%EDGE_DESCRIPTIONS%%", json.dumps(edge_descs, ensure_ascii=False))
            .replace("%%TITLE_TOOLTIP%%", title_tt_json)
            .replace("%%TIMING_JS%%", _HTML_TIMING_JS)
        )

    @staticmethod
    def to_html(
        graph: Graph,
        title: str = "",
        title_tooltip: str = "",
        *,
        with_title: bool = True,
    ) -> str:
        """Return a standalone interactive HTML page for *graph*.

        Graphviz generates the SVG layout.  JavaScript overlays rich Markdown
        tooltips on hover using ``marked.js`` from CDN.  Hovering over any
        vertex (leaf or cluster) shows its full attribute description.
        When ``title_tooltip`` is provided and ``with_title`` is True, hovering
        over the page header shows a rich Markdown tooltip with that content.

        Args:
            graph: The composition graph to render.
            title: Page title in ``<title>``; also shown in the header when
                   ``with_title`` is True.  Defaults to the root vertex label.
            title_tooltip: Markdown tooltip for the page header (only when
                           ``with_title`` is True).
            with_title: When True, include the visible header bar with *title*.
                        Set False when embedding in another UI (e.g. GUI Structure tab).

        Returns:
            Complete self-contained HTML string (no external files needed).

        Raises:
            ImportError: If the ``graphviz`` Python package is not installed.
        """
        gv = GraphRenderer._require_graphviz()
        dot, descs, edge_descs = GraphRenderer._build_dot(graph)
        svg = GraphRenderer._render_svg_from_dot(dot)
        page_title = title or graph.root.label
        return GraphRenderer._assemble_interactive_html(
            page_title=page_title,
            svg=svg,
            descs=descs,
            edge_descs=edge_descs,
            title_tooltip=title_tooltip,
            with_title=with_title,
        )

    @staticmethod
    def dot_to_html(
        dot_source: str,
        *,
        title: str = "",
        title_tooltip: str = "",
        descs: dict[str, str] | None = None,
        edge_descs: dict[str, str] | None = None,
        with_title: bool = True,
    ) -> str:
        """Render an existing DOT source to the same interactive HTML as ``to_html()``.

        Uses ``_render_svg_from_dot()`` and ``_HTML_TEMPLATE``.  When *descs* /
        *edge_descs* are omitted, tooltip attributes are extracted from the DOT
        so hover panels work for agentflow-generated files.

        Args:
            dot_source: Graphviz DOT document.
            title: Page title; defaults to the first ``label=`` in the file.
            title_tooltip: Optional Markdown tooltip for the page header.
            descs: Vertex/cluster tooltip map; auto-extracted when ``None``.
            edge_descs: Usage-edge tooltip map; auto-extracted when ``None``.
            with_title: When True, include the visible header bar (CLI/HTML export).

        Returns:
            Complete standalone HTML string.

        Raises:
            ImportError: If the ``graphviz`` Python package is not installed.
        """
        parsed_descs, parsed_edge_descs = GraphRenderer._extract_tooltip_descs_from_dot(
            dot_source,
        )
        if descs is None:
            descs = parsed_descs
        if edge_descs is None:
            edge_descs = parsed_edge_descs
        GraphRenderer._require_graphviz()
        svg = GraphRenderer._render_svg_from_dot(dot_source)
        page_title = title or GraphRenderer._default_title_from_dot(dot_source)
        return GraphRenderer._assemble_interactive_html(
            page_title=page_title,
            svg=svg,
            descs=descs,
            edge_descs=edge_descs,
            title_tooltip=title_tooltip,
            with_title=with_title,
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
        dot, descs, edge_descs = GraphRenderer._build_dot(graph)
        raw_svg = GraphRenderer._render_svg_from_dot(dot)
        return GraphRenderer._inject_svg_interactivity(raw_svg, descs, edge_descs)

    @staticmethod
    def open_browser(
        graph: Graph,
        title: str = "",
        title_tooltip: str = "",
        *,
        with_title: bool = True,
    ) -> None:
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
            with_title: Forwarded to ``to_html()`` (default True for CLI/browser).
        """
        xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", "")
        if xdg_runtime:
            cache_dir = Path(xdg_runtime) / "agentflow" / "graphs"
        else:
            cache_dir = Path.home() / ".local" / "share" / "agentflow" / "graphs"
        cache_dir.mkdir(parents=True, exist_ok=True)

        content = GraphRenderer.to_html(
            graph,
            title=title,
            title_tooltip=title_tooltip,
            with_title=with_title,
        )
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", graph.root.label)
        out = cache_dir / f"{safe_name}.html"
        out.write_text(content, encoding="utf-8")
        os.chmod(out, 0o644)
        webbrowser.open(out.as_uri())

    # ------------------------------------------------------------------
    # Private — DOT building
    # ------------------------------------------------------------------

    @staticmethod
    def _build_dot(graph: Graph) -> tuple[str, dict[str, str], dict[str, str]]:
        """Build the DOT source and tooltip description dicts for rendering.

        Returns:
            Tuple of ``(dot_source, vertex_descs, edge_descs)``.
            Vertex keys match Graphviz node/cluster ``<title>`` text; edge keys
            match Graphviz edge ``<title>`` text (with optional ``:port`` suffix).
        """
        lines: list[str] = [
            "digraph {",
            "  rankdir=TB",
            "  center=true",
            "  compound=true",
            "  splines=true",
            '  node [fontname="Helvetica" fontsize=11]',
            '  edge [fontname="Helvetica" fontsize=9 color=gray40]',
        ]
        descs: dict[str, str] = {}
        edge_descs: dict[str, str] = {}
        GraphRenderer._render_vertex(graph.root, lines, descs, depth=0)
        for edge in graph.edges:
            lines.append(f"  {GraphRenderer._edge_to_dot(edge, edge_descs)}")
        lines.append("}")
        return "\n".join(lines), descs, edge_descs

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

        Depth-based layout rules (depth = distance from AgentApp root):
          depth 0  — AgentApp stacks StateGraph above Context (invisible edges).
          depth 1  — StateGraph uses ``rankdir=LR``; Context uses ``rankdir=TB``
                     and stacks its child clusters vertically.
          depth ≥2 — compact clusters: smaller frame margin and tighter node
                     margins / font to keep inner boxes visually lean.

        Args:
            v: Vertex to render.
            lines: List to append DOT statements to (mutated in place).
            descs: Dict populated with ``{dot_id: markdown}`` for tooltips.
            depth: Nesting depth — controls indentation, colour palette, and
                   depth-based layout adjustments.

        Returns:
            DOT id of this vertex: leaf node id or the cluster's anchor id.
        """
        pad  = "  " * (depth + 1)   # outer indent (inside digraph / parent cluster)
        ipad = "  " * (depth + 2)   # inner indent (inside this cluster)
        safe    = GraphRenderer._safe_id(v.id)
        md      = GraphRenderer._vertex_to_md(v)
        tooltip = GraphRenderer._vertex_to_dot_tooltip(v)
        url_suffix = GraphRenderer._dot_url_suffix(v)

        if not v.children:
            fill = "#90EE90" if v.attributes.get("active", False) else _LEAF_FILL
            # Compact leaf nodes deep in the hierarchy: tighter padding and smaller font.
            compact = ' margin="0.1,0.04" fontsize=10' if depth >= 3 else ""
            node_attrs = (
                f'label="{v.label}"'
                f'{url_suffix} '
                f'tooltip="{tooltip}" '
                f'shape=box style="rounded,filled" '
                f'fillcolor={fill} color={_LEAF_BORDER}'
                f"{compact}"
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
        if url_suffix:
            lines.append(f"{ipad}{url_suffix.lstrip()}")
        lines.append(f'{ipad}style="rounded,filled"')
        lines.append(f"{ipad}fillcolor={fill}")
        lines.append(f"{ipad}color={border}")
        lines.append(f'{ipad}tooltip="{tooltip}"')
        cluster_rankdir = GraphRenderer._cluster_rankdir(v, depth)
        if cluster_rankdir is not None:
            lines.append(f"{ipad}rankdir={cluster_rankdir}")
        # Compact inner clusters: tighter frame padding (default Graphviz margin is ~8 pt).
        if depth >= 2:
            lines.append(f'{ipad}margin="10,5"')
        usage_port_cluster = GraphRenderer._is_usage_port_cluster(v)
        anchor_after_children = GraphRenderer._cluster_anchor_after_children(v)
        invis_anchor = (
            f"{ipad}{anchor_id} [label=\"\" style=invis width=0.01 height=0.01]"
        )
        if not anchor_after_children:
            lines.append(invis_anchor)
        child_anchors: list[tuple[str, str]] = []
        usage_port_leaves: list[str] = []
        for child in v.children:
            child_anchor = GraphRenderer._render_vertex(child, lines, descs, depth + 1)
            if child_anchor.startswith("_a_"):
                child_anchors.append((child.label, child_anchor))
            elif usage_port_cluster:
                usage_port_leaves.append(child_anchor)
        if usage_port_cluster:
            GraphRenderer._align_usage_port_anchor(
                lines, ipad, anchor_id, usage_port_leaves
            )
        elif anchor_after_children:
            lines.append(invis_anchor)

        if depth == 0:
            GraphRenderer._append_vertical_stack_edges(lines, ipad, child_anchors, root=True)
        elif depth == 1 and v.label == "Context":
            GraphRenderer._append_vertical_stack_edges(lines, ipad, child_anchors, root=False)

        lines.append(f"{pad}}}")
        return anchor_id

    # Preferred top-to-bottom order for AgentApp's depth-1 clusters in graph output.
    _AGENTAPP_CLUSTER_ORDER: dict[str, int] = {"StateGraph": 0, "Context": 1}
    # Clusters that receive dashed usage edges from StateGraph vertices.
    _USAGE_PORT_CLUSTER_LABELS: frozenset[str] = frozenset({"LlmConnector", "ToolRegistry"})

    @staticmethod
    def _is_usage_port_cluster(v: Vertex) -> bool:
        """Return True when dashed usage edges should attach to *v*'s west port."""
        return v.label in GraphRenderer._USAGE_PORT_CLUSTER_LABELS

    @staticmethod
    def _cluster_anchor_after_children(v: Vertex) -> bool:
        """Return True when the invisible cluster anchor is emitted after children.

        StateGraph uses ``rankdir=LR``; declaring its anchor after state vertices
        keeps the left-to-right flow unobstructed for usage edges leaving via
        ``tailport=e``.
        """
        return v.label == "StateGraph"

    @staticmethod
    def _align_usage_port_anchor(
        lines: list[str],
        ipad: str,
        anchor_id: str,
        leaf_ids: list[str],
    ) -> None:
        """Vertically align a west-side usage port anchor with the middle leaf.

        The invisible anchor node is declared before visible children so Graphviz
        places it on the left cluster border for ``headport=w`` compound edges.

        Args:
            lines: DOT line buffer to append to.
            ipad: Indentation prefix inside the parent cluster.
            anchor_id: Invisible anchor node identifier (already declared).
            leaf_ids: DOT ids of rendered leaf nodes inside the cluster.
        """
        if leaf_ids:
            mid_leaf = leaf_ids[len(leaf_ids) // 2]
            lines.append(f"{ipad}{{ rank=same; {anchor_id}; {mid_leaf}; }}")

    @staticmethod
    def _cluster_rankdir(v: Vertex, depth: int) -> str | None:
        """Return a Graphviz ``rankdir`` for cluster *v*, or ``None`` for default.

        Args:
            v: Cluster vertex being rendered.
            depth: Nesting depth from the application root.

        Returns:
            ``"LR"``, ``"TB"``, or ``None`` when the global digraph default applies.
        """
        if v.label == "StateGraph":
            return "LR"
        if v.label == "Context":
            return "TB"
        if depth == 0:
            return "TB"
        return None

    @staticmethod
    def _append_vertical_stack_edges(
        lines: list[str],
        ipad: str,
        child_anchors: list[tuple[str, str]],
        *,
        root: bool,
    ) -> None:
        """Add invisible edges that force sibling clusters into a vertical column.

        Args:
            lines: DOT line buffer to append to.
            ipad: Indentation prefix for statements inside the parent cluster.
            child_anchors: ``(child_label, anchor_dot_id)`` for each sub-cluster.
            root: When ``True``, sort StateGraph before Context for AgentApp layout.
        """
        if len(child_anchors) < 2:
            return
        ordered = child_anchors
        if root:
            ordered = sorted(
                child_anchors,
                key=lambda item: GraphRenderer._AGENTAPP_CLUSTER_ORDER.get(item[0], 99),
            )
        for (_, from_anchor), (_, to_anchor) in zip(ordered, ordered[1:]):
            lines.append(
                f"{ipad}{from_anchor} -> {to_anchor} [style=invis, weight=100]"
            )

    @staticmethod
    def _register_usage_edge_tooltip(
        edge_descs: dict[str, str],
        from_dot: str,
        to_anchor: str,
        summary: str,
    ) -> None:
        """Store Markdown tooltip text for a usage edge under Graphviz title keys.

        Graphviz edge ``<title>`` values include an optional ``:port`` suffix when
        ``headport`` / ``tailport`` are set; both variants are registered.

        Args:
            edge_descs: Edge-description dict mutated in place.
            from_dot: Source node DOT identifier.
            to_anchor: Target invisible anchor node DOT identifier.
            summary: Plain-text usage summary shown in the tooltip heading.
        """
        markdown = f"## {summary}"
        for key in (
            f"{from_dot}:e->{to_anchor}:w",
            f"{from_dot}->{to_anchor}:w",
            f"{from_dot}->{to_anchor}",
        ):
            edge_descs[key] = markdown

    @staticmethod
    def _edge_to_dot(edge: Edge, edge_descs: dict[str, str] | None = None) -> str:
        """Render an explicit edge to a single DOT statement.

        Three edge flavours are supported:

        * **Parallel fan-out** (``edge.attributes["parallel"] == True``):
          dashed blue arrow — distinguishes fan-out from sequential transitions.
        * **Usage** (``edge.attributes["usage"] == True``):
          dashed undirected line from a StateVertex to the LlmConnector or ToolRegistry
          cluster it uses.  ``headport=w`` / ``tailport=e`` attach the line to the
          left-centre of the target cluster and the right-centre of the source vertex.
          The human-readable usage summary is stored in ``edge_descs`` for HTML/SVG tooltips, not as a
          visible edge label.  ``lhead`` clips the segment to the cluster boundary.
        * **Default**: plain grey directed or undirected arrow.

        Args:
            edge: The edge to render.
            edge_descs: Optional dict populated with usage-edge tooltip Markdown.

        Returns:
            DOT statement string (no trailing newline).
        """
        if edge.attributes.get("usage"):
            from_dot = GraphRenderer._safe_id(edge.from_id)
            to_safe  = GraphRenderer._safe_id(edge.to_id)
            to_anchor = f"_a_{to_safe}"
            color    = (
                f'"{_USAGE_EDGE_LLM_STROKE}"'
                if edge.attributes.get("usage_type") == "llm"
                else f'"{_USAGE_EDGE_TOOLS_STROKE}"'
            )
            # dir=none + arrowsize=0 yields undirected usage lines.  Do not set
            # arrowhead=none/arrowtail=none together with headport/tailport compass
            # points — Graphviz mis-parses the port letter as an arrow type name
            # (e.g. Warning: Arrow type "w" unknown).
            attrs = [
                "style=dashed",
                "dir=none",
                "arrowsize=0",
                f"color={color}",
                "penwidth=1",
                "tailport=e",
                "headport=w",
                f'lhead="cluster_{to_safe}"',
            ]
            if edge.label:
                tooltip = GraphRenderer._dot_attr_escape(edge.label)
                attrs.append(f'tooltip="{tooltip}"')
                if edge_descs is not None:
                    GraphRenderer._register_usage_edge_tooltip(
                        edge_descs, from_dot, to_anchor, edge.label,
                    )
            return f"{from_dot} -> {to_anchor} [{', '.join(attrs)}]"

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
    def _skip_description_key(v: Vertex, key: str, value: Any) -> bool:
        """Return True when *key* should be omitted from graph tooltip rendering.

        Skips structural keys and ``name`` when it duplicates the vertex label.

        Args:
            v: Vertex being rendered.
            key: Description dict key.
            value: Description dict value.

        Returns:
            ``True`` when the key/value pair must not appear in tooltips.
        """
        if key == "_type":
            return True
        return key == "name" and str(value) == v.label

    @staticmethod
    @lru_cache(maxsize=1)
    def _agentflow_package_root() -> Path | None:
        """Return the installed ``agentflow`` package directory, if importable.

        Uses ``agentflow.__file__`` so library detection works for editable
        checkouts and pip-installed wheels alike.

        Returns:
            Absolute path to the ``agentflow`` package root, or ``None``.
        """
        try:
            import agentflow
        except ImportError:
            return None
        package_file = getattr(agentflow, "__file__", None)
        if not package_file:
            return None
        return Path(package_file).resolve().parent

    @staticmethod
    def _is_library_vertex(v: Vertex) -> bool:
        """Return True when the vertex class is defined inside the ``agentflow`` package.

        Args:
            v: Vertex with optional ``source_file`` metadata.

        Returns:
            ``True`` for library classes; ``False`` for user/application code.
        """
        if not v.source_file:
            return False
        root = GraphRenderer._agentflow_package_root()
        if root is None:
            return False
        try:
            return Path(v.source_file).resolve().is_relative_to(root)
        except (OSError, ValueError):
            return False

    @staticmethod
    def _truncate_library_description(text: str) -> str:
        """Shorten a library docstring to the first sentence or paragraph.

        Stops at the first period (included) or blank line (paragraph break).
        When the source text continues beyond that point, appends `` ...``.

        Args:
            text: Full class or field description text.

        Returns:
            One-sentence summary, optionally suffixed with `` ...``.
        """
        remaining = text.strip()
        if not remaining:
            return ""

        period_idx = remaining.find(".")
        blank_line_idx = remaining.find("\n\n")
        cutoffs: list[int] = []
        if period_idx >= 0:
            cutoffs.append(period_idx + 1)
        if blank_line_idx >= 0:
            cutoffs.append(blank_line_idx)

        if cutoffs:
            end = min(cutoffs)
            short = remaining[:end].strip()
            tail = remaining[end:].strip()
        else:
            short = remaining
            tail = ""

        if tail and not short.endswith("..."):
            return f"{short} ..."
        return short

    @staticmethod
    def _tooltip_description_text(v: Vertex) -> str | None:
        """Return the body description line(s) for graph tooltips.

        Library vertices get a one-sentence summary; user vertices keep the full
        text.  The result is rendered without a ``description:`` field label.

        Args:
            v: Vertex whose ``description`` dict may contain a ``description`` key.

        Returns:
            Plain-text description body, or ``None`` when absent or skipped.
        """
        if "description" not in v.description:
            return None
        raw = v.description["description"]
        if GraphRenderer._skip_description_key(v, "description", raw):
            return None
        text = str(raw).strip()
        if not text:
            return None
        if GraphRenderer._is_library_vertex(v):
            text = GraphRenderer._truncate_library_description(text)
        return text

    @staticmethod
    def _iter_tooltip_attribute_items(v: Vertex) -> list[tuple[str, Any]]:
        """Return description dict entries rendered below the free-form body text.

        Args:
            v: Source vertex.

        Returns:
            ``(key, value)`` pairs excluding structural keys and ``description``.
        """
        items: list[tuple[str, Any]] = []
        for key, value in v.description.items():
            if key == "description":
                continue
            if GraphRenderer._skip_description_key(v, key, value):
                continue
            items.append((key, value))
        return items

    @staticmethod
    def _vertex_source_href(v: Vertex) -> str | None:
        """Return a ``file://`` URL pointing at the class definition, if known.

        Args:
            v: Vertex whose ``source_file`` / ``source_line`` are used.

        Returns:
            URL string suitable for Markdown links, or ``None`` when unavailable.
        """
        if not v.source_file or v.source_line <= 0:
            return None
        try:
            return Path(v.source_file).resolve().as_uri() + f"#L{v.source_line}"
        except (OSError, ValueError):
            return None

    @staticmethod
    def _dot_url_suffix(v: Vertex) -> str:
        """Return a Graphviz ``URL`` attribute suffix for clickable vertex labels.

        Graphviz embeds ``URL`` as ``xlink:href`` on the node/cluster label in SVG
        output (``graph --format svg|html``, ``graph --browser``, interactive SVG).

        Args:
            v: Vertex whose source location is linked when known.

        Returns:
            Empty string, or `` URL="file://…"`` safe for inline DOT attributes.
        """
        href = GraphRenderer._vertex_source_href(v)
        if href is None:
            return ""
        escaped = href.replace("\\", "\\\\").replace('"', '\\"')
        return f' URL="{escaped}"'

    @staticmethod
    def _vertex_heading_md(v: Vertex) -> str:
        """Return the Markdown heading line for a vertex tooltip.

        Source links are rendered on graph labels (Graphviz ``URL``), not here,
        because tooltip panels follow the cursor and label links are clickable.

        Args:
            v: Source vertex.

        Returns:
            Plain ``## Label`` heading without hyperlinks.
        """
        return f"## {v.label}"

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
        body = GraphRenderer._tooltip_description_text(v)
        if body:
            lines.append(body)
        for key, value in GraphRenderer._iter_tooltip_attribute_items(v):
            lines.extend(GraphRenderer._dot_kv(key, value, indent=1))
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

    @staticmethod
    def _dot_attr_unescape(text: str) -> str:
        """Reverse ``_dot_attr_escape`` for tooltip values read from DOT source.

        Args:
            text: Escaped attribute value from a DOT file (without surrounding quotes).

        Returns:
            Unescaped plain text.
        """
        return (
            text
            .replace("\\n", "\n")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
        )

    _DOT_TOOLTIP_RE = re.compile(r'tooltip="((?:\\.|[^"\\])*)"')
    _DOT_NODE_LINE_RE = re.compile(r"^(\s*)([A-Za-z_]\w*)\s+\[")
    _DOT_SUBGRAPH_RE = re.compile(r"^\s*subgraph\s+(cluster_\w+)\s*\{")
    _DOT_USAGE_EDGE_RE = re.compile(
        r"^(\s*)([A-Za-z_]\w*)\s+->\s+(_a_[A-Za-z_]\w*)\s+\[(.*)\]\s*$",
    )

    @staticmethod
    def _tooltip_to_markdown(raw: str) -> str:
        """Convert a Graphviz tooltip string to the Markdown heading used in HTML hover."""
        text = GraphRenderer._dot_attr_unescape(raw).strip()
        if not text:
            return ""
        if "\n" in text:
            heading, body = text.split("\n", 1)
            return f"## {heading}\n{body}"
        return f"## {text}"

    @staticmethod
    def _extract_dot_attribute(attrs: str, name: str) -> str | None:
        """Return the unescaped value of *name* from a DOT attribute list string."""
        match = re.search(
            rf'{name}="((?:\\.|[^"\\])*)"',
            attrs,
        )
        if not match:
            return None
        return GraphRenderer._dot_attr_unescape(match.group(1))

    @staticmethod
    def _default_title_from_dot(dot_source: str) -> str:
        """Guess a page title from the first ``label=`` attribute in *dot_source*."""
        match = re.search(r'label="((?:\\.|[^"\\])*)"', dot_source)
        if match:
            return GraphRenderer._dot_attr_unescape(match.group(1))
        return "Graph"

    @staticmethod
    def _extract_tooltip_descs_from_dot(
        dot_source: str,
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Build vertex and usage-edge description dicts from DOT ``tooltip=`` attrs.

        Keys match Graphviz SVG ``<title>`` text so the HTML hover script can resolve
        them the same way as graphs built via ``_build_dot()``.

        Args:
            dot_source: Graphviz DOT document.

        Returns:
            Tuple ``(vertex_descs, edge_descs)``.
        """
        descs: dict[str, str] = {}
        edge_descs: dict[str, str] = {}
        cluster_stack: list[str] = []

        for line in dot_source.splitlines():
            subgraph_match = GraphRenderer._DOT_SUBGRAPH_RE.match(line)
            if subgraph_match:
                cluster_stack.append(subgraph_match.group(1))
                continue

            stripped = line.strip()
            if stripped == "}" and cluster_stack:
                cluster_stack.pop()
                continue

            edge_match = GraphRenderer._DOT_USAGE_EDGE_RE.match(line)
            if edge_match:
                from_dot, to_anchor, attrs = edge_match.group(2), edge_match.group(3), edge_match.group(4)
                summary = GraphRenderer._extract_dot_attribute(attrs, "tooltip")
                if summary and "style=dashed" in attrs:
                    GraphRenderer._register_usage_edge_tooltip(
                        edge_descs, from_dot, to_anchor, summary,
                    )
                continue

            node_match = GraphRenderer._DOT_NODE_LINE_RE.match(line)
            tooltip_match = GraphRenderer._DOT_TOOLTIP_RE.search(line)
            if not tooltip_match:
                continue

            markdown = GraphRenderer._tooltip_to_markdown(tooltip_match.group(1))
            if not markdown:
                continue

            if node_match:
                descs[node_match.group(2)] = markdown
                continue

            if cluster_stack and "tooltip=" in line and "->" not in line:
                descs[cluster_stack[-1]] = markdown

        return descs, edge_descs

    # ------------------------------------------------------------------
    # Private — interactive SVG injection
    # ------------------------------------------------------------------

    @staticmethod
    def _inject_svg_interactivity(
        svg_str: str,
        descs: dict[str, str],
        edge_descs: dict[str, str] | None = None,
    ) -> str:
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
            edge_descs: Mapping ``{edge_title: markdown_string}`` for usage edges.

        Returns:
            Modified SVG string with embedded interactivity.
        """
        descs_json = json.dumps(descs, ensure_ascii=False)
        edge_descs_json = json.dumps(edge_descs or {}, ensure_ascii=False)
        injection = (
            _SVG_INJECTION_TEMPLATE
            .replace("%%DESCRIPTIONS%%", descs_json)
            .replace("%%EDGE_DESCRIPTIONS%%", edge_descs_json)
            .replace("%%TIMING_JS%%", _SVG_TIMING_JS)
        )
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
        lines: list[str] = [GraphRenderer._vertex_heading_md(v)]
        if v.id != v.label:
            lines.append(f"*`{v.id}`*")
        lines.append("")
        body = GraphRenderer._tooltip_description_text(v)
        if body:
            lines.append(body)
        for key, value in GraphRenderer._iter_tooltip_attribute_items(v):
            lines.extend(GraphRenderer._md_kv(key, value, indent=1))
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

    # Inline SVG styles for Graphviz label hyperlinks (file:// class definitions).
    _SVG_LABEL_LINK_STYLE = (
        "a { cursor: pointer; }"
        "a text { fill: #1565c0; text-decoration: underline;"
        " text-decoration-color: #1565c0; }"
    )

    @staticmethod
    def _render_svg_from_dot(dot: str) -> str:
        """Render DOT to SVG and post-process label hyperlinks for all graph outputs.

        Args:
            dot: Graphviz DOT source.

        Returns:
            SVG string with new-tab targets and label link styling applied.
        """
        gv = GraphRenderer._require_graphviz()
        svg = gv.Source(dot, format="svg").pipe().decode("utf-8")
        svg = GraphRenderer._strip_usage_edge_arrowheads(svg)
        return GraphRenderer._enhance_label_links(svg)

    _USAGE_EDGE_STROKE_COLORS: frozenset[str] = frozenset({
        _USAGE_EDGE_LLM_STROKE,
        _USAGE_EDGE_TOOLS_STROKE,
    })

    @staticmethod
    def _strip_usage_edge_arrowheads(svg_str: str) -> str:
        """Remove arrow polygons from dashed LLM/tool usage edges in Graphviz SVG.

        ``dir=none`` with ``arrowsize=0`` suppresses most arrowheads, but some
        compound edges still emit a degenerate ``<polygon>``; those are stripped
        so usage lines stay visually undirected.

        Args:
            svg_str: Raw SVG from Graphviz.

        Returns:
            SVG string with usage-edge arrow polygons removed.
        """
        usage_strokes = GraphRenderer._USAGE_EDGE_STROKE_COLORS

        def _clean_edge_block(match: re.Match[str]) -> str:
            block = match.group(0)
            if "stroke-dasharray" not in block:
                return block
            if not any(f'stroke="{color}"' in block for color in usage_strokes):
                return block
            return re.sub(r"<polygon[^>]*/>", "", block)

        return re.sub(
            r'<g id="(?:a_)?edge\d+" class="edge">.*?</g>',
            _clean_edge_block,
            svg_str,
            flags=re.DOTALL,
        )

    @staticmethod
    def _enhance_label_links(svg_str: str) -> str:
        """Add new-tab navigation and link styling to Graphviz ``URL`` anchors in SVG.

        Graphviz emits ``<a xlink:href="…">`` around vertex/cluster labels.  This
        adds ``target="_blank"``, injects shared CSS, and keeps tooltip cleanup
        separate (handled in HTML/JS templates).

        Args:
            svg_str: Raw SVG from Graphviz.

        Returns:
            Post-processed SVG string.
        """
        if "xlink:href=" not in svg_str:
            return svg_str

        svg_str = GraphRenderer._inject_svg_label_link_style(svg_str)

        def _add_new_tab_target(match: re.Match[str]) -> str:
            tag = match.group(0)
            if "target=" in tag:
                return tag
            return tag[:-1] + ' target="_blank" rel="noopener noreferrer">'

        return re.sub(
            r'<a\b[^>]*xlink:href="[^"]*"[^>]*>',
            _add_new_tab_target,
            svg_str,
        )

    @staticmethod
    def _inject_svg_label_link_style(svg_str: str) -> str:
        """Insert CSS for blue underlined label links into an SVG document.

        Args:
            svg_str: SVG XML string.

        Returns:
            SVG with a ``<style>`` block immediately after the root ``<svg>`` tag.
        """
        marker = GraphRenderer._SVG_LABEL_LINK_STYLE
        if marker in svg_str:
            return svg_str
        style_block = (
            f'<style type="text/css"><![CDATA[{GraphRenderer._SVG_LABEL_LINK_STYLE}]]></style>'
        )
        return re.sub(r"(<svg[^>]*>)", r"\1\n" + style_block, svg_str, count=1)

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

_SVG_INJECTION_TEMPLATE = r"""\
<defs>
  <style type="text/css"><![CDATA[
    a { cursor: pointer; }
    a text { fill: #1565c0; text-decoration: underline; text-decoration-color: #1565c0; }
  ]]></style>
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
  var edgeDescs = %%EDGE_DESCRIPTIONS%%;
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

  // --- Sticky tooltip --------------------------------------------------
  // The panel follows the cursor while it moves, then "freezes" after a
  // short idle so the user can move into it and scroll long content.
  //   IDLE_MS — cursor must rest this long before the panel freezes.
  //   HIDE_MS — grace period when leaving a node, so the cursor can cross
  //             the small offset gap into the panel without it vanishing.
  %%TIMING_JS%%
  var ttSource = null;   // element currently described
  var frozen = false;    // when true the panel stays put and is scrollable
  var hideTimer = null, idleTimer = null;

  function tipContains(node) {
    while (node) { if (node === ttG) return true; node = node.parentNode; }
    return false;
  }
  function clearHide() { if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; } }
  function clearIdle() { if (idleTimer) { clearTimeout(idleTimer); idleTimer = null; } }
  function hideTip() {
    clearHide(); clearIdle();
    ttG.setAttribute("display", "none");
    frozen = false; ttSource = null;
  }
  function scheduleHide() { clearHide(); hideTimer = setTimeout(hideTip, HIDE_MS); }
  function freezeTip() { frozen = true; }
  function armIdle() { clearIdle(); idleTimer = setTimeout(freezeTip, IDLE_MS); }

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

    function lookupEdgeMd(titleKey) {
      if (edgeDescs[titleKey]) return edgeDescs[titleKey];
      var colon = titleKey.lastIndexOf(":");
      if (colon > 0 && edgeDescs[titleKey.slice(0, colon)]) {
        return edgeDescs[titleKey.slice(0, colon)];
      }
      var normalized = titleKey.replace(/^([^:]+):[a-z]+->/, "$1->");
      if (edgeDescs[normalized]) return edgeDescs[normalized];
      colon = normalized.lastIndexOf(":");
      if (colon > 0 && edgeDescs[normalized.slice(0, colon)]) {
        return edgeDescs[normalized.slice(0, colon)];
      }
      return null;
    }

  var allEdges = svg.querySelectorAll("g.edge");
  for (var ei = 0; ei < allEdges.length; ei++) {
    var edgeG = allEdges[ei];
    var edgeTitle = null;
    for (var ec = 0; ec < edgeG.childNodes.length; ec++) {
      var edgeNode = edgeG.childNodes[ec];
      if (edgeNode.nodeType === 1 && edgeNode.tagName === "title") {
        edgeTitle = edgeNode;
        break;
      }
    }
    if (!edgeTitle) continue;
    var edgeKey = edgeTitle.textContent.trim();
    var edgeMd = lookupEdgeMd(edgeKey);
    if (edgeMd) {
      edgeG._md = edgeMd;
      edgeG.style.cursor = "help";
    }
    edgeG.removeChild(edgeTitle);
  }

  // Remove xlink:title from <a> elements: Graphviz tooltip= DOT attribute
  // generates these, causing a second native grey tooltip alongside the custom panel.
  var allAnchors = svg.querySelectorAll("a");
  for (var ai = 0; ai < allAnchors.length; ai++) {
    var anchor = allAnchors[ai];
    if (anchor.hasAttribute("xlink:href") || anchor.hasAttribute("href")) {
      anchor.setAttribute("target", "_blank");
      anchor.setAttribute("rel", "noopener noreferrer");
    }
    anchor.removeAttribute("xlink:title");
    anchor.removeAttribute("title");
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
    if (tipContains(e.target)) { clearHide(); freezeTip(); return; }
    var el = e.target;
    while (el && el.tagName !== "svg" && el.tagName !== "SVG") {
      if (el._md) {
        if (ttSource !== el) {       // new target — render, reposition, re-arm
          ttSource = el;
          ttInner.innerHTML = renderMd(el._md);
          frozen = false;
          ttG.setAttribute("display", "block");
          positionTooltip(e);
        }
        clearHide();
        if (!frozen) armIdle();
        return;
      }
      el = el.parentElement;
    }
    scheduleHide();
  });

  svg.addEventListener("mousemove", function (e) {
    if (ttG.getAttribute("display") === "none" || frozen) return;
    if (tipContains(e.target)) return;
    positionTooltip(e);
    armIdle();
  });

  svg.addEventListener("mouseleave", scheduleHide);

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
#   %%TITLE%%         → HTML-escaped page title (used in <title>)
#   %%HEADER%%        → optional header bar with <h1> (empty when with_title=False)
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
    #svg-wrap svg a { cursor: pointer; }
    #svg-wrap svg a text {
      fill: #1565c0;
      text-decoration: underline;
      text-decoration-color: #1565c0;
    }
    #tt {
      display: none; position: fixed; z-index: 1000;
      max-width: 400px; max-height: 72vh; overflow-y: auto;
      background: white; border-radius: 8px; padding: 16px;
      box-shadow: 0 6px 28px rgba(0,0,0,.22);
      border-left: 4px solid #1976d2;
      font-size: 13px; line-height: 1.6; pointer-events: none;
    }
    /* When frozen (cursor idle or hovering the panel) the tooltip becomes
       interactive so its scrollbar can be used. */
    #tt.sticky { pointer-events: auto; }
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
%%HEADER%%  <div id="svg-wrap">%%SVG%%</div>
  <div id="tt"></div>
  <script>
    const descs = %%DESCRIPTIONS%%;
    const edgeDescs = %%EDGE_DESCRIPTIONS%%;
    const tt = document.getElementById("tt");

    // --- Sticky tooltip ---------------------------------------------------
    // The panel follows the cursor while it moves, then "freezes" after a
    // short idle so the user can move into it and scroll long content.
    //   IDLE_MS — cursor must rest this long before the panel freezes.
    //   HIDE_MS — grace period when leaving a node, so the cursor can cross
    //             the small offset gap into the panel without it vanishing.
    %%TIMING_JS%%
    let ttSource = null;   // element (or "title") currently described
    let frozen = false;    // when true the panel stays put and is scrollable
    let hideTimer = null, idleTimer = null;

    function renderMd(md) {
      return (typeof marked !== "undefined")
        ? marked.parse(md)
        : "<pre>" + md.replace(/</g, "&lt;") + "</pre>";
    }
    function clearHide() { if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; } }
    function clearIdle() { if (idleTimer) { clearTimeout(idleTimer); idleTimer = null; } }
    function hideTip() {
      clearHide(); clearIdle();
      tt.style.display = "none";
      tt.classList.remove("sticky");
      frozen = false;
      ttSource = null;
    }
    function scheduleHide() { clearHide(); hideTimer = setTimeout(hideTip, HIDE_MS); }
    function freezeTip() { frozen = true; tt.classList.add("sticky"); }
    function armIdle() { clearIdle(); idleTimer = setTimeout(freezeTip, IDLE_MS); }
    function placeTip(e) {
      const x = e.clientX + OFFSET_X, y = e.clientY + OFFSET_Y;
      const w = tt.offsetWidth || 420;
      tt.style.left = (x + w > window.innerWidth ? e.clientX - w - 4 : x) + "px";
      tt.style.top  = Math.max(8, y) + "px";
    }
    function showTip(md, source, e) {
      if (ttSource !== source) {     // new target — render, reposition, re-arm
        ttSource = source;
        tt.innerHTML = renderMd(md);
        tt.classList.remove("sticky");
        frozen = false;
        tt.style.display = "block";
        placeTip(e);
      }
      clearHide();
      if (!frozen) armIdle();
    }

    // Keep the panel alive and frozen while the cursor is inside it.
    tt.addEventListener("mouseenter", function() { clearHide(); freezeTip(); });
    tt.addEventListener("mouseleave", hideTip);

    function lookupEdgeMd(titleKey) {
      if (edgeDescs[titleKey]) return edgeDescs[titleKey];
      let colon = titleKey.lastIndexOf(":");
      if (colon > 0 && edgeDescs[titleKey.slice(0, colon)]) {
        return edgeDescs[titleKey.slice(0, colon)];
      }
      const normalized = titleKey.replace(/^([^:]+):[a-z]+->/, "$1->");
      if (edgeDescs[normalized]) return edgeDescs[normalized];
      colon = normalized.lastIndexOf(":");
      if (colon > 0 && edgeDescs[normalized.slice(0, colon)]) {
        return edgeDescs[normalized.slice(0, colon)];
      }
      return null;
    }

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

    document.querySelectorAll("#svg-wrap svg g.edge").forEach(function(g) {
      const tel = g.querySelector(":scope > title");
      if (!tel) return;
      const md = lookupEdgeMd(tel.textContent.trim());
      if (md) { g._md = md; g.style.cursor = "help"; }
      tel.remove();
    });

    // Remove native Graphviz tooltips; keep label hyperlinks (new tab + styling).
    document.querySelectorAll("#svg-wrap svg a").forEach(function(a) {
      if (a.hasAttribute("xlink:href") || a.hasAttribute("href")) {
        a.setAttribute("target", "_blank");
        a.setAttribute("rel", "noopener noreferrer");
      }
      a.removeAttribute("xlink:title");
      a.removeAttribute("title");
    });

    // Optional header tooltip — shown when hovering the page title.
    const titleTt = %%TITLE_TOOLTIP%%;
    if (titleTt) {
      const hdrEl = document.getElementById("hdr-title");
      if (hdrEl) {
        hdrEl.style.cursor = "help";
        hdrEl.addEventListener("mouseover", function(e) { showTip(titleTt, "title", e); });
        hdrEl.addEventListener("mousemove", function(e) {
          if (!frozen) { placeTip(e); armIdle(); }
        });
        hdrEl.addEventListener("mouseleave", scheduleHide);
      }
    }

    // On hover: find the innermost group with a description and show tooltip.
    const svgWrap = document.getElementById("svg-wrap");

    svgWrap.addEventListener("mouseover", function(e) {
      let el = e.target;
      while (el && el.id !== "svg-wrap") {
        if (el._md) { showTip(el._md, el, e); return; }
        el = el.parentElement;
      }
      // Not over a described element: hide after a grace period so the cursor
      // can still reach the panel across the offset gap.
      scheduleHide();
    });

    svgWrap.addEventListener("mousemove", function(e) {
      if (tt.style.display === "none" || frozen) return;
      placeTip(e);
      armIdle();
    });

    svgWrap.addEventListener("mouseleave", scheduleHide);
  </script>
</body>
</html>
"""
