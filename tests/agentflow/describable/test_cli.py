"""Tests for Describable.run_argparse() and AgentApp.cli() unified CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from agentflow.app import AgentApp
from agentflow.describable.describable import Describable


class _RunnableDescribable(Describable):
    """Minimal runnable describable for CLI tests."""

    def __init__(self) -> None:
        super().__init__()
        self.run_called = False
        self.last_question: str | None = None

    def run(self, question: str | None = None) -> str | None:  # type: ignore[override]
        self.run_called = True
        self.last_question = question
        return f"answer:{question!r}"

    def get_description_dict(self) -> dict:
        return {"name": self.name, "kind": "test"}

    def get_description_markdown(self) -> str:
        return "# test\n"

    def get_description_html(self) -> str:
        return "<p>test</p>"

    def get_graph_dot(self) -> str:
        return "digraph G { }"

    def get_graph_interactive_svg(self) -> str:
        return "<svg></svg>"

    def get_graph_html(self, title: str = "", title_tooltip: str = "") -> str:
        return "<html>graph</html>"


@pytest.fixture
def runnable() -> _RunnableDescribable:
    return _RunnableDescribable()


def test_no_args_prints_help_and_does_not_run(
    runnable: _RunnableDescribable,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch.object(sys, "argv", ["script.py"]):
        with pytest.raises(SystemExit) as exc:
            runnable.run_argparse(doc="Test CLI", name="__main__")
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out
    assert "describe" in captured.out
    assert "graph" in captured.out
    assert "run" in captured.out
    assert "commands (full syntax):" in captured.out
    assert "--format" in captured.out
    assert "QUESTION" in captured.out
    assert not runnable.run_called


def test_root_help_includes_full_subcommand_grammar(
    runnable: _RunnableDescribable,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch.object(sys, "argv", ["script.py", "-h"]):
        with pytest.raises(SystemExit) as exc:
            runnable.run_argparse(doc="Test CLI", name="__main__")
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "commands (full syntax):" in out
    assert "    positional arguments:" in out
    assert "    options:" in out
    assert "--browser" in out


def test_run_invokes_computation(
    runnable: _RunnableDescribable,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch.object(sys, "argv", ["script.py", "run", "hello", "world"]):
        runnable.run_argparse(doc="Test CLI", name="__main__")
    assert runnable.run_called
    assert runnable.last_question == "hello world"
    assert "answer:'hello world'" in capsys.readouterr().out


def test_gui_branch_calls_cli_start_gui(
    runnable: _RunnableDescribable,
) -> None:
    with patch.object(
        runnable,
        "_cli_start_gui",
        autospec=True,
    ) as mock_gui:
        with patch.object(sys, "argv", ["script.py", "gui", "--host", "0.0.0.0", "--port", "9000"]):
            runnable.run_argparse(doc="Test CLI", name="__main__", include_gui=True)
    mock_gui.assert_called_once_with(host="0.0.0.0", port=9000, no_browser=False)


def test_syntax_error_in_graph_shows_graph_help(
    runnable: _RunnableDescribable,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch.object(sys, "argv", ["script.py", "graph", "--format", "bogus"]):
        with pytest.raises(SystemExit) as exc:
            runnable.run_argparse(doc="Test CLI", name="__main__")
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "graph" in captured.err
    assert "--format" in captured.err
    assert not runnable.run_called


def test_describe_format_json_writes_output_file(
    runnable: _RunnableDescribable,
    tmp_path: Path,
) -> None:
    out = tmp_path / "desc.json"
    with patch.object(sys, "argv", [
        "script.py",
        "describe",
        "--format",
        "json",
        "-o",
        str(out),
    ]):
        runnable.run_argparse(doc="Test CLI", name="__main__")
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["kind"] == "test"


def test_graph_browser_opens_browser(
    runnable: _RunnableDescribable,
) -> None:
    with patch.object(
        runnable,
        "open_graph_browser",
        autospec=True,
    ) as mock_open:
        with patch.object(sys, "argv", ["script.py", "graph", "--browser"]):
            runnable.run_argparse(doc="Test CLI", name="__main__")
    mock_open.assert_called_once()


def test_agent_app_cli_includes_gui(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = AgentApp(doc="Agent test")
    with patch.object(sys, "argv", ["script.py"]):
        with pytest.raises(SystemExit):
            app.cli(doc="Agent test", name="__main__")
    assert "gui" in capsys.readouterr().out


def test_agent_app_gui_delegates_to_cli_start_gui() -> None:
    app = AgentApp(doc="Agent test")
    with patch.object(app, "_cli_start_gui", autospec=True) as mock_gui:
        with patch.object(sys, "argv", ["script.py", "gui", "--no-browser"]):
            app.cli(doc="Agent test", name="__main__")
    mock_gui.assert_called_once_with(host="127.0.0.1", port=None, no_browser=True)


def test_describe_default_markdown_to_stdout(
    runnable: _RunnableDescribable,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch.object(sys, "argv", ["script.py", "describe"]):
        runnable.run_argparse(doc="Test CLI", name="__main__")
    assert "# test" in capsys.readouterr().out


def test_graph_default_html_to_stdout(
    runnable: _RunnableDescribable,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch.object(sys, "argv", ["script.py", "graph"]):
        runnable.run_argparse(doc="Test CLI", name="__main__")
    assert "<html>graph</html>" in capsys.readouterr().out


def test_unknown_top_level_command_shows_help(
    runnable: _RunnableDescribable,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch.object(sys, "argv", ["script.py", "not-a-command"]):
        with pytest.raises(SystemExit) as exc:
            runnable.run_argparse(doc="Test CLI", name="__main__")
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "describe" in captured.err
