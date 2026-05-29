"""Unit tests for ToolCallVertex adapter.

Tests verify: successful tool execution returning ok_signal + patch,
error handling returning fail_signal, and correct state-to-args extraction.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest

from src.agentflow.statemachine.adapters.tool_call_vertex import ToolCallVertex
from src.agentflow.statemachine.signal import StdSignal
from src.agentflow.statemachine.testing.fakes import make_fake_context
from src.agentflow.tools.Tool import ToolBase


# ---------------------------------------------------------------------------
# Minimal ToolBase implementations for tests
# ---------------------------------------------------------------------------


class EchoTool(ToolBase):
    """Echo tool — returns the JSON args string as the result."""

    def execute(self, text: str) -> str:
        """Echo the input back prefixed with 'echo:'.

        Args:
            text: The JSON argument string passed by ToolCallVertex.

        Returns:
            Input text prefixed with 'echo:'.
        """
        return f"echo:{text}"


class BrokenTool(ToolBase):
    """Tool that always raises RuntimeError — used to test fail_signal path."""

    def execute(self, **kwargs: Any) -> str:  # type: ignore[override]
        """Always raise RuntimeError to simulate a tool failure.

        Args:
            **kwargs: Ignored.

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("BrokenTool intentional failure")


# ---------------------------------------------------------------------------
# Test state dataclass
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _State:
    """Minimal frozen state for tests."""

    payload: str = "hello"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_call_vertex_executes_tool_and_returns_ok_signal_with_patch() -> None:
    """ToolCallVertex returns ok_signal and calls result_to_patch with tool output."""
    received: list[str] = []

    def args_from_state(state: Any) -> dict[str, Any]:
        return {"text": "ignored"}

    def result_to_patch(result: str) -> str:
        received.append(result)
        return f"patch:{result}"

    vertex = ToolCallVertex(
        tool=EchoTool(),
        args_from_state=args_from_state,
        result_to_patch=result_to_patch,
    )
    ctx = make_fake_context()
    signal, patch = await vertex.run(_State(), ctx)

    assert signal is StdSignal.ok
    assert len(received) == 1
    # EchoTool receives json.dumps({"text": "ignored"}) as its text arg
    expected_result = f'echo:{json.dumps({"text": "ignored"})}'
    assert received[0] == expected_result
    assert patch == f"patch:{expected_result}"


@pytest.mark.asyncio
async def test_tool_call_vertex_returns_fail_signal_on_tool_exception() -> None:
    """ToolCallVertex returns fail_signal when the tool raises an exception."""

    def args_from_state(state: Any) -> dict[str, Any]:
        return {}

    def result_to_patch(result: str) -> str:
        return f"patch:{result}"

    vertex = ToolCallVertex(
        tool=BrokenTool(),
        args_from_state=args_from_state,
        result_to_patch=result_to_patch,
    )
    ctx = make_fake_context()
    signal, patch = await vertex.run(_State(), ctx)

    assert signal is StdSignal.fail
    # result_to_patch is called with "" on failure
    assert patch == "patch:"


@pytest.mark.asyncio
async def test_tool_call_vertex_extracts_args_from_state_correctly() -> None:
    """args_from_state receives the exact state object passed to run()."""
    captured_states: list[Any] = []

    def args_from_state(state: Any) -> dict[str, Any]:
        captured_states.append(state)
        return {"text": state.payload}

    def result_to_patch(result: str) -> dict[str, str]:
        return {"result": result}

    state = _State(payload="world")
    vertex = ToolCallVertex(
        tool=EchoTool(),
        args_from_state=args_from_state,
        result_to_patch=result_to_patch,
    )
    ctx = make_fake_context()
    await vertex.run(state, ctx)

    assert len(captured_states) == 1
    assert captured_states[0] is state
    assert captured_states[0].payload == "world"
