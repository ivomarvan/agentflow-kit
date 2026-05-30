"""Unit tests for the Calculator tool."""

from __future__ import annotations

import pytest

from agentflow.tools.common_tools.Calculator import Calculator


@pytest.fixture
def calc() -> Calculator:
    return Calculator()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCalculatorHappyPath:
    def test_addition(self, calc: Calculator) -> None:
        assert calc.execute(expression="2 + 2") == "4"

    def test_multiplication(self, calc: Calculator) -> None:
        assert calc.execute(expression="19 * 23") == "437"

    def test_division(self, calc: Calculator) -> None:
        assert calc.execute(expression="10 / 4") == "2.5"

    def test_parentheses(self, calc: Calculator) -> None:
        assert calc.execute(expression="(2 + 3) * 4") == "20"

    def test_float_arithmetic(self, calc: Calculator) -> None:
        result = calc.execute(expression="1.5 * 2")
        assert result == "3.0"

    def test_spaces_are_allowed(self, calc: Calculator) -> None:
        assert calc.execute(expression="  3  +  3  ") == "6"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCalculatorErrors:
    def test_injection_attempt_returns_error(self, calc: Calculator) -> None:
        result = calc.execute(expression="import os")
        assert result.startswith("ERROR")

    def test_variable_name_returns_error(self, calc: Calculator) -> None:
        result = calc.execute(expression="x + 1")
        assert result.startswith("ERROR")

    def test_division_by_zero_returns_error(self, calc: Calculator) -> None:
        result = calc.execute(expression="1 / 0")
        assert result.startswith("ERROR")

    def test_empty_expression_returns_error(self, calc: Calculator) -> None:
        result = calc.execute(expression="")
        assert result.startswith("ERROR")

    def test_semicolon_injection_returns_error(self, calc: Calculator) -> None:
        result = calc.execute(expression="1; import os")
        assert result.startswith("ERROR")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_calculator_schema_structure(calc: Calculator) -> None:
    schema = calc.to_openai_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "calculator"
    params = schema["function"]["parameters"]
    assert "expression" in params["properties"]
    assert "expression" in params["required"]


@pytest.mark.unit
def test_calculator_name_is_calculator(calc: Calculator) -> None:
    assert calc.name == "calculator"
