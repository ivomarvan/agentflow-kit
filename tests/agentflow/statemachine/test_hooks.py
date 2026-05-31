"""Unit tests for RunnerHooks, NoOpHooks, and LoggingHooks."""

from __future__ import annotations

import asyncio
import logging

import pytest

from agentflow.statemachine.hooks import LoggingHooks, NoOpHooks, RunnerHooks


@pytest.mark.unit
class TestNoOpHooks:
    def test_noop_hooks_callbacks_return_none(self) -> None:
        # All async callbacks on NoOpHooks must return None (fire-and-forget safe)
        hooks = NoOpHooks()
        result = asyncio.run(hooks.on_run_start(object()))
        assert result is None

    def test_noop_hooks_satisfies_protocol(self) -> None:
        # NoOpHooks satisfies RunnerHooks structurally (duck typing via @runtime_checkable)
        hooks = NoOpHooks()
        assert isinstance(hooks, RunnerHooks)

    def test_noop_hooks_super_step_end_returns_none(self) -> None:
        # Edge case: set argument for next_active must be accepted without error
        hooks = NoOpHooks()
        result = asyncio.run(hooks.on_super_step_end(1, object(), set()))
        assert result is None


@pytest.mark.unit
class TestLoggingHooks:
    def test_logging_hooks_logs_at_super_step_start(self, caplog: pytest.LogCaptureFixture) -> None:
        hooks = LoggingHooks()
        with caplog.at_level(logging.DEBUG, logger="statemachine.runner"):
            asyncio.run(hooks.on_super_step_start(1, object(), []))
        assert any("step #1 start" in r.message for r in caplog.records)

    def test_logging_hooks_logs_vertex_error(self, caplog: pytest.LogCaptureFixture) -> None:
        class _FakeVertex:
            pass

        hooks = LoggingHooks()
        exc = ValueError("test error")
        with caplog.at_level(logging.ERROR, logger="statemachine.runner"):
            asyncio.run(hooks.on_vertex_error(_FakeVertex(), exc))  # type: ignore[arg-type]
        assert any(r.levelname == "ERROR" for r in caplog.records)

    def test_logging_hooks_custom_logger_name(self, caplog: pytest.LogCaptureFixture) -> None:
        # LoggingHooks must use the provided logger name, not the default
        hooks = LoggingHooks(name="custom.test.logger")
        with caplog.at_level(logging.INFO, logger="custom.test.logger"):
            asyncio.run(hooks.on_run_start(object()))
        assert any(r.name == "custom.test.logger" for r in caplog.records)

    def test_logging_hooks_satisfies_protocol(self) -> None:
        # LoggingHooks satisfies RunnerHooks structurally (duck typing via @runtime_checkable)
        hooks = LoggingHooks()
        assert isinstance(hooks, RunnerHooks)
