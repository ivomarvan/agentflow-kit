"""Unit tests for ToolBase, param_desc and the JSON schema builder."""

from __future__ import annotations

from typing import Any

import pytest
from git_root_to_syspath import agr

agr()

from src.agentflow.tools.Tool import ToolBase, build_parameters_schema, param_desc


# ---------------------------------------------------------------------------
# Minimal concrete tool for testing
# (No leading underscore — would cause camel→snake to produce "__greet")
# ---------------------------------------------------------------------------


class Greet(ToolBase):
    """Say hello to a person."""

    @param_desc(name="The person's name.", language="Greeting language: 'en' or 'cs'.")
    def execute(self, name: str, language: str = "en") -> str:
        return f"Hello {name}" if language == "en" else f"Ahoj {name}"


class NoDesc(ToolBase):
    """Tool without param_desc decorator."""

    def execute(self, value: int) -> str:  # type: ignore[override]
        return str(value)


class MultiType(ToolBase):
    """Tool with various parameter types."""

    def execute(  # type: ignore[override]
        self,
        text: str,
        count: int,
        ratio: float,
        flag: bool,
        items: list,
    ) -> str:
        return ""


# ---------------------------------------------------------------------------
# name derivation (CamelCase → snake_case)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestToolName:
    def test_name_is_snake_case_of_class(self) -> None:
        assert Greet().name == "greet"

    def test_name_multi_word(self) -> None:
        class GetCurrentWeather(ToolBase):
            """Weather tool."""
            def execute(self) -> str:  # type: ignore[override]
                return ""
        assert GetCurrentWeather().name == "get_current_weather"


# ---------------------------------------------------------------------------
# description defaults to docstring
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_description_uses_class_docstring() -> None:
    assert Greet().description == "Say hello to a person."


# ---------------------------------------------------------------------------
# build_parameters_schema
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParametersSchema:
    def test_required_param_appears_in_required_list(self) -> None:
        schema = Greet().parameters_schema()
        assert "name" in schema["required"]

    def test_optional_param_not_in_required_list(self) -> None:
        schema = Greet().parameters_schema()
        assert "language" not in schema["required"]

    def test_param_desc_sets_description(self) -> None:
        schema = Greet().parameters_schema()
        assert schema["properties"]["name"]["description"] == "The person's name."
        assert "language" in schema["properties"]["language"]["description"]

    def test_no_param_desc_omits_description_key(self) -> None:
        schema = NoDesc().parameters_schema()
        assert "description" not in schema["properties"]["value"]

    def test_int_type_maps_to_integer(self) -> None:
        schema = NoDesc().parameters_schema()
        assert schema["properties"]["value"]["type"] == "integer"

    def test_multiple_types_mapped_correctly(self) -> None:
        props = MultiType().parameters_schema()["properties"]
        assert props["text"]["type"] == "string"
        assert props["count"]["type"] == "integer"
        assert props["ratio"]["type"] == "number"
        assert props["flag"]["type"] == "boolean"
        assert props["items"]["type"] == "array"

    def test_self_is_excluded_from_schema(self) -> None:
        schema = Greet().parameters_schema()
        assert "self" not in schema["properties"]


# ---------------------------------------------------------------------------
# to_openai_schema
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_to_openai_schema_top_level_structure() -> None:
    schema = Greet().to_openai_schema()
    assert schema["type"] == "function"
    assert "function" in schema
    fn = schema["function"]
    assert fn["name"] == "greet"
    assert "parameters" in fn


# ---------------------------------------------------------------------------
# Optional type unwrapping
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_optional_param_type_is_unwrapped() -> None:
    class _Opt(ToolBase):
        """Tool with optional param."""
        def execute(self, x: str | None = None) -> str:  # type: ignore[override]
            return x or ""

    schema = _Opt().parameters_schema()
    assert schema["properties"]["x"]["type"] == "string"
    assert "x" not in schema["required"]
