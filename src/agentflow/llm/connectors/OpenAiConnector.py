"""Concrete LlmConnector implementation for all OpenAI-compatible backends.

Handles: openai, ollama, gemini, deepseek — every backend that speaks the
OpenAI Chat Completions API.  Uses the ``openai.OpenAI`` SDK with a custom
``base_url`` where needed.

The response is normalised into a ``ChatResponse`` value object so the rest
of the application never depends on the openai SDK types directly.
"""

from __future__ import annotations

import logging
from typing import Any

from openai import OpenAI

from git_root_to_syspath import agr
agr()

from src.agentflow.llm.ChatResponse import ChatResponse, ToolCallFunction, ToolCallInfo, UsageInfo
from src.agentflow.llm.LlmConfig import LlmConfig
from src.agentflow.llm.LlmConnector import LlmConnector

logger = logging.getLogger(__name__)


class OpenAiConnector(LlmConnector):
    """LlmConnector for all OpenAI-compatible backends.

    Builds and owns an ``openai.OpenAI`` client.  Routes chat requests to
    the Chat Completions endpoint and maps the SDK response to ``ChatResponse``.
    """

    def __init__(self, config: LlmConfig) -> None:
        """Initialise the connector and build the underlying OpenAI client.

        Args:
            config: Resolved ``LlmConfig`` for an OpenAI-compatible backend.
        """
        super().__init__()
        self._config = config
        self._client = self._build_client(config)
        logger.info(
            "OpenAiConnector ready: backend=%s model=%s",
            config.backend,
            config.model,
        )

    # ------------------------------------------------------------------
    # LlmConnector interface
    # ------------------------------------------------------------------

    @property
    def config(self) -> LlmConfig:
        return self._config

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        model_override: str | None = None,
    ) -> ChatResponse:
        """Send a chat completion request and return a normalised response.

        Args:
            messages: OpenAI-format message list.
            tools: Optional list of OpenAI-format tool definitions.  When
                   provided, ``tool_choice`` is set to ``"auto"``.
            temperature: Sampling temperature.
            model_override: Per-call model name override.

        Returns:
            ``ChatResponse`` with role, content, tool_calls, and usage.

        Raises:
            openai.OpenAIError: On API-level errors (network, auth, quota).
        """
        model = model_override or self._config.model
        logger.debug(
            "LLM request: backend=%s model=%s messages=%d tools=%d",
            self._config.backend, model, len(messages), len(tools) if tools else 0,
        )

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        resp = self._client.chat.completions.create(**kwargs)
        response = self._parse_response(resp.choices[0].message, resp.usage)

        logger.debug(
            "LLM response: has_content=%s has_tool_calls=%s usage=%s",
            bool(response.content), response.has_tool_calls, response.usage,
        )
        return response

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_client(config: LlmConfig) -> OpenAI:
        """Create the ``openai.OpenAI`` client for the given config.

        Args:
            config: Resolved configuration.

        Returns:
            Configured ``OpenAI`` client instance.
        """
        kwargs: dict[str, Any] = {
            "timeout": config.timeout,
            # The SDK requires a non-empty string; Ollama ignores the value.
            "api_key": config.api_key or "local",
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        return OpenAI(**kwargs)

    @staticmethod
    def _parse_response(msg: Any, usage: Any) -> ChatResponse:
        """Convert the openai SDK message object to a typed ``ChatResponse``.

        Preserves backend-specific extra fields on tool calls (e.g. Gemini's
        ``thought_signature``) so they can be echoed back in the next turn.

        Args:
            msg: ``openai.types.chat.ChatCompletionMessage`` object.
            usage: ``openai.types.CompletionUsage`` object or ``None``.

        Returns:
            Typed ``ChatResponse``.
        """
        tool_calls: list[ToolCallInfo] | None = None
        if getattr(msg, "tool_calls", None):
            tool_calls = []
            for tc in msg.tool_calls:
                fn_extra = dict(getattr(tc.function, "model_extra", None) or {})
                tc_extra = dict(getattr(tc, "model_extra", None) or {})
                tool_calls.append(
                    ToolCallInfo(
                        id=tc.id,
                        type=tc.type,
                        function=ToolCallFunction(
                            name=tc.function.name,
                            arguments=tc.function.arguments,
                            extra=fn_extra,
                        ),
                        extra=tc_extra,
                    )
                )

        usage_info: UsageInfo | None = None
        if usage:
            usage_info = UsageInfo(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            )

        return ChatResponse(
            role="assistant",
            content=msg.content or None,
            tool_calls=tool_calls,
            usage=usage_info,
        )
