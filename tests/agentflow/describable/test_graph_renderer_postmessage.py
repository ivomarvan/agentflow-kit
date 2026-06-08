"""Unit tests for postMessage graph↔params linking in GraphRenderer HTML."""

from __future__ import annotations

from agentflow.describable.graph import Graph, Vertex
from agentflow.describable.graph_renderer import GraphRenderer


def _sample_graph() -> Graph:
    """Minimal graph with one vertex for HTML generation tests."""
    return Graph(
        root=Vertex(
            id="SampleVertex",
            label="SampleVertex",
            description={"description": "Hello"},
        ),
    )


def test_html_contains_postmessage_click_handler() -> None:
    """Generated HTML posts node clicks to the parent window."""
    html = GraphRenderer.to_html(_sample_graph(), with_title=False)
    assert "af:nodeClicked" in html
    assert "window.parent.postMessage" in html


def test_html_contains_message_listener() -> None:
    """Generated HTML listens for highlight and tooltip update messages."""
    html = GraphRenderer.to_html(_sample_graph(), with_title=False)
    assert "af:highlightNode" in html
    assert "af:updateTooltip" in html


def test_html_contains_af_selected_css() -> None:
    """Generated HTML includes amber stroke styling for selected nodes."""
    html = GraphRenderer.to_html(_sample_graph(), with_title=False)
    assert "af-selected" in html
    assert "#f59e0b" in html


def test_html_sets_g_key_on_nodes() -> None:
    """Node key is preserved on SVG groups for postMessage routing."""
    html = GraphRenderer.to_html(_sample_graph(), with_title=False)
    assert "g._key = key" in html
