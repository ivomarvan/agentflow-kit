"""Unit tests for the dot2html CLI and DOT-to-HTML renderer."""

from __future__ import annotations

import re
from pathlib import Path

from agentflow.describable.graph_renderer import GraphRenderer
from tools.dot2html import main

_SAMPLE_DOT = """\
digraph {
  subgraph cluster_App {
    label="App"
    tooltip="App\\nRoot application."
    N [label="N" tooltip="N\\nLeaf node."]
  }
  N -> _a_App_context_tools [style=dashed, dir=none, tailport=e, headport=w, tooltip="N-Tools: default"]
}
"""


def test_extract_tooltip_descs_from_dot() -> None:
    """Tooltip attributes in DOT are mapped to HTML description keys."""
    descs, edge_descs = GraphRenderer._extract_tooltip_descs_from_dot(_SAMPLE_DOT)

    assert descs["cluster_App"] == "## App\nRoot application."
    assert descs["N"] == "## N\nLeaf node."
    assert edge_descs["N:e->_a_App_context_tools:w"] == "## N-Tools: default"


def test_dot_to_html_uses_html_template_and_svg() -> None:
    """dot_to_html produces the same HTML shell as ``graph --format html``."""
    html = GraphRenderer.dot_to_html(_SAMPLE_DOT, title="Test")

    assert "<title>Test</title>" in html
    assert 'id="svg-wrap"' in html
    assert "<svg" in html
    assert "edgeDescs" in html


def test_dot2html_cli_writes_output(tmp_path: Path) -> None:
    """CLI reads DOT from -i and writes HTML to -o."""
    dot_path = tmp_path / "g.dot"
    html_path = tmp_path / "g.html"
    dot_path.write_text(_SAMPLE_DOT, encoding="utf-8")

    exit_code = main(["-i", str(dot_path), "-o", str(html_path), "--title", "CLI"])

    assert exit_code == 0
    content = html_path.read_text(encoding="utf-8")
    assert re.search(r"<title>CLI</title>", content)
