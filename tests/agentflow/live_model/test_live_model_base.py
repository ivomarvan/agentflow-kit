"""Unit tests for LiveModel base class and @action adapter."""

from __future__ import annotations

from typing import Annotated, Literal
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, ConfigDict, Field

from agentflow.live_model import LiveModel, action
from agentflow.live_model._action_adapter import _ActionToolAdapter


class _DemoState(BaseModel):
    model_config = ConfigDict(frozen=False)
    count: int = 0


class _DemoModel(LiveModel):
    def __init__(self) -> None:
        self._state = _DemoState()

    @property
    def state(self) -> _DemoState:
        return self._state

    def helper(self) -> str:
        """Not an action."""
        return "helper"

    @action
    def increment(
        self,
        step: Annotated[int, Field(description="Step size", ge=1)] = 1,
    ) -> str:
        """Add step to the counter."""
        self._state.count += step
        return f"count={self._state.count}"

    @action
    def set_mode(
        self,
        mode: Annotated[
            Literal["a", "b"],
            Field(description="Mode", json_schema_extra={"x-widget": "select"}),
        ],
    ) -> str:
        """Set operating mode."""
        return f"mode={mode}"

    @action
    def boom(self) -> str:
        """Always fails."""
        raise RuntimeError("kaboom")

    @action
    def book(
        self,
        when: Annotated[str, Field(json_schema_extra={"x-widget": "date"})],
    ) -> str:
        """Book on a date."""
        return f"booked {when}"


@pytest.mark.unit
def test_action_decorator_sets_flag() -> None:
    @action
    def sample() -> None:
        pass

    assert getattr(sample, "_is_action", False) is True


@pytest.mark.unit
def test_tools_discovers_action_methods() -> None:
    model = _DemoModel()
    tools = model.tools()
    assert len(tools) == 4
    names = {t.name for t in tools}
    assert names == {"increment", "set_mode", "boom", "book"}


@pytest.mark.unit
def test_tools_ignores_non_action_methods() -> None:
    model = _DemoModel()
    assert all(t.name != "helper" for t in model.tools())


@pytest.mark.unit
def test_tool_registry_wraps_all_tools() -> None:
    registry = _DemoModel().tool_registry()
    assert len(registry.tools) == 4


@pytest.mark.unit
def test_adapter_name_equals_method_name() -> None:
    adapter = next(t for t in _DemoModel().tools() if t.name == "increment")
    assert adapter.name == "increment"


@pytest.mark.unit
def test_adapter_description_from_docstring() -> None:
    adapter = next(t for t in _DemoModel().tools() if t.name == "increment")
    assert adapter.description == "Add step to the counter."


@pytest.mark.unit
def test_adapter_execute_returns_string() -> None:
    adapter = next(t for t in _DemoModel().tools() if t.name == "increment")
    result = adapter.execute(step=1)
    assert result == "count=1"


@pytest.mark.unit
def test_adapter_execute_catches_exception() -> None:
    adapter = next(t for t in _DemoModel().tools() if t.name == "boom")
    result = adapter.execute()
    assert "Error:" in result
    assert "kaboom" in result


@pytest.mark.unit
def test_adapter_schema_str_param() -> None:
    adapter = next(t for t in _DemoModel().tools() if t.name == "book")
    schema = adapter.parameters_schema()
    assert schema["properties"]["when"]["type"] == "string"


@pytest.mark.unit
def test_adapter_schema_int_param() -> None:
    adapter = next(t for t in _DemoModel().tools() if t.name == "increment")
    schema = adapter.parameters_schema()
    assert schema["properties"]["step"]["type"] == "integer"


@pytest.mark.unit
def test_adapter_schema_optional_param() -> None:
    adapter = next(t for t in _DemoModel().tools() if t.name == "increment")
    schema = adapter.parameters_schema()
    assert "step" not in schema["required"]


@pytest.mark.unit
def test_adapter_schema_x_widget_date() -> None:
    adapter = next(t for t in _DemoModel().tools() if t.name == "book")
    prop = adapter.parameters_schema()["properties"]["when"]
    assert prop.get("x-widget") == "date"


@pytest.mark.unit
def test_adapter_schema_literal_enum() -> None:
    adapter = next(t for t in _DemoModel().tools() if t.name == "set_mode")
    prop = adapter.parameters_schema()["properties"]["mode"]
    assert prop.get("enum") == ["a", "b"]


@pytest.mark.unit
@patch("agentflow.gui.server.serve")
def test_demo_creates_instance_and_calls_serve(mock_serve: MagicMock) -> None:
    _DemoModel.demo(port=9000, open_browser=False, _argv=[])
    mock_serve.assert_called_once()
    call_kwargs = mock_serve.call_args.kwargs
    assert call_kwargs["port"] == 9000
    assert call_kwargs["open_browser"] is False
    assert call_kwargs["demo_url_path"] == "/demo"
    app = mock_serve.call_args.args[0]
    assert app._live_model is not None
