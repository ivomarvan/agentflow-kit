"""Unit tests for graph tooltip rendering in GraphRenderer."""

from __future__ import annotations

import re
from pathlib import Path

import agentflow
from agentflow.describable.describable import Describable
from agentflow.describable.graph import Graph, Vertex
from agentflow.describable.graph_renderer import GraphRenderer


class _TooltipSampleApp(Describable):
    """Sample application for graph tooltip tests."""


def _agentflow_source_file(relative: str) -> str:
    """Return an absolute path inside the installed agentflow package."""
    return str((Path(agentflow.__file__).resolve().parent / relative).resolve())


def test_skip_description_key_omits_redundant_name() -> None:
    """Redundant name matching the label must not appear in tooltips."""
    vertex = Vertex(
        id="Sample",
        label="Sample",
        description={"_type": "Sample", "name": "Sample", "description": "Hello"},
    )
    assert GraphRenderer._skip_description_key(vertex, "name", "Sample") is True
    assert GraphRenderer._skip_description_key(vertex, "name", "Other") is False
    assert GraphRenderer._skip_description_key(vertex, "description", "Hello") is False


def test_is_library_vertex_uses_agentflow_package_root() -> None:
    """Library detection follows the installed package tree, not a fixed repo path."""
    library = Vertex(
        id="Lib",
        label="Lib",
        description={},
        source_file=_agentflow_source_file("llm/cache/LlmFileCache.py"),
    )
    user = Vertex(
        id="User",
        label="User",
        description={},
        source_file="/tmp/examples/my_app.py",
    )
    assert GraphRenderer._is_library_vertex(library) is True
    assert GraphRenderer._is_library_vertex(user) is False


def test_truncate_library_description_first_sentence() -> None:
    """Library tooltips keep the first sentence and append ellipsis when truncated."""
    long = "First sentence here. Second sentence with more detail.\n\nThird paragraph."
    assert GraphRenderer._truncate_library_description(long) == "First sentence here. ..."


def test_truncate_library_description_blank_line() -> None:
    """Library tooltips stop at the first blank line when no period appears earlier."""
    text = "Opening paragraph without a period\n\nSecond paragraph."
    assert GraphRenderer._truncate_library_description(text) == "Opening paragraph without a period ..."


def test_truncate_library_description_no_ellipsis_when_short() -> None:
    """A single-sentence library description must not receive a trailing ellipsis."""
    assert GraphRenderer._truncate_library_description("Only one sentence.") == "Only one sentence."


def test_vertex_to_md_user_description_without_header() -> None:
    """User tooltips show the full description without a description field label."""
    vertex = Vertex(
        id="Sample",
        label="Sample",
        description={
            "_type": "Sample",
            "name": "Sample",
            "description": "First sentence. Second sentence.",
            "cache_file": "/tmp/cache.jsonl",
        },
        source_file="/tmp/sample_app.py",
        source_line=42,
    )
    markdown = GraphRenderer._vertex_to_md(vertex)

    assert "**name**" not in markdown
    assert "**description**" not in markdown
    assert "First sentence. Second sentence." in markdown
    assert "  - **cache_file**: /tmp/cache.jsonl" in markdown
    assert markdown.startswith("## Sample")
    assert "file://" not in markdown


def test_vertex_to_md_library_description_truncated() -> None:
    """Library tooltips shorten the body description to one sentence."""
    vertex = Vertex(
        id="LlmFileCache",
        label="LlmFileCache",
        description={
            "description": "First sentence here. Second sentence.",
            "cache_file": "/tmp/cache.jsonl",
        },
        source_file=_agentflow_source_file("llm/cache/LlmFileCache.py"),
        source_line=60,
    )
    markdown = GraphRenderer._vertex_to_md(vertex)

    assert "First sentence here. ..." in markdown
    assert "Second sentence." not in markdown
    assert "  - **cache_file**: /tmp/cache.jsonl" in markdown


def test_vertex_to_dot_tooltip_user_description_without_header() -> None:
    """Plain-text DOT tooltips omit the description field label for user objects."""
    vertex = Vertex(
        id="Sample",
        label="Sample",
        description={
            "_type": "Sample",
            "name": "Sample",
            "description": "Hello",
            "size": 2,
        },
        source_file="/tmp/sample_app.py",
        source_line=42,
    )
    tooltip = GraphRenderer._vertex_to_dot_tooltip(vertex)
    decoded = tooltip.replace("\\n", "\n")

    assert "name:" not in decoded
    assert "description: Hello" not in decoded
    assert "\nHello\n" in decoded
    assert "  size: 2" in decoded


def test_vertex_to_dot_tooltip_library_description_truncated() -> None:
    """Plain-text DOT tooltips shorten library descriptions to one sentence."""
    vertex = Vertex(
        id="LlmFileCache",
        label="LlmFileCache",
        description={
            "description": "First sentence here. More detail follows.",
            "max_size": 500,
        },
        source_file=_agentflow_source_file("llm/cache/LlmFileCache.py"),
        source_line=60,
    )
    decoded = GraphRenderer._vertex_to_dot_tooltip(vertex).replace("\\n", "\n")

    assert "description:" not in decoded
    assert "First sentence here. ..." in decoded
    assert "More detail follows." not in decoded
    assert "  max_size: 500" in decoded


def test_build_vertex_populates_source_location() -> None:
    """Vertices built from Describable instances carry class source metadata."""
    app = _TooltipSampleApp()
    vertex = app._build_vertex("_TooltipSampleApp")

    assert vertex.source_file.endswith("test_graph_renderer_tooltips.py")
    assert vertex.source_line > 0
    markdown = GraphRenderer._vertex_to_md(vertex)
    assert "file://" not in markdown
    assert "**name**" not in markdown


def test_to_dot_adds_url_for_source_location() -> None:
    """Graphviz URL attribute on labels is emitted for all graph render paths."""
    vertex = Vertex(
        id="Sample",
        label="Sample",
        description={"description": "Hello"},
        source_file="/tmp/sample_app.py",
        source_line=42,
    )
    dot = GraphRenderer.to_dot(Graph(root=vertex))
    assert 'URL="file:///tmp/sample_app.py#L42"' in dot


def test_to_svg_embeds_label_hyperlink() -> None:
    """Raw SVG from Graphviz includes xlink:href on vertex labels."""
    vertex = Vertex(
        id="Sample",
        label="Sample",
        description={"description": "Hello"},
        source_file="/tmp/sample_app.py",
        source_line=42,
    )
    svg = GraphRenderer.to_svg(Graph(root=vertex))
    assert re.search(r'xlink:href="file:///tmp/sample_app\.py#L42"', svg)
    assert 'target="_blank"' in svg
    assert "a text { fill: #1565c0" in svg


def test_to_html_embeds_label_hyperlink() -> None:
    """Standalone HTML embeds the same clickable SVG labels."""
    vertex = Vertex(
        id="Sample",
        label="Sample",
        description={"description": "Hello"},
        source_file="/tmp/sample_app.py",
        source_line=42,
    )
    html = GraphRenderer.to_html(Graph(root=vertex), title="Sample")
    assert 'xlink:href="file:///tmp/sample_app.py#L42"' in html
    assert 'target="_blank"' in html
    assert "#svg-wrap svg a text" in html
    assert "file://" not in html.split("const descs =", 1)[1].split(";", 1)[0]


def test_to_html_with_title_false_omits_header() -> None:
    """Embedded GUI graph HTML has no duplicate page header bar."""
    vertex = Vertex(id="Sample", label="Sample", description={"description": "Hello"})
    html = GraphRenderer.to_html(Graph(root=vertex), title="Sample", with_title=False)
    assert 'id="header"' not in html
    assert "<title>Sample</title>" in html


def test_to_html_with_title_true_includes_header() -> None:
    """CLI/browser graph HTML includes the page header bar by default."""
    vertex = Vertex(id="Sample", label="Sample", description={"description": "Hello"})
    html = GraphRenderer.to_html(Graph(root=vertex), title="Sample")
    assert 'id="header"' in html
    assert 'id="hdr-title"' in html
