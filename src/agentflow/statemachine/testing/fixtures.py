"""pytest fixtures for agentflow.statemachine tests.

Import in conftest.py or directly in test modules:
    from src.agentflow.statemachine.testing.fixtures import (
        fake_ctx,
        make_state_graph,
        recorded_runner,
    )
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from src.agentflow.statemachine.context import Context
from src.agentflow.statemachine.hooks import RecorderHooks
from src.agentflow.statemachine.runner import StateGraphRunner
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


@pytest.fixture  # type: ignore[untyped-decorator]
def recorded_runner(
    fake_ctx: Context,
) -> Callable[[StateGraph], tuple[StateGraphRunner, RecorderHooks]]:
    """Factory fixture: given a StateGraph, returns a (runner, recorder) pair.

    The recorder captures the full super-step history so tests can assert
    on execution order, active nodes, and state evolution after the run.

    Usage::

        def test_something(recorded_runner):
            runner, recorder = recorded_runner(my_graph)
            runner.run_sync(initial_state)
            assert len(recorder.history) == expected

    Args:
        fake_ctx: Injected Context fixture backed by FakeLlmConnector.

    Returns:
        Callable[[StateGraph], tuple[StateGraphRunner, RecorderHooks]] —
        call with a StateGraph to obtain a configured (runner, recorder) pair.
    """

    def _factory(graph: StateGraph) -> tuple[StateGraphRunner, RecorderHooks]:
        recorder = RecorderHooks()
        return StateGraphRunner(graph, fake_ctx, hooks=recorder), recorder

    return _factory
