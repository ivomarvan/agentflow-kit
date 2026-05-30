"""Unit tests for Context dataclass and run_sync helper."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import pytest_asyncio  # noqa: F401 — ensures asyncio plugin is active

from agentflow.statemachine.context import Context


def _make_context() -> Context:
    """Return a Context with a mock connector for testing."""
    connector = MagicMock()
    return Context(connector=connector)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_run_sync_executes_sync_callable() -> None:
    """run_sync should execute a blocking callable and return its value."""
    ctx = _make_context()

    result = await ctx.run_sync(lambda x: x * 2, 21)

    assert result == 42


@pytest.mark.unit
def test_context_run_id_is_unique_per_instance() -> None:
    """Each Context instance must generate a distinct run_id."""
    ctx_a = _make_context()
    ctx_b = _make_context()

    assert ctx_a.run_id != ctx_b.run_id


@pytest.mark.unit
def test_context_default_logger_named_statemachine() -> None:
    """Default logger must use the 'statemachine' namespace."""
    ctx = _make_context()

    assert ctx.logger.name == "statemachine"
