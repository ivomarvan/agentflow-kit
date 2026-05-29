"""Unit tests for FakeLlmConnector.achat() and ToolAgent.arun().

All tests are async and use pytest-asyncio (mark.asyncio per-test, no global mode).
"""

from __future__ import annotations

import pytest
from git_root_to_syspath import agr

agr()

from src.agentflow.agents.ToolAgent import ToolAgent
from src.agentflow.llm.ChatResponse import ChatResponse
from src.agentflow.statemachine.testing.fakes import FakeLlmConnector
from src.agentflow.tools.ToolRegistry import ToolRegistry


# ---------------------------------------------------------------------------
# FakeLlmConnector.achat — basic behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_connector_achat_returns_chat_response() -> None:
    """achat() returns a ChatResponse for a queued string."""
    connector = FakeLlmConnector()
    connector.queue_responses(["Hello from async!"])

    response = await connector.achat([{"role": "user", "content": "hi"}])

    assert isinstance(response, ChatResponse)
    assert response.text == "Hello from async!"
    assert response.role == "assistant"


@pytest.mark.asyncio
async def test_fake_connector_achat_dequeues_responses_in_order() -> None:
    """achat() returns queued responses in FIFO order across multiple calls."""
    connector = FakeLlmConnector()
    connector.queue_responses(["first", "second"])

    r1 = await connector.achat([{"role": "user", "content": "a"}])
    r2 = await connector.achat([{"role": "user", "content": "b"}])

    assert r1.text == "first"
    assert r2.text == "second"


@pytest.mark.asyncio
async def test_fake_connector_achat_raises_when_queue_empty() -> None:
    """achat() raises RuntimeError when the response queue is exhausted."""
    connector = FakeLlmConnector()

    with pytest.raises(RuntimeError, match="queue is empty"):
        await connector.achat([{"role": "user", "content": "anything"}])


# ---------------------------------------------------------------------------
# ToolAgent.arun — integration with FakeLlmConnector
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_agent_arun_returns_final_answer() -> None:
    """arun() returns the LLM answer when no tool calls are issued."""
    connector = FakeLlmConnector()
    connector.queue_responses(["42 is the answer."])

    agent = ToolAgent(
        connector=connector,
        tools=ToolRegistry(),
        system_prompt="You are a helpful assistant.",
        max_steps=5,
    )

    answer = await agent.arun("What is the answer to everything?")

    assert answer == "42 is the answer."


@pytest.mark.asyncio
async def test_tool_agent_arun_max_steps_exceeded_returns_error_string() -> None:
    """arun() returns an error string when max_steps is exhausted without a final answer.

    The fake connector always returns a response with no tool calls, but we
    exhaust the queue to trigger the max_steps path by setting max_steps=0.
    """
    connector = FakeLlmConnector()

    agent = ToolAgent(
        connector=connector,
        tools=ToolRegistry(),
        system_prompt="You are a helpful assistant.",
        max_steps=0,
    )

    answer = await agent.arun("Will this ever finish?")

    assert "AGENT ERROR" in answer
    assert "max_steps" in answer
