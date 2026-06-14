"""Unit tests for SmartHomeModel."""

from __future__ import annotations

import pytest

from examples.agents.smart_home_model import SmartHomeModel


@pytest.mark.unit
def test_initial_state_kitchen_default() -> None:
    model = SmartHomeModel()
    assert model.state.kitchen.temperature == 20.0


@pytest.mark.unit
def test_set_temperature_updates_state() -> None:
    model = SmartHomeModel()
    result = model.set_temperature("kitchen", 23.0)
    assert "23" in result
    assert model.state.kitchen.temperature == 23.0


@pytest.mark.unit
def test_set_temperature_safety_guard() -> None:
    model = SmartHomeModel()
    before = model.state.bedroom.temperature
    result = model.set_temperature("bedroom", 35.0)
    assert "safety limit" in result
    assert model.state.bedroom.temperature == before


@pytest.mark.unit
def test_toggle_light_kitchen() -> None:
    model = SmartHomeModel()
    initial = model.state.kitchen.lights
    model.toggle_light("kitchen")
    assert model.state.kitchen.lights != initial
    model.toggle_light("kitchen")
    assert model.state.kitchen.lights == initial


@pytest.mark.unit
def test_toggle_stove() -> None:
    model = SmartHomeModel()
    initial = model.state.kitchen.stove
    model.toggle_stove()
    assert model.state.kitchen.stove != initial
    model.toggle_stove()
    assert model.state.kitchen.stove == initial


@pytest.mark.unit
def test_get_status_kitchen() -> None:
    result = SmartHomeModel().get_status("kitchen")
    assert "temperature" in result
    assert "lights" in result


@pytest.mark.unit
def test_get_status_unknown_room() -> None:
    result = SmartHomeModel().get_status("garage")
    assert "Unknown room" in result


@pytest.mark.unit
def test_set_persons() -> None:
    model = SmartHomeModel()
    model.set_persons("living", 3)
    assert model.state.living.persons == 3


@pytest.mark.unit
def test_tools_returns_5_tools() -> None:
    assert len(SmartHomeModel().tools()) == 5


@pytest.mark.unit
def test_tool_registry_has_correct_names() -> None:
    names = set(SmartHomeModel().tool_registry().names())
    assert names == {
        "get_status",
        "set_temperature",
        "toggle_light",
        "toggle_stove",
        "set_persons",
    }


@pytest.mark.unit
def test_state_property_returns_same_instance() -> None:
    model = SmartHomeModel()
    assert model.state is model.state
