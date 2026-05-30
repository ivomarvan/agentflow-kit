"""Mock-based unit tests for the async achat() method in OpenAiConnector and AnthropicConnector.

These tests do NOT make network calls and do NOT require API keys.
They verify that:
  - achat() delegates to the correct async SDK client.
  - _parse_response() is used to map the SDK response to ChatResponse.
  - The system-message extraction logic in AnthropicConnector is applied in achat().
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentflow.llm.connectors.AnthropicConnector import AnthropicConnector
from agentflow.llm.connectors.OpenAiConnector import OpenAiConnector
from agentflow.llm.LlmConfig import LlmConfig

# ---------------------------------------------------------------------------
# OpenAiConnector.achat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_openai_connector_achat_delegates_to_async_client() -> None:
    """achat() calls AsyncOpenAI.chat.completions.create and parses its response."""
    config = LlmConfig(backend="openai", model="gpt-4o-mini", base_url=None, api_key="test-key", timeout=30.0)
    connector = OpenAiConnector(config)

    fake_message = MagicMock()
    fake_message.content = "Hello from async"
    fake_message.tool_calls = None

    fake_usage = MagicMock()
    fake_usage.prompt_tokens = 10
    fake_usage.completion_tokens = 5
    fake_usage.total_tokens = 15

    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock()]
    fake_resp.choices[0].message = fake_message
    fake_resp.usage = fake_usage

    async_create_mock = AsyncMock(return_value=fake_resp)

    with patch.object(connector, "_async_client_cache", None):
        mock_async_client = MagicMock()
        mock_async_client.chat.completions.create = async_create_mock

        # Inject the mock client directly into the cache so the lazy property returns it.
        connector._async_client_cache = mock_async_client  # type: ignore[assignment]

        messages = [{"role": "user", "content": "hello"}]
        result = await connector.achat(messages)

    assert result.content == "Hello from async"
    assert result.role == "assistant"
    assert result.usage is not None
    assert result.usage.total_tokens == 15
    async_create_mock.assert_called_once()
    call_kwargs = async_create_mock.call_args[1]
    assert call_kwargs["model"] == "gpt-4o-mini"
    assert call_kwargs["messages"] == messages


# ---------------------------------------------------------------------------
# AnthropicConnector.achat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anthropic_connector_achat_delegates_to_async_client() -> None:
    """achat() calls AsyncAnthropic.messages.create, extracts system messages, parses response."""
    config = LlmConfig(backend="anthropic", model="claude-3-haiku-20240307", base_url=None, api_key="test-key", timeout=30.0)
    connector = AnthropicConnector(config)

    # Build a fake Anthropic response: content is a list of blocks.
    fake_text_block = MagicMock()
    fake_text_block.type = "text"
    fake_text_block.text = "Paris is the capital of France."

    fake_usage = MagicMock()
    fake_usage.input_tokens = 20
    fake_usage.output_tokens = 8

    fake_resp = MagicMock()
    fake_resp.content = [fake_text_block]
    fake_resp.usage = fake_usage
    fake_resp.stop_reason = "end_turn"

    async_create_mock = AsyncMock(return_value=fake_resp)

    mock_async_client = MagicMock()
    mock_async_client.messages.create = async_create_mock
    connector._async_client_cache = mock_async_client  # type: ignore[assignment]

    messages = [
        {"role": "system", "content": "You are a helpful geography assistant."},
        {"role": "user", "content": "What is the capital of France?"},
    ]
    result = await connector.achat(messages)

    assert result.content == "Paris is the capital of France."
    assert result.role == "assistant"
    assert result.usage is not None
    assert result.usage.prompt_tokens == 20
    assert result.usage.completion_tokens == 8
    assert result.usage.total_tokens == 28

    async_create_mock.assert_called_once()
    call_kwargs = async_create_mock.call_args[1]

    # system message must be extracted and passed as the dedicated 'system' parameter
    assert call_kwargs["system"] == "You are a helpful geography assistant."
    # only the user message should appear in 'messages'
    assert len(call_kwargs["messages"]) == 1
    assert call_kwargs["messages"][0]["role"] == "user"
