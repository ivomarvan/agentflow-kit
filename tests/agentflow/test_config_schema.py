"""Unit tests for T030: Pydantic LlmConfig + AgentApp config schema API."""
from __future__ import annotations

import pytest

from agentflow import AgentApp, ConfigParam, LlmConfig
from agentflow.llm.LlmConnector import LlmConnector as _LlmConnector


class _ConnectorApp(AgentApp):
    """Minimal app with a real-like connector attribute for config schema tests."""

    def __init__(self) -> None:
        super().__init__()
        config = LlmConfig(
            backend="openai",
            model="gpt-4o-mini",
            base_url=None,
            api_key="test-key",
            timeout=30.0,
        )
        self.connector = _LlmConnector(config=config)


@pytest.mark.unit
def test_llm_config_is_pydantic_basemodel() -> None:
    """LlmConfig should be a Pydantic BaseModel, not a dataclass."""
    from pydantic import BaseModel

    assert issubclass(LlmConfig, BaseModel)


@pytest.mark.unit
def test_llm_config_model_json_schema_has_properties() -> None:
    """LlmConfig.model_json_schema() should include the key field names."""
    schema = LlmConfig.model_json_schema()
    assert "properties" in schema
    props = schema["properties"]
    assert "backend" in props
    assert "model" in props
    assert "timeout" in props


@pytest.mark.unit
def test_llm_config_field_access() -> None:
    """LlmConfig fields should be accessible as attributes (same as dataclass)."""
    cfg = LlmConfig(backend="ollama", model="test-model", timeout=60.0)
    assert cfg.backend == "ollama"
    assert cfg.model == "test-model"
    assert cfg.timeout == 60.0
    assert cfg.base_url is None
    assert cfg.api_key is None


@pytest.mark.unit
def test_llm_config_mutation() -> None:
    """LlmConfig should allow field mutation (frozen=False)."""
    cfg = LlmConfig(backend="ollama", model="old-model", timeout=60.0)
    cfg.model = "new-model"
    assert cfg.model == "new-model"


@pytest.mark.unit
def test_llm_config_describe() -> None:
    """LlmConfig.describe() should return a summary string."""
    cfg = LlmConfig(backend="openai", model="gpt-4o-mini", timeout=120.0)
    text = cfg.describe()
    assert "openai" in text
    assert "gpt-4o-mini" in text


@pytest.mark.unit
def test_agent_app_get_config_schema_no_connector() -> None:
    """get_config_schema() on app with no LlmConnector should return empty properties."""
    app = AgentApp.__new__(AgentApp)
    AgentApp.__init__(app)
    schema = app.get_config_schema()
    assert schema["type"] == "object"
    assert schema["properties"] == {}


@pytest.mark.unit
def test_agent_app_get_config_schema_with_connector() -> None:
    """get_config_schema() should include connector's LlmConfig schema."""
    app = _ConnectorApp()
    schema = app.get_config_schema()
    assert "connector" in schema["properties"]
    connector_schema = schema["properties"]["connector"]
    assert "properties" in connector_schema
    assert "model" in connector_schema["properties"]


@pytest.mark.unit
def test_agent_app_get_config_returns_current_values() -> None:
    """get_config() returns nested dict with model and timeout; backend is hidden."""
    app = _ConnectorApp()
    cfg = app.get_config()
    assert "connector" in cfg
    assert isinstance(cfg["connector"], dict)
    # backend is intentionally hidden from the config values
    assert "backend" not in cfg["connector"]
    assert cfg["connector"]["model"] == "gpt-4o-mini"
    assert "timeout" in cfg["connector"]


@pytest.mark.unit
def test_agent_app_set_config_updates_connector_field() -> None:
    """set_config('connector.model', ...) should update the connector's model."""
    app = _ConnectorApp()
    app.set_config("connector.model", "gpt-4o")
    assert app.connector.model == "gpt-4o"


@pytest.mark.unit
def test_agent_app_set_config_invalid_path_raises_key_error() -> None:
    """set_config with a non-dotted path should raise KeyError."""
    app = _ConnectorApp()
    with pytest.raises(KeyError, match="Invalid config path"):
        app.set_config("no-dot-here", "value")


@pytest.mark.unit
def test_agent_app_set_config_unknown_child_raises_key_error() -> None:
    """set_config with unknown child name should raise KeyError."""
    app = _ConnectorApp()
    with pytest.raises(KeyError):
        app.set_config("nonexistent.model", "gpt-4o")


@pytest.mark.unit
def test_agent_app_set_config_unknown_param_raises_key_error() -> None:
    """set_config with unknown param name should raise KeyError."""
    app = _ConnectorApp()
    with pytest.raises(KeyError):
        app.set_config("connector.nonexistent_field", "value")


@pytest.mark.unit
def test_config_param_dataclass() -> None:
    """ConfigParam should be a dataclass with expected fields."""
    param = ConfigParam(name="model", type_hint="str", value="gpt-4o")
    assert param.name == "model"
    assert param.type_hint == "str"
    assert param.value == "gpt-4o"
    assert param.description == ""
    assert param.min_value is None
    assert param.max_value is None
    assert param.choices == []
    assert param.required is False
