"""Tests for StateVertex as Pydantic BaseModel."""
from __future__ import annotations

from typing import Annotated, Any

import pytest
from pydantic import Field, ValidationError

from agentflow.statemachine.context import Context
from agentflow.statemachine.vertex import StateVertex

# ---------------------------------------------------------------------------
# Concrete vertex with a validated field
# ---------------------------------------------------------------------------


class _MyV(StateVertex):
    """Vertex with a ge=1 constraint on x."""

    x: Annotated[int, Field(ge=1, description="Must be >= 1")] = 5

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return object(), object()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPydanticVertex:
    def test_default_instantiation_succeeds(self) -> None:
        """_MyV() with default x=5 must construct without error."""
        v = _MyV()
        assert v.x == 5

    def test_valid_param_instantiation(self) -> None:
        """_MyV(x=10) must succeed."""
        v = _MyV(x=10)
        assert v.x == 10

    def test_invalid_param_raises_validation_error(self) -> None:
        """_MyV(x=-1) must raise pydantic.ValidationError (ge=1 violated)."""
        with pytest.raises(ValidationError):
            _MyV(x=-1)

    def test_model_json_schema_contains_x_in_properties(self) -> None:
        """model_json_schema() must list 'x' in properties."""
        schema = _MyV.model_json_schema()
        assert "x" in schema.get("properties", {}), (
            f"Expected 'x' in schema properties, got: {schema}"
        )

    def test_get_config_schema_contains_x(self) -> None:
        """get_config_schema() must return 'x' as a scalar property."""
        v = _MyV()
        schema = v.get_config_schema()
        props = schema.get("properties", {})
        assert "x" in props, f"Expected 'x' in config schema properties, got: {props}"

    def test_get_param_values_returns_x(self) -> None:
        """get_param_values() must return the current value of x."""
        v = _MyV()
        params = v.get_param_values()
        assert params.get("x") == 5

    def test_set_params_updates_x(self) -> None:
        """set_params(x=7) must update v.x to 7."""
        v = _MyV()
        v.set_params(x=7)
        assert v.x == 7

    def test_direct_field_assignment_works(self) -> None:
        """StateVertex has frozen=False so v.x = 3 must work."""
        v = _MyV()
        v.x = 3
        assert v.x == 3

    def test_is_pydantic_base_model(self) -> None:
        """StateVertex must be a subclass of pydantic.BaseModel."""
        from pydantic import BaseModel

        assert issubclass(_MyV, BaseModel)

    def test_different_instances_are_independent(self) -> None:
        """Two _MyV instances must not share state."""
        v1 = _MyV(x=1)
        v2 = _MyV(x=2)
        v1.x = 99
        assert v2.x == 2
