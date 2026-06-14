"""Unit tests for CounterModel."""

from __future__ import annotations

import importlib

import pytest

_counter_mod = importlib.import_module("examples.framework.05_counter_live_model")
CounterModel = _counter_mod.CounterModel


@pytest.mark.unit
def test_increment_default_step() -> None:
    model = CounterModel()
    model.increment()
    assert model.state.count == 1


@pytest.mark.unit
def test_increment_custom_step() -> None:
    model = CounterModel()
    model.increment(step=5)
    assert model.state.count == 5


@pytest.mark.unit
def test_decrement_never_below_zero() -> None:
    model = CounterModel()
    model.decrement(step=3)
    assert model.state.count == 0


@pytest.mark.unit
def test_reset_clears_count_and_history() -> None:
    model = CounterModel()
    model.increment(step=2)
    model.reset()
    assert model.state.count == 0
    assert model.state.history == []


@pytest.mark.unit
def test_set_value() -> None:
    model = CounterModel()
    model.set_value(42)
    assert model.state.count == 42


@pytest.mark.unit
def test_history_keeps_last_five() -> None:
    model = CounterModel()
    for step in range(1, 8):
        model.increment(step=1)
    assert len(model.state.history) == 5


@pytest.mark.unit
def test_tools_returns_four_actions() -> None:
    assert len(CounterModel().tools()) == 4
