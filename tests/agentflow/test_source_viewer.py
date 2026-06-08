"""Tests for GUI source viewer (path policy and Pygments HTML)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentflow.gui.source_viewer import (
    allowed_source_roots,
    render_source_html,
    resolve_source_path,
)


def test_allowed_source_roots_includes_cwd() -> None:
    """Current working directory is always an allowed source root."""
    roots = allowed_source_roots()
    assert Path.cwd().resolve() in roots


def test_resolve_source_path_allows_repo_test_file() -> None:
    """A test module under the project tree is readable."""
    path = Path(__file__).resolve()
    assert resolve_source_path(str(path)) == path


def test_resolve_source_path_rejects_outside_roots(tmp_path: Path) -> None:
    """Paths outside allowed roots must not be served."""
    secret = tmp_path / "secret.py"
    secret.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(PermissionError):
        resolve_source_path(str(secret))


def test_resolve_source_path_rejects_non_python(tmp_path: Path) -> None:
    """Only .py files are accepted."""
    text_file = tmp_path / "notes.txt"
    text_file.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match="Only .py"):
        resolve_source_path(str(text_file))


def test_render_source_html_highlights_python_and_line() -> None:
    """Rendered HTML contains Pygments spans and scroll anchor for the target line."""
    path = Path(__file__).resolve()
    html = render_source_html(path, line=1)
    assert "<!DOCTYPE html>" in html
    assert "pygments" in html.lower() or "highlight" in html
    assert "L1" in html
    assert str(path) in html
    assert "scrollIntoView" in html
