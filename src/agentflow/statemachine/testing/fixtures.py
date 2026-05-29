"""pytest fixtures for agentflow.statemachine tests.

Import in conftest.py or directly in test modules:
    from src.agentflow.statemachine.testing.fixtures import fake_ctx, make_state_graph
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from src.agentflow.statemachine.context import Context
from src.agentflow.statemachine.testing.fakes import make_fake_context
from src.agentflow.statemachine.topology import StateGraph, Transition


@pytest.fixture  # type: ignore[untyped-decorator]
def fake_ctx() -> Context:
    """Pytest fixture providing a Context backed by FakeLlmConnector.

    Returns:
        Context with FakeLlmConnector, logger 'statemachine.test', and
        run_id 'test-run-id' — fully deterministic, no real LLM calls.
    """
    return make_fake_context()


@pytest.fixture  # type: ignore[untyped-decorator]
def make_state_graph() -> Callable[..., StateGraph]:
    """Factory fixture for building simple StateGraph instances in tests.

    Returns:
        Callable accepting (start, transitions) that constructs a StateGraph.
        ``start`` must be a StateVertex instance; ``transitions`` a list of
        Transition objects.
    """

    def _factory(start: Any, transitions: list[Transition]) -> StateGraph:
        return StateGraph(start=start, transitions=transitions)

    return _factory
