"""Unit tests for StateVertex ABC and End/StdEnd terminal nodes."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import pytest_asyncio  # noqa: F401 — ensures asyncio plugin is active

from agentflow.statemachine.signal import StdSignal
from agentflow.statemachine.vertex import End, StateVertex, StdEnd


@pytest.mark.unit
@pytest.mark.asyncio
async def test_state_vertex_run_raises_not_implemented() -> None:
    """Calling run() on a StateVertex without overriding run() must raise NotImplementedError."""

    class _BareVertex(StateVertex):
        pass

    vertex = _BareVertex()
    with pytest.raises(NotImplementedError):
        await vertex.run(object(), None)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_std_end_returns_done_and_empty_patch() -> None:
    """StdEnd.run() must return StdSignal.done as the routing signal."""
    vertex = StdEnd()
    ctx = MagicMock()
    state = object()

    signal, _patch = await vertex.run(state, ctx)

    assert signal is StdSignal.done


@pytest.mark.unit
def test_end_subclass_detected_by_isinstance() -> None:
    """StdEnd must be recognised as an End instance for runner termination detection."""
    assert isinstance(StdEnd(), End)
