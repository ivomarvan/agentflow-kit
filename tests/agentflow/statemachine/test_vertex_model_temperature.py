"""Tests for LlmStateVertex model and temperature fields, and StateVertex tooltip."""
from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from agentflow.statemachine.context import Context
from agentflow.statemachine.vertex import LlmStateVertex, StateVertex


class _ConcreteVertex(StateVertex):
    """Minimal concrete StateVertex — no LLM fields."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return object(), object()


class _ConcreteLlmVertex(LlmStateVertex):
    """Minimal concrete LlmStateVertex — has model + temperature."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return object(), object()


@pytest.mark.unit
class TestStateVertexTooltip:
    def test_state_vertex_no_model_field(self) -> None:
        """Base StateVertex must NOT have model or temperature fields."""
        v = _ConcreteVertex()
        assert not hasattr(v, "model") or "model" not in v.model_fields
        assert not hasattr(v, "temperature") or "temperature" not in v.model_fields

    def test_state_vertex_pydantic_fields_in_own_attributes(self) -> None:
        """_get_own_attributes() must include Pydantic-declared fields."""
        class _WithField(StateVertex):
            my_param: int = 42
            async def run(self, state, ctx):  # type: ignore[override]
                return object(), object()

        v = _WithField()
        attrs = v._get_own_attributes()
        assert attrs.get("my_param") == 42


@pytest.mark.unit
class TestLlmVertexModelField:
    def test_llm_vertex_has_model_field_default_empty(self) -> None:
        """LlmStateVertex.model must default to empty string."""
        v = _ConcreteLlmVertex()
        assert v.model == ""

    def test_llm_vertex_has_temperature_field_default(self) -> None:
        """LlmStateVertex.temperature must default to 0.2."""
        v = _ConcreteLlmVertex()
        assert v.temperature == 0.2

    def test_model_can_be_set_at_construction(self) -> None:
        """Passing model= at construction must be accepted."""
        v = _ConcreteLlmVertex(model="gpt-4o-mini")
        assert v.model == "gpt-4o-mini"

    def test_temperature_can_be_set_at_construction(self) -> None:
        """Passing temperature= at construction must be accepted."""
        v = _ConcreteLlmVertex(temperature=0.8)
        assert v.temperature == 0.8

    def test_temperature_below_zero_raises_validation_error(self) -> None:
        """temperature < 0.0 must raise pydantic.ValidationError."""
        with pytest.raises(ValidationError):
            _ConcreteLlmVertex(temperature=-0.1)

    def test_temperature_above_two_raises_validation_error(self) -> None:
        """temperature > 2.0 must raise pydantic.ValidationError."""
        with pytest.raises(ValidationError):
            _ConcreteLlmVertex(temperature=2.1)

    def test_model_field_in_config_schema(self) -> None:
        """get_config_schema() must include 'model' in properties."""
        v = _ConcreteLlmVertex()
        schema = v.get_config_schema()
        assert "model" in schema.get("properties", {})

    def test_temperature_field_in_config_schema(self) -> None:
        """get_config_schema() must include 'temperature' in properties."""
        v = _ConcreteLlmVertex()
        schema = v.get_config_schema()
        assert "temperature" in schema.get("properties", {})

    def test_model_schema_has_x_model_select(self) -> None:
        """model field schema must carry x-model-select: true for GUI hint."""
        v = _ConcreteLlmVertex()
        schema = v.get_config_schema()
        model_prop = schema["properties"].get("model", {})
        assert model_prop.get("x-model-select") is True

    def test_get_param_values_includes_model_and_temperature(self) -> None:
        """get_param_values() must return model and temperature."""
        v = _ConcreteLlmVertex(model="gpt-4o-mini", temperature=0.5)
        params = v.get_param_values()
        assert params["model"] == "gpt-4o-mini"
        assert params["temperature"] == 0.5

    def test_llm_vertex_is_state_vertex(self) -> None:
        """LlmStateVertex must be a subclass of StateVertex."""
        assert issubclass(LlmStateVertex, StateVertex)

    def test_llm_vertex_tooltip_includes_model_and_temperature(self) -> None:
        """_get_own_attributes() on LlmStateVertex must expose model + temperature."""
        v = _ConcreteLlmVertex(model="gemini-3.5-flash", temperature=0.7)
        attrs = v._get_own_attributes()
        assert attrs.get("model") == "gemini-3.5-flash"
        assert attrs.get("temperature") == 0.7
