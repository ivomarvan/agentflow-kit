"""Graph data structures for describing object composition.

``Vertex``  — a labelled node, optionally containing child vertices.
``Edge``    — a directed or undirected relationship between two vertices.
``Graph``   — the full graph: one root vertex and a list of edges.

These types are intentionally plain dataclasses with no rendering logic.
Conversion to Graphviz DOT, SVG, HTML, or other formats will be implemented
as separate methods/functions once the structure is stable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Vertex:
    """A labelled node in the composition graph.

    Args:
        id: Unique path-based identifier, e.g. ``"ToolAgent.connector.config"``.
        label: Display label — typically the class name.
        description: Scalar attribute dict from ``get_description_item_dict()``.
        children: Directly owned nested vertices (containment / composition).
        attributes: Reserved for future extensions (state machine info, styling, …).
        source_file: Absolute path to the Python source file defining this vertex's class.
        source_line: 1-based line number of the class definition in ``source_file``.
    """

    id: str
    label: str
    description: dict[str, Any]
    children: list[Vertex] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    source_file: str = ""
    source_line: int = 0


@dataclass
class Edge:
    """A relationship between two vertices.

    Args:
        from_id: Source vertex ID.
        to_id: Target vertex ID.
        directed: When ``True``, the edge is directed from → to.
        label: Optional human-readable label on the edge.
        attributes: Additional metadata (weight, style, …).
    """

    from_id: str
    to_id: str
    directed: bool = True
    label: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Graph:
    """The composition graph of a Describable object tree.

    The base ``Describable.get_graph()`` produces only the vertex tree from
    introspection — no edges.  Subclasses add semantic edges (data-flow,
    call relationships, state transitions, …) by overriding ``get_graph()``.

    Args:
        root: The top-level vertex of the composition tree.
        edges: Explicit relationships between vertices (empty by default).
    """

    root: Vertex
    edges: list[Edge] = field(default_factory=list)
