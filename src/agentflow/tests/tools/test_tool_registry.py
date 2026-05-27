"""Unit tests for ToolRegistry — registration, dispatch, error handling."""

from __future__ import annotations

import pytest
from git_root_to_syspath import agr

agr()

from src.agentflow.tools.Tool import ToolBase, param_desc
from src.agentflow.tools.ToolRegistry import ToolRegistry


# ---------------------------------------------------------------------------
# Fixture tools
# ---------------------------------------------------------------------------


class Echo(ToolBase):
    """Echo the input text back."""

    @param_desc(text="Text to echo.")
    def execute(self, text: str) -> str:
        return text


class Add(ToolBase):
    """Add two integers."""

    def execute(self, a: int, b: int) -> str:  # type: ignore[override]
        return str(a + b)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRegistration:
    def test_register_adds_tool(self) -> None:
        reg = ToolRegistry()
        reg.register(Echo())
        assert "echo" in reg

    def test_duplicate_registration_raises_value_error(self) -> None:
        reg = ToolRegistry()
        reg.register(Echo())
        with pytest.raises(ValueError, match="already registered"):
            reg.register(Echo())

    def test_unregister_removes_tool(self) -> None:
        reg = ToolRegistry()
        reg.register(Echo())
        reg.unregister("echo")
        assert "echo" not in reg

    def test_unregister_unknown_raises_key_error(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(KeyError):
            reg.unregister("nonexistent")

    def test_len_reflects_registered_count(self) -> None:
        reg = ToolRegistry()
        assert len(reg) == 0
        reg.register(Echo())
        reg.register(Add())
        assert len(reg) == 2

    def test_names_returns_sorted_list(self) -> None:
        reg = ToolRegistry()
        reg.register(Add())
        reg.register(Echo())
        assert reg.names() == ["add", "echo"]


# ---------------------------------------------------------------------------
# schemas()
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_schemas_returns_list_of_dicts() -> None:
    reg = ToolRegistry()
    reg.register(Echo())
    schemas = reg.schemas()
    assert len(schemas) == 1
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "echo"


# ---------------------------------------------------------------------------
# execute()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecute:
    def test_execute_calls_tool_and_returns_string(self) -> None:
        reg = ToolRegistry()
        reg.register(Echo())
        result = reg.execute("echo", '{"text": "hello"}')
        assert result == "hello"

    def test_execute_with_multiple_args(self) -> None:
        reg = ToolRegistry()
        reg.register(Add())
        result = reg.execute("add", '{"a": 3, "b": 4}')
        assert result == "7"

    def test_execute_empty_args_json_treated_as_empty_dict(self) -> None:
        class _NoArgs(ToolBase):
            """Tool with no args."""
            def execute(self) -> str:  # type: ignore[override]
                return "ok"

        reg = ToolRegistry()
        reg.register(_NoArgs())
        assert reg.execute("no_args", "") == "ok"
        assert reg.execute("no_args", "  ") == "ok"

    def test_execute_unknown_tool_raises_key_error(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(KeyError, match="unknown_tool"):
            reg.execute("unknown_tool", "{}")

    def test_execute_invalid_json_uses_empty_args(self) -> None:
        class _NoArgs(ToolBase):
            """Tool with no args."""
            def execute(self) -> str:  # type: ignore[override]
                return "ok"

        reg = ToolRegistry()
        reg.register(_NoArgs())
        # Invalid JSON: registry logs warning and falls back to {}
        assert reg.execute("no_args", "not valid json {{") == "ok"

    def test_execute_propagates_tool_exception(self) -> None:
        class _Boom(ToolBase):
            """Always raises."""
            def execute(self) -> str:  # type: ignore[override]
                raise RuntimeError("boom")

        reg = ToolRegistry()
        reg.register(_Boom())
        with pytest.raises(RuntimeError, match="boom"):
            reg.execute("boom", "{}")


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_returns_tool_instance() -> None:
    reg = ToolRegistry()
    tool = Echo()
    reg.register(tool)
    assert reg.get("echo") is tool


@pytest.mark.unit
def test_get_returns_none_for_unknown() -> None:
    reg = ToolRegistry()
    assert reg.get("missing") is None
