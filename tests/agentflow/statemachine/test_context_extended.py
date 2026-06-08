"""Tests for the extended Context features added in T103-02."""
from __future__ import annotations

import logging

import pytest

from agentflow.llm.connectors.FakeLlmConnector import FakeLlmConnector
from agentflow.statemachine.context import Context
from agentflow.statemachine.run_stats import RunStats

# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestContextConstruction:
    def test_context_no_args_constructs(self) -> None:
        """Context() must work with zero arguments — all fields have defaults."""
        ctx = Context()
        assert ctx.connector is None
        assert ctx.tools is None
        assert ctx.step == 0

    def test_context_connector_kwarg_backward_compat(self) -> None:
        """Context(connector=fake) is still valid after multi-connector refactor."""
        fake = FakeLlmConnector()
        ctx = Context(connector=fake)
        assert ctx.connector is fake

    def test_context_llm_connectors_dict_works(self) -> None:
        """Context(llm_connectors={...}) constructs correctly."""
        fake = FakeLlmConnector()
        ctx = Context(llm_connectors={"default": fake})
        assert ctx.llm_connectors["default"] is fake

    def test_context_stats_is_run_stats_instance(self) -> None:
        """ctx.stats must be a RunStats instance, not None."""
        ctx = Context()
        assert isinstance(ctx.stats, RunStats)

    def test_context_step_starts_at_zero(self) -> None:
        ctx = Context()
        assert ctx.step == 0

    def test_context_auto_generates_run_id(self) -> None:
        ctx = Context()
        assert ctx.run_id and isinstance(ctx.run_id, str)


# ---------------------------------------------------------------------------
# ctx.llm()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestContextLlm:
    def test_ctx_llm_returns_connector_from_dict(self) -> None:
        """ctx.llm() resolves 'default' key from llm_connectors."""
        fake = FakeLlmConnector()
        ctx = Context(llm_connectors={"default": fake})
        assert ctx.llm() is fake

    def test_ctx_llm_falls_back_to_legacy_connector(self) -> None:
        """When llm_connectors is empty, ctx.llm() falls back to ctx.connector."""
        fake = FakeLlmConnector()
        ctx = Context(connector=fake)
        assert ctx.llm() is fake

    def test_ctx_llm_missing_key_logs_warning_and_raises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Requesting a non-existent key (with no fallback) must log a warning and raise."""
        ctx = Context(llm_connectors={"other": FakeLlmConnector()})
        with caplog.at_level(logging.WARNING), pytest.raises(ValueError, match="No LLM connector"):
            ctx.llm("missing_key")
        assert any("missing_key" in r.message or "not found" in r.message for r in caplog.records)

    def test_ctx_llm_no_connector_raises_value_error(self) -> None:
        """ctx.llm() with neither dict nor legacy connector must raise ValueError."""
        ctx = Context()
        with pytest.raises(ValueError, match="No LLM connector"):
            ctx.llm()


# ---------------------------------------------------------------------------
# ctx.get_tools()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestContextGetTools:
    def test_ctx_get_tools_no_tools_raises(self) -> None:
        """ctx.get_tools() with no registry configured must raise ValueError."""
        ctx = Context()
        with pytest.raises(ValueError, match="No tool registry"):
            ctx.get_tools()


# ---------------------------------------------------------------------------
# ctx.exceeded()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestContextExceeded:
    def test_exceeded_below_threshold_returns_false(self) -> None:
        ctx = Context()
        ctx.step = 3
        assert ctx.exceeded(5) is False

    def test_exceeded_at_threshold_returns_true(self) -> None:
        ctx = Context()
        ctx.step = 5
        assert ctx.exceeded(5) is True

    def test_exceeded_above_threshold_returns_true(self) -> None:
        ctx = Context()
        ctx.step = 10
        assert ctx.exceeded(5) is True

    def test_exceeded_at_zero_step_returns_false_for_positive_n(self) -> None:
        ctx = Context()
        assert ctx.exceeded(1) is False


# ---------------------------------------------------------------------------
# ctx.llm_for_model()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestContextLlmForModel:
    def test_llm_for_model_finds_by_model_name(self) -> None:
        """llm_for_model() returns the connector whose config.model matches."""
        fake = FakeLlmConnector()
        # FakeLlmConnector has no real config, so use a wrapped approach
        # by patching config attribute for the test
        from unittest.mock import MagicMock, patch

        mock_config = MagicMock()
        mock_config.model = "gpt-4o-mini"
        with patch.object(type(fake), "config", new_callable=lambda: property(lambda self: mock_config)):
            ctx = Context(llm_connectors={"default": fake})
            result = ctx.llm_for_model("gpt-4o-mini")
        assert result is fake

    def test_llm_for_model_falls_back_to_default_when_model_empty(self) -> None:
        """llm_for_model('') returns the default connector via llm()."""
        fake = FakeLlmConnector()
        ctx = Context(llm_connectors={"default": fake})
        result = ctx.llm_for_model("")
        assert result is fake

    def test_llm_for_model_creates_transient_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """llm_for_model() logs a WARNING and creates transient connector when no match."""
        fake = FakeLlmConnector()
        # connector has no matching model
        from unittest.mock import MagicMock, patch

        mock_config = MagicMock()
        mock_config.model = "other-model"
        with (
            caplog.at_level(logging.WARNING),
            patch.object(type(fake), "config", new_callable=lambda: property(lambda self: mock_config)),
        ):
            ctx = Context(llm_connectors={"default": fake})
            result = ctx.llm_for_model("gpt-4o-mini")
        # Must have logged a warning about the missing connector
        assert any("transient" in r.message.lower() or "no connector" in r.message.lower()
                   for r in caplog.records)
        # Must return some connector (the transient one)
        assert result is not None
