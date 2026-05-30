"""Shared pytest fixtures and configuration for the test suite.

Integration tests (marked with ``@pytest.mark.integration``) require a live
LLM connection.  The default model is ``gpt-4o-mini`` (OpenAI) — very cheap
and responds quickly, making it suitable for automated testing.

Override the test model and backend via environment variables:
  TEST_LLM_BACKEND   backend to use in integration tests (default: "openai")
  TEST_LLM_MODEL     model to use in integration tests (default: "gpt-4o-mini")

Example — run only unit tests (no network, no API key needed):
  pytest -m unit

Example — run integration tests with a specific model:
  TEST_LLM_BACKEND=openai TEST_LLM_MODEL=gpt-4o-mini pytest -m integration
"""

from __future__ import annotations

import os

import pytest

from agentflow.llm.LlmConfig import LlmConfig
from agentflow.llm.LlmConnector import LlmConnector

# ---------------------------------------------------------------------------
# Integration test model defaults
# ---------------------------------------------------------------------------

_DEFAULT_TEST_BACKEND = "openai"
_DEFAULT_TEST_MODEL = "gpt-4o-mini"


def _integration_config() -> LlmConfig:
    """Build LlmConfig for integration tests.

    Reads TEST_LLM_BACKEND / TEST_LLM_MODEL from the environment, falling
    back to gpt-4o-mini so tests are cheap and fast by default.
    """
    backend = os.getenv("TEST_LLM_BACKEND", _DEFAULT_TEST_BACKEND)
    model = os.getenv("TEST_LLM_MODEL", _DEFAULT_TEST_MODEL)
    # Temporarily set env vars so LlmConfig.from_env() picks them up.
    old_backend = os.environ.get("LLM_BACKEND")
    old_model = os.environ.get("LLM_MODEL")
    try:
        os.environ["LLM_BACKEND"] = backend
        os.environ["LLM_MODEL"] = model
        return LlmConfig.from_env()
    finally:
        # Restore original values (or remove if they were not set before).
        if old_backend is None:
            os.environ.pop("LLM_BACKEND", None)
        else:
            os.environ["LLM_BACKEND"] = old_backend
        if old_model is None:
            os.environ.pop("LLM_MODEL", None)
        else:
            os.environ["LLM_MODEL"] = old_model


@pytest.fixture(scope="session")
def integration_config() -> LlmConfig:
    """Session-scoped LlmConfig for integration tests."""
    return _integration_config()


@pytest.fixture(scope="session")
def integration_connector(integration_config: LlmConfig) -> LlmConnector:
    """Session-scoped LlmConnector for integration tests."""
    return LlmConnector.create(integration_config)
