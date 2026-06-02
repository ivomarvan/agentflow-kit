"""Unit tests for graph edge rendering in GraphRenderer."""

from __future__ import annotations

import re

from agentflow.describable.graph import Edge, Graph, Vertex
from agentflow.describable.graph_renderer import GraphRenderer


def test_usage_edge_is_undirected_without_visible_label() -> None:
    """Usage edges are undirected; summary text goes to tooltips, not labels."""
    edge_descs: dict[str, str] = {}
    edge = Edge(
        from_id="App.StateGraph.LlmCall",
        to_id="App.context.default",
        label="LlmCall-OpenAiConnector-gpt-4o-mini",
        attributes={"usage": True, "usage_type": "llm"},
    )
    dot_line = GraphRenderer._edge_to_dot(edge, edge_descs)

    assert " -> _a_App_context_default [" in dot_line
    assert "dir=none" in dot_line
    assert "arrowsize=0" in dot_line
    assert "arrowhead=none" not in dot_line
    assert "arrowtail=none" not in dot_line
    assert "headport=w" in dot_line
    assert "tailport=e" in dot_line
    assert "constraint=false" not in dot_line
    assert 'label="' not in dot_line
    assert 'tooltip="LlmCall-OpenAiConnector-gpt-4o-mini"' in dot_line
    assert edge_descs["App_StateGraph_LlmCall:e->_a_App_context_default:w"] == (
        "## LlmCall-OpenAiConnector-gpt-4o-mini"
    )
    assert edge_descs["App_StateGraph_LlmCall->_a_App_context_default:w"] == (
        "## LlmCall-OpenAiConnector-gpt-4o-mini"
    )


def test_usage_edge_dot_avoids_graphviz_arrow_port_conflict() -> None:
    """Usage edges must not combine arrowhead/tail=none with compass headport."""
    edge_descs: dict[str, str] = {}
    edge = Edge(
        from_id="App.graph.Judge",
        to_id="App.context.quality",
        label="Judge-OpenAiConnector-gpt-4o",
        attributes={"usage": True, "usage_type": "llm"},
    )
    dot_line = GraphRenderer._edge_to_dot(edge, edge_descs)

    assert "headport=w" in dot_line
    assert "arrowhead=none" not in dot_line
    assert "arrowtail=none" not in dot_line


def test_strip_usage_edge_arrowheads_removes_dashed_polygons() -> None:
    """Post-processing strips arrow polygons from purple/green dashed edges only."""
    svg = """
    <g id="a_edge1" class="edge">
      <path fill="none" stroke="#7b2fa8" stroke-dasharray="5,2" d="M0,0L1,1"/>
      <polygon fill="#7b2fa8" stroke="#7b2fa8" points="0,0 1,1 2,2"/>
    </g>
    <g id="edge2" class="edge">
      <path fill="none" stroke="#666666" d="M0,0L1,1"/>
      <polygon fill="#666666" stroke="#666666" points="0,0 1,1 2,2"/>
    </g>
    """
    cleaned = GraphRenderer._strip_usage_edge_arrowheads(svg)
    assert "<polygon" not in cleaned.split("a_edge1")[1].split("</g>")[0]
    assert cleaned.count("<polygon") == 1


def test_parallel_edge_remains_directed() -> None:
    """Parallel fan-out edges stay directed with dashed styling."""
    edge = Edge(
        from_id="App.StateGraph.Fork",
        to_id="App.StateGraph.BranchA",
        attributes={"parallel": True},
    )
    dot_line = GraphRenderer._edge_to_dot(edge)

    assert " -> " in dot_line
    assert "style=dashed" in dot_line
    assert "dir=none" not in dot_line


def test_build_dot_populates_usage_edge_tooltips() -> None:
    """Usage edge summaries are available for HTML/SVG edge hover tooltips."""
    edge = Edge(
        from_id="App.graph.Worker",
        to_id="App.context.tools",
        label="Worker-Tools: default",
        attributes={"usage": True, "usage_type": "tools"},
    )
    graph = Graph(
        root=Vertex(id="App", label="App", description={}),
        edges=[edge],
    )
    _, _, edge_descs = GraphRenderer._build_dot(graph)

    assert edge_descs["App_graph_Worker:e->_a_App_context_tools:w"] == (
        "## Worker-Tools: default"
    )


def test_agentapp_stacks_stategraph_above_context() -> None:
    """AgentApp uses invisible edges so StateGraph sits above Context."""
    root = Vertex(
        id="App",
        label="AgentApp",
        description={},
        children=[
            Vertex(
                id="App.context",
                label="Context",
                description={},
                children=[
                    Vertex(id="App.context.tools", label="ToolRegistry", description={}),
                ],
            ),
            Vertex(
                id="App.graph",
                label="StateGraph",
                description={},
                children=[
                    Vertex(id="App.graph.start", label="Start", description={}),
                ],
            ),
        ],
    )
    dot, _, _ = GraphRenderer._build_dot(Graph(root=root))

    assert "rankdir=TB" in dot.split("subgraph cluster_App {", 1)[0]
    assert re.search(r"_a_App_graph -> _a_App_context \[style=invis", dot)
    assert 'subgraph cluster_App_graph' in dot
    assert 'subgraph cluster_App_context' in dot


def test_context_cluster_uses_vertical_rankdir() -> None:
    """Context cluster stacks LLM/tool sub-clusters top-to-bottom."""
    root = Vertex(
        id="App",
        label="AgentApp",
        description={},
        children=[
            Vertex(
                id="App.graph",
                label="StateGraph",
                description={},
                children=[Vertex(id="App.graph.n", label="N", description={})],
            ),
            Vertex(
                id="App.context",
                label="Context",
                description={},
                children=[
                    Vertex(
                        id="App.context.a",
                        label="LlmConnector",
                        description={},
                        children=[Vertex(id="App.context.a.c", label="C", description={})],
                    ),
                    Vertex(
                        id="App.context.b",
                        label="ToolRegistry",
                        description={},
                        children=[Vertex(id="App.context.b.t", label="T", description={})],
                    ),
                ],
            ),
        ],
    )
    dot, _, _ = GraphRenderer._build_dot(Graph(root=root))

    assert re.search(r"subgraph cluster_App_context \{[^}]*rankdir=TB", dot, re.DOTALL)
    assert re.search(r"_a_App_context_a -> _a_App_context_b \[style=invis", dot)


def test_usage_port_cluster_aligns_anchor_to_middle_leaf() -> None:
    """LlmConnector clusters place the usage anchor beside the middle leaf."""
    root = Vertex(
        id="App",
        label="AgentApp",
        description={},
        children=[
            Vertex(
                id="App.context",
                label="Context",
                description={},
                children=[
                    Vertex(
                        id="App.context.economy",
                        label="LlmConnector",
                        description={},
                        children=[
                            Vertex(id="App.context.economy.cache", label="LlmFileCache", description={}),
                            Vertex(id="App.context.economy.backend", label="OpenAiConnector", description={}),
                        ],
                    ),
                ],
            ),
        ],
    )
    dot, _, _ = GraphRenderer._build_dot(Graph(root=root))

    assert re.search(
        r"\{ rank=same; _a_App_context_economy; App_context_economy_backend; \}",
        dot,
    )


def test_usage_port_cluster_declares_anchor_before_children() -> None:
    """Usage-port anchor is emitted before visible children inside the cluster."""
    root = Vertex(
        id="App",
        label="AgentApp",
        description={},
        children=[
            Vertex(
                id="App.context",
                label="Context",
                description={},
                children=[
                    Vertex(
                        id="App.context.economy",
                        label="LlmConnector",
                        description={},
                        children=[
                            Vertex(id="App.context.economy.cache", label="LlmFileCache", description={}),
                            Vertex(id="App.context.economy.backend", label="OpenAiConnector", description={}),
                        ],
                    ),
                ],
            ),
        ],
    )
    dot, _, _ = GraphRenderer._build_dot(Graph(root=root))
    economy_block = dot.split("subgraph cluster_App_context_economy", 1)[1].split("\n    }", 1)[0]

    assert economy_block.index("_a_App_context_economy") < economy_block.index(
        "App_context_economy_cache"
    )


def test_stategraph_cluster_uses_horizontal_rankdir() -> None:
    """StateGraph keeps left-to-right flow for state-machine vertices."""
    root = Vertex(
        id="App",
        label="AgentApp",
        description={},
        children=[
            Vertex(
                id="App.graph",
                label="StateGraph",
                description={},
                children=[Vertex(id="App.graph.n", label="N", description={})],
            ),
        ],
    )
    dot, _, _ = GraphRenderer._build_dot(Graph(root=root))
    graph_block = dot.split("subgraph cluster_App_graph", 1)[1].split("\n    }", 1)[0]

    assert "rankdir=LR" in graph_block
    assert graph_block.index("App_graph_n") < graph_block.index("_a_App_graph")
