"""Unit tests for LlmTurnVertex adapter.

Tests verify: achat is called and ok_signal returned with patch,
tools parameter is forwarded to achat, and messages_from_state is invoked
with the correct state object.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from agentflow.llm.ChatResponse import ChatResponse
from agentflow.statemachine.adapters.llm_turn_vertex import LlmTurnVertex
from agentflow.statemachine.signal import StdSignal
from agentflow.statemachine.testing.fakes import FakeLlmConnector, make_fake_context

# ---------------------------------------------------------------------------
# Test state dataclass
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _State:
    """Minimal frozen state for tests."""

    user_text: str = "hello"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_turn_vertex_calls_achat_returns_ok_signal_with_patch() -> None:
    """LlmTurnVertex calls achat, maps the response, and returns ok_signal."""
    connector = FakeLlmConnector()
    connector.queue_responses(["LLM answer"])

    def messages_from_state(state: Any) -> list[dict[str, Any]]:
        return [{"role": "user", "content": state.user_text}]

    def response_to_patch(response: ChatResponse) -> str:
        return f"patch:{response.text}"

    vertex = LlmTurnVertex(
        messages_from_state=messages_from_state,
        response_to_patch=response_to_patch,
    )
    ctx = make_fake_context(connector=connector)
    signal, patch = await vertex.run(_State(), ctx)

    assert signal is StdSignal.ok
    assert patch == "patch:LLM answer"


@pytest.mark.asyncio
async def test_llm_turn_vertex_passes_tools_parameter_to_achat() -> None:
    """LlmTurnVertex forwards the tools list to connector.achat."""
    received_tools: list[Any] = []

    class CapturingConnector(FakeLlmConnector):
        def _do_chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None,
            temperature: float,
            model_override: str | None,
        ) -> ChatResponse:
            received_tools.append(tools)
            return ChatResponse(
                role="assistant", content="ok", tool_calls=None, usage=None
            )

    tool_schemas = [{"type": "function", "function": {"name": "my_tool"}}]

    vertex = LlmTurnVertex(
        messages_from_state=lambda state: [],
        response_to_patch=lambda r: r.text,
        tools=tool_schemas,
    )
    ctx = make_fake_context(connector=CapturingConnector())
    await vertex.run(_State(), ctx)

    assert len(received_tools) == 1
    assert received_tools[0] == tool_schemas


@pytest.mark.asyncio
async def test_llm_turn_vertex_builds_messages_from_state() -> None:
    """messages_from_state is called with the state object passed to run()."""
    captured_states: list[Any] = []
    connector = FakeLlmConnector()
    connector.queue_responses(["response"])

    def messages_from_state(state: Any) -> list[dict[str, Any]]:
        captured_states.append(state)
        return [{"role": "user", "content": state.user_text}]

    vertex = LlmTurnVertex(
        messages_from_state=messages_from_state,
        response_to_patch=lambda r: r.text,
    )
    state = _State(user_text="test message")
    ctx = make_fake_context(connector=connector)
    await vertex.run(state, ctx)

    assert len(captured_states) == 1
    assert captured_states[0] is state
    assert captured_states[0].user_text == "test message"
