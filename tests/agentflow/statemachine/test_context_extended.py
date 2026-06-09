"""Tests for Context dataclass — E107: LlmPool-based connector management."""
from __future__ import annotations

import logging

import pytest

from agentflow.llm.LlmPool import LlmPool
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
        assert ctx.tools is None
        assert ctx.step == 0
        assert isinstance(ctx.pool, LlmPool)

    def test_context_pool_kwarg_accepted(self) -> None:
        """Context(pool=LlmPool()) is valid."""
        pool = LlmPool()
        ctx = Context(pool=pool)
        assert ctx.pool is pool

    def test_context_pool_from_connector_wraps_fake(self) -> None:
        """LlmPool.from_connector() lets tests inject a fixed connector."""
        fake = FakeLlmConnector()
        pool = LlmPool.from_connector(fake)
        ctx = Context(pool=pool)
        assert ctx.pool is pool

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

    def test_default_pool_is_llm_pool(self) -> None:
        """Context() default pool must be an LlmPool instance."""
        ctx = Context()
        assert isinstance(ctx.pool, LlmPool)


# ---------------------------------------------------------------------------
# ctx.llm()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestContextLlm:
    def test_ctx_llm_returns_connector_via_pool(self) -> None:
        """ctx.llm() returns a connector from the pool."""
        fake = FakeLlmConnector()
        pool = LlmPool.from_connector(fake)
        ctx = Context(pool=pool)
        result = ctx.llm()
        assert result is fake

    def test_ctx_llm_key_is_ignored(self) -> None:
        """ctx.llm(key='anything') delegates to pool and ignores the key."""
        fake = FakeLlmConnector()
        pool = LlmPool.from_connector(fake)
        ctx = Context(pool=pool)
        assert ctx.llm("any_key") is fake


# ---------------------------------------------------------------------------
# ctx.llm_for_model()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestContextLlmForModel:
    def test_llm_for_model_delegates_to_pool(self) -> None:
        """llm_for_model() returns whatever the pool returns."""
        fake = FakeLlmConnector()
        pool = LlmPool.from_connector(fake)
        ctx = Context(pool=pool)
        result = ctx.llm_for_model("gpt-4o-mini")
        assert result is fake

    def test_llm_for_model_empty_string_returns_default(self) -> None:
        """llm_for_model('') returns the default pool connector."""
        fake = FakeLlmConnector()
        pool = LlmPool.from_connector(fake)
        ctx = Context(pool=pool)
        result = ctx.llm_for_model("")
        assert result is fake


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
# LlmPool.from_connector (test helper factory)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLlmPoolFromConnector:
    def test_from_connector_returns_pool(self) -> None:
        fake = FakeLlmConnector()
        pool = LlmPool.from_connector(fake)
        assert isinstance(pool, LlmPool)

    def test_from_connector_always_returns_same_connector(self) -> None:
        fake = FakeLlmConnector()
        pool = LlmPool.from_connector(fake)
        assert pool.get_connector("gpt-4o") is fake
        assert pool.get_connector("gemini-3.5") is fake
        assert pool.get_connector("") is fake

    def test_pool_without_cache_returns_connector(self) -> None:
        """LlmPool(cache=None) constructs without error; get_connector creates connector."""
        pool = LlmPool(cache=None)
        # We only test construction — actual LlmConnector creation requires env vars
        assert isinstance(pool, LlmPool)
