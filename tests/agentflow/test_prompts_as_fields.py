"""Unit tests — system prompts as Pydantic fields on StateVertex subclasses (E105.T01)."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture(scope="module")
def smart_home():
    """Load the smart home example module once per test module."""
    return importlib.import_module("examples.agents.06_smart_home_assistant")


@pytest.mark.unit
def test_safety_judge_exposes_system_prompt_in_schema(smart_home) -> None:
    """SafetyJudgeVertex schema must expose system_prompt as textarea."""
    schema = smart_home.SafetyJudgeVertex().get_config_schema()
    assert "system_prompt" in schema["properties"]
    assert schema["properties"]["system_prompt"]["format"] == "textarea"


@pytest.mark.unit
def test_safety_judge_system_prompt_override(smart_home) -> None:
    """system_prompt must be overridable via constructor."""
    vertex = smart_home.SafetyJudgeVertex(system_prompt="Custom rules.")
    assert vertex.system_prompt == "Custom rules."


@pytest.mark.unit
def test_voice_formatter_system_prompt_in_schema(smart_home) -> None:
    """VoiceFormatterVertex schema must mark system_prompt as textarea."""
    schema = smart_home.VoiceFormatterVertex().get_config_schema()
    assert schema["properties"]["system_prompt"]["format"] == "textarea"


@pytest.mark.unit
def test_intent_parser_system_prompt_in_schema(smart_home) -> None:
    """IntentParserVertex schema must include system_prompt."""
    schema = smart_home.IntentParserVertex().get_config_schema()
    assert "system_prompt" in schema["properties"]


@pytest.mark.unit
def test_device_worker_system_prompt_in_schema(smart_home) -> None:
    """DeviceWorkerVertex schema must include system_prompt."""
    schema = smart_home.DeviceWorkerVertex().get_config_schema()
    assert "system_prompt" in schema["properties"]
