"""Tests for StateVertex model and temperature base fields (T106-02)."""
from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from agentflow.statemachine.context import Context
from agentflow.statemachine.vertex import StateVertex


class _ConcreteVertex(StateVertex):
    """Minimal concrete vertex for field-level tests."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return object(), object()


@pytest.mark.unit
class TestStateVertexModelField:
    def test_state_vertex_has_model_field_default_empty(self) -> None:
        """StateVertex.model must default to empty string."""
        v = _ConcreteVertex()
        assert v.model == ""

    def test_state_vertex_has_temperature_field_default(self) -> None:
        """StateVertex.temperature must default to 0.2."""
        v = _ConcreteVertex()
        assert v.temperature == 0.2

    def test_model_can_be_set_at_construction(self) -> None:
        """Passing model= at construction must be accepted."""
        v = _ConcreteVertex(model="gpt-4o-mini")
        assert v.model == "gpt-4o-mini"

    def test_temperature_can_be_set_at_construction(self) -> None:
        """Passing temperature= at construction must be accepted."""
        v = _ConcreteVertex(temperature=0.8)
        assert v.temperature == 0.8

    def test_temperature_below_zero_raises_validation_error(self) -> None:
        """temperature < 0.0 must raise pydantic.ValidationError."""
        with pytest.raises(ValidationError):
            _ConcreteVertex(temperature=-0.1)

    def test_temperature_above_two_raises_validation_error(self) -> None:
        """temperature > 2.0 must raise pydantic.ValidationError."""
        with pytest.raises(ValidationError):
            _ConcreteVertex(temperature=2.1)

    def test_model_field_in_config_schema(self) -> None:
        """get_config_schema() must include 'model' in properties."""
        v = _ConcreteVertex()
        schema = v.get_config_schema()
        assert "model" in schema.get("properties", {})

    def test_temperature_field_in_config_schema(self) -> None:
        """get_config_schema() must include 'temperature' in properties."""
        v = _ConcreteVertex()
        schema = v.get_config_schema()
        assert "temperature" in schema.get("properties", {})

    def test_model_schema_has_x_model_select(self) -> None:
        """model field schema must carry x-model-select: true for GUI hint."""
        v = _ConcreteVertex()
        schema = v.get_config_schema()
        model_prop = schema["properties"].get("model", {})
        assert model_prop.get("x-model-select") is True

    def test_get_param_values_includes_model_and_temperature(self) -> None:
        """get_param_values() must return model and temperature."""
        v = _ConcreteVertex(model="gpt-4o-mini", temperature=0.5)
        params = v.get_param_values()
        assert params["model"] == "gpt-4o-mini"
        assert params["temperature"] == 0.5
