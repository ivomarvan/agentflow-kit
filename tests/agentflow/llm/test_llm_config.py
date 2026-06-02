"""Unit tests for LlmConfig — backend detection, env parsing, model lists."""

from __future__ import annotations

import pytest

from agentflow.llm.LlmConfig import OPENAI_COMPATIBLE_BACKENDS, SUPPORTED_BACKENDS, LlmConfig

# ---------------------------------------------------------------------------
# _infer_backend
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInferBackend:
    def test_infer_backend_gpt_returns_openai(self) -> None:
        assert LlmConfig._infer_backend("gpt-4o-mini") == "openai"

    def test_infer_backend_o1_returns_openai(self) -> None:
        assert LlmConfig._infer_backend("o1-preview") == "openai"

    def test_infer_backend_gemini_returns_gemini(self) -> None:
        assert LlmConfig._infer_backend("gemini-3.5-flash") == "gemini"

    def test_infer_backend_deepseek_returns_deepseek(self) -> None:
        assert LlmConfig._infer_backend("deepseek-chat") == "deepseek"

    def test_infer_backend_claude_returns_anthropic(self) -> None:
        assert LlmConfig._infer_backend("claude-haiku-4-5") == "anthropic"

    def test_infer_backend_unknown_model_returns_none(self) -> None:
        assert LlmConfig._infer_backend("qwen3:8b") is None

    def test_infer_backend_empty_string_returns_none(self) -> None:
        assert LlmConfig._infer_backend("") is None


# ---------------------------------------------------------------------------
# _load_model_list
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadModelList:
    def test_load_model_list_parses_csv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLLAMA_MODELS", "qwen3:8b,llama3.2,qwen2.5:1.5b")
        result = LlmConfig._load_model_list("ollama")
        assert result == ["qwen3:8b", "llama3.2", "qwen2.5:1.5b"]

    def test_load_model_list_strips_spaces(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_MODELS", " gpt-4o-mini , gpt-4o ")
        result = LlmConfig._load_model_list("openai")
        assert result == ["gpt-4o-mini", "gpt-4o"]

    def test_load_model_list_empty_env_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLLAMA_MODELS", raising=False)
        assert LlmConfig._load_model_list("ollama") == []

    def test_load_model_list_unknown_backend_returns_empty(self) -> None:
        assert LlmConfig._load_model_list("unknown_backend") == []


# ---------------------------------------------------------------------------
# from_env — backend resolution
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFromEnvBackendResolution:
    def test_explicit_backend_ollama(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_BACKEND", "ollama")
        monkeypatch.delenv("LLM_MODEL", raising=False)
        cfg = LlmConfig.from_env()
        assert cfg.backend == "ollama"

    def test_model_prefix_detects_openai(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LLM_BACKEND", raising=False)
        monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        cfg = LlmConfig.from_env()
        assert cfg.backend == "openai"
        assert cfg.model == "gpt-4o-mini"

    def test_model_prefix_detects_gemini(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LLM_BACKEND", raising=False)
        monkeypatch.setenv("LLM_MODEL", "gemini-3.5-flash")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        cfg = LlmConfig.from_env()
        assert cfg.backend == "gemini"

    def test_unknown_prefix_defaults_to_ollama(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LLM_BACKEND", raising=False)
        monkeypatch.setenv("LLM_MODEL", "qwen3:8b")
        cfg = LlmConfig.from_env()
        assert cfg.backend == "ollama"

    def test_no_env_defaults_to_ollama(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LLM_BACKEND", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)
        cfg = LlmConfig.from_env()
        assert cfg.backend == "ollama"

    def test_unsupported_backend_raises_value_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_BACKEND", "nonexistent")
        with pytest.raises(ValueError, match="nonexistent"):
            LlmConfig.from_env()

    def test_cloud_backend_without_api_key_raises_runtime_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_BACKEND", "openai")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        # Prevent _find_env_file from loading .env which may contain the key.
        monkeypatch.setattr(LlmConfig, "_find_env_file", staticmethod(lambda _: None))
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            LlmConfig.from_env()

    def test_timeout_is_parsed_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_BACKEND", "ollama")
        monkeypatch.setenv("LLM_TIMEOUT", "30")
        cfg = LlmConfig.from_env()
        assert cfg.timeout == 30.0


# ---------------------------------------------------------------------------
# with_overrides
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWithOverrides:
    def test_model_override_infers_openai_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Overriding model to gpt-* must switch away from default ollama backend."""
        monkeypatch.delenv("LLM_BACKEND", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        base = LlmConfig.from_env()
        assert base.backend == "ollama"

        updated = base.with_overrides(model="gpt-4o-mini")
        assert updated.backend == "openai"
        assert updated.model == "gpt-4o-mini"
        assert updated.base_url is None
        assert updated.api_key == "test-key"

    def test_explicit_backend_override_is_respected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_BACKEND", "ollama")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        base = LlmConfig.from_env()

        updated = base.with_overrides(backend="openai", model="gpt-4o")
        assert updated.backend == "openai"
        assert updated.model == "gpt-4o"


@pytest.mark.unit
def test_llm_connector_model_override_infers_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LlmConnector(model=...) must not leave ollama backend for OpenAI model names."""
    from agentflow.llm.connectors.LlmConnector import LlmConnector

    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    connector = LlmConnector(model="gpt-4o-mini")
    assert connector.config.backend == "openai"
    assert connector.config.model == "gpt-4o-mini"
    assert connector.config.base_url is None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_supported_backends_contains_expected() -> None:
    assert {"openai", "gemini", "ollama", "deepseek", "anthropic"} <= SUPPORTED_BACKENDS


@pytest.mark.unit
def test_openai_compatible_backends_does_not_contain_anthropic() -> None:
    assert "anthropic" not in OPENAI_COMPATIBLE_BACKENDS
    assert "openai" in OPENAI_COMPATIBLE_BACKENDS
