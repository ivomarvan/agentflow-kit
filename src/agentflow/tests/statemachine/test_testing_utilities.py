"""Unit tests for testing utilities: FakeVertex, FakeLlmConnector, make_fake_context."""

from __future__ import annotations

import pytest
import pytest_asyncio  # noqa: F401 — ensures asyncio plugin is active

from agentflow.statemachine.signal import StdSignal
from agentflow.statemachine.testing import FakeLlmConnector, FakeVertex, make_fake_context


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fake_vertex_returns_configured_signal_and_patch() -> None:
    """FakeVertex.run() must return exactly the signal and patch set at construction."""
    ctx = make_fake_context()
    patch = {"answer": 42}
    vertex = FakeVertex(signal=StdSignal.ok, patch=patch)

    signal, returned_patch = await vertex.run(object(), ctx)

    assert signal is StdSignal.ok
    assert returned_patch is patch


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fake_vertex_counts_calls() -> None:
    """FakeVertex.calls must increment by one on each run() invocation."""
    ctx = make_fake_context()
    vertex = FakeVertex(signal=StdSignal.done, patch=None)

    assert vertex.calls == 0
    await vertex.run(object(), ctx)
    assert vertex.calls == 1
    await vertex.run(object(), ctx)
    assert vertex.calls == 2


@pytest.mark.unit
def test_fake_llm_connector_returns_queued_responses_in_order() -> None:
    """FakeLlmConnector.chat() must return queued responses FIFO."""
    connector = FakeLlmConnector()
    connector.queue_responses(["first", "second", "third"])

    r1 = connector.chat([])
    r2 = connector.chat([])
    r3 = connector.chat([])

    assert r1.text == "first"
    assert r2.text == "second"
    assert r3.text == "third"


@pytest.mark.unit
def test_fake_llm_connector_raises_when_queue_empty() -> None:
    """FakeLlmConnector.chat() must raise RuntimeError when no responses are queued."""
    connector = FakeLlmConnector()

    with pytest.raises(RuntimeError, match="queue is empty"):
        connector.chat([])


@pytest.mark.unit
def test_make_fake_context_provides_default_logger_and_run_id() -> None:
    """make_fake_context() must return Context with deterministic logger and run_id."""
    ctx = make_fake_context()

    assert ctx.logger.name == "statemachine.test"
    assert ctx.run_id == "test-run-id"
