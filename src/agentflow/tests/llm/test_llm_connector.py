"""Integration tests for LlmConnector — live API calls.

These tests require a valid API key and network access.
Default model: gpt-4o-mini (very cheap, fast, reliable).

Run with:
  pytest -m integration

Skip in CI environments without an API key by using:
  pytest -m "not integration"
"""

from __future__ import annotations

import pytest
from git_root_to_syspath import agr

agr()

from src.agentflow.llm.ChatResponse import ChatResponse
from src.agentflow.llm.LlmConnector import LlmConnector
from src.agentflow.tools.ToolRegistry import ToolRegistry
from src.agentflow.tools.common_tools.Calculator import Calculator


# ---------------------------------------------------------------------------
# Basic ping — single text response
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_connector_returns_chat_response(integration_connector: LlmConnector) -> None:
    """LlmConnector.chat() returns a ChatResponse for a simple prompt."""
    messages = [{"role": "user", "content": "Reply with the single word: pong"}]
    response = integration_connector.chat(messages)
    assert isinstance(response, ChatResponse)


@pytest.mark.integration
def test_connector_response_has_text(integration_connector: LlmConnector) -> None:
    """Response text is a non-empty string."""
    messages = [{"role": "user", "content": "Reply with the single word: pong"}]
    response = integration_connector.chat(messages)
    assert len(response.text) > 0


@pytest.mark.integration
def test_connector_response_role_is_assistant(integration_connector: LlmConnector) -> None:
    """The response role is 'assistant'."""
    messages = [{"role": "user", "content": "Hi"}]
    response = integration_connector.chat(messages)
    assert response.role == "assistant"


@pytest.mark.integration
def test_connector_usage_is_reported(integration_connector: LlmConnector) -> None:
    """Usage info is populated (at least total_tokens > 0)."""
    messages = [{"role": "user", "content": "What is 1+1?"}]
    response = integration_connector.chat(messages)
    if response.usage is not None:
        assert response.usage.total_tokens > 0


# ---------------------------------------------------------------------------
# Tool calling — Calculator
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_connector_calls_calculator_tool(integration_connector: LlmConnector) -> None:
    """LLM issues a calculator tool call for a math question."""
    registry = ToolRegistry()
    registry.register(Calculator())

    messages = [
        {
            "role": "user",
            "content": "Use the calculator tool to compute 17 * 18. Return only the result.",
        }
    ]
    response = integration_connector.chat(messages, tools=registry.schemas())

    # The model should have called the calculator tool
    assert response.has_tool_calls, (
        f"Expected at least one tool call, got text: {response.text!r}"
    )
    call = response.tool_calls[0]  # type: ignore[index]
    assert call.name == "calculator"
    assert "17" in call.arguments or "18" in call.arguments


@pytest.mark.integration
def test_tool_loop_produces_final_answer(integration_connector: LlmConnector) -> None:
    """Full agentic loop: question → tool call → tool result → final text answer."""
    registry = ToolRegistry()
    registry.register(Calculator())

    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                "Use the calculator tool to compute 123 * 456, "
                "then tell me the result in a sentence."
            ),
        }
    ]

    # First turn — should request tool call
    response = integration_connector.chat(messages, tools=registry.schemas())
    assert response.has_tool_calls

    # Append assistant turn
    messages.append(response.to_message_dict())

    # Execute each tool call and append results
    for tc in response.tool_calls:  # type: ignore[union-attr]
        result = registry.execute(tc.name, tc.arguments)
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": result,
        })

    # Second turn — should produce final text
    final = integration_connector.chat(messages, tools=registry.schemas())
    assert not final.has_tool_calls
    # Accept both "56088" and "56,088" (locale-formatted thousands separator)
    assert "56088" in final.text or "56,088" in final.text
