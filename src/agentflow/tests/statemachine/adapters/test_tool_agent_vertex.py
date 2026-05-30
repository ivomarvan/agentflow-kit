"""Unit tests for ToolAgentVertex adapter.

Tests verify: correct question extraction from state passed to agent.arun(),
and correct mapping of agent answer to patch with ok_signal returned.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from agentflow.agents.ToolAgent import ToolAgent
from agentflow.statemachine.adapters.tool_agent_vertex import ToolAgentVertex
from agentflow.statemachine.signal import StdSignal
from agentflow.statemachine.testing.fakes import make_fake_context


@pytest.mark.asyncio
async def test_tool_agent_vertex_calls_arun_with_question_from_state() -> None:
    """ToolAgentVertex extracts the question from state and passes it to agent.arun()."""
    mock_agent = AsyncMock(spec=ToolAgent)
    mock_agent.arun.return_value = "42"

    vertex = ToolAgentVertex(
        agent=mock_agent,
        question_from_state=lambda state: state.question,
        answer_to_patch=lambda ans: SimpleNamespace(answer=ans),
    )
    state = SimpleNamespace(question="What is 6 × 7?")
    ctx = make_fake_context()
    signal, patch = await vertex.run(state, ctx)

    mock_agent.arun.assert_called_once_with("What is 6 × 7?")
    assert signal == StdSignal.ok


@pytest.mark.asyncio
async def test_tool_agent_vertex_maps_answer_to_patch_with_ok_signal() -> None:
    """ToolAgentVertex maps agent answer to patch via answer_to_patch and returns ok_signal."""
    mock_agent = AsyncMock(spec=ToolAgent)
    mock_agent.arun.return_value = "the answer is 42"

    patches_received: list[str] = []

    def answer_to_patch(ans: str) -> dict[str, Any]:
        patches_received.append(ans)
        return {"answer": ans}

    vertex = ToolAgentVertex(
        agent=mock_agent,
        question_from_state=lambda state: getattr(state, "question", ""),
        answer_to_patch=answer_to_patch,
    )
    state = SimpleNamespace(question="What is the answer?")
    ctx = make_fake_context()
    signal, patch = await vertex.run(state, ctx)

    assert signal is StdSignal.ok
    assert len(patches_received) == 1
    assert patches_received[0] == "the answer is 42"
    assert patch == {"answer": "the answer is 42"}
