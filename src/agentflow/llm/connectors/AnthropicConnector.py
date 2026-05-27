"""Concrete LlmConnector implementation for the Anthropic (Claude) backend.

The Anthropic Messages API differs from the OpenAI Chat Completions API in
three important ways handled here:

  1. ``system`` messages are NOT part of the ``messages`` list — they are
     passed as a separate ``system=`` parameter.  This connector extracts
     them automatically.

  2. ``max_tokens`` is REQUIRED by the Anthropic API (no server-side default).
     A sensible default of 4096 is used; override via ``max_tokens`` kwarg.

  3. Usage counters use ``input_tokens`` / ``output_tokens`` instead of
     ``prompt_tokens`` / ``completion_tokens`` — mapped to ``UsageInfo`` here.

Tool-call support for Anthropic is planned as a follow-up (see TOOL_USE note
in ``_parse_response``).
"""

from __future__ import annotations

import logging
from typing import Any

import anthropic

from git_root_to_syspath import agr
agr()

from src.agentflow.llm.ChatResponse import ChatResponse, UsageInfo
from src.agentflow.llm.LlmConfig import LlmConfig
from src.agentflow.llm.LlmConnector import LlmConnector

logger = logging.getLogger(__name__)

_MAX_TOKENS_DEFAULT = 4096


class AnthropicConnector(LlmConnector):
    """LlmConnector for the Anthropic (Claude) backend.

    Uses the native ``anthropic.Anthropic`` SDK.  Adapts the Anthropic
    Messages API response to the shared ``ChatResponse`` value object so
    calling code never needs to know which backend it is talking to.
    """

    def __init__(self, config: LlmConfig) -> None:
        """Initialise the connector and build the Anthropic client.

        The API key is read from ``config.api_key`` (loaded from
        ``ANTHROPIC_API_KEY`` by ``LlmConfig.from_env()``).

        Args:
            config: Resolved ``LlmConfig`` for the anthropic backend.
        """
        self._config = config
        self._client = anthropic.Anthropic(api_key=config.api_key)
        logger.info(
            "AnthropicConnector ready: model=%s",
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
        max_tokens: int = _MAX_TOKENS_DEFAULT,
    ) -> ChatResponse:
        """Send a chat request to the Anthropic Messages API.

        Extracts any ``system`` role messages from the list and passes them
        via the dedicated ``system=`` parameter.  The remaining messages are
        forwarded as-is.

        Args:
            messages: OpenAI-format message list.  ``system`` role entries are
                      extracted automatically; ``user`` and ``assistant`` entries
                      are forwarded to Anthropic unchanged.
            tools: Tool definitions (not yet implemented for Anthropic — logged as warning).
            temperature: Sampling temperature (0.0 – 1.0).
            model_override: Per-call model name override.  Uses ``config.model``
                            when ``None``.
            max_tokens: Maximum tokens to generate.  Anthropic requires an
                        explicit value; defaults to ``4096``.

        Returns:
            ``ChatResponse`` with role, content, and usage.

        Raises:
            anthropic.APIError: On API-level errors (network, auth, quota).
        """
        model = model_override or self._config.model

        if tools:
            # TOOL_USE: Anthropic tool calling format differs from OpenAI.
            # Full implementation is a planned follow-up task.
            logger.warning(
                "AnthropicConnector: tools parameter is not yet implemented "
                "(%d tools ignored)", len(tools)
            )

        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        user_messages = [m for m in messages if m["role"] != "system"]

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": user_messages,
        }
        if system_parts:
            # Anthropic accepts a single string; join multiple system messages.
            kwargs["system"] = "\n".join(system_parts)

        logger.debug(
            "Anthropic request: model=%s messages=%d system=%s",
            model, len(user_messages), bool(system_parts),
        )

        resp = self._client.messages.create(**kwargs)
        response = self._parse_response(resp)

        logger.debug(
            "Anthropic response: stop_reason=%s has_content=%s usage=%s",
            resp.stop_reason, bool(response.content), response.usage,
        )
        return response

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(resp: Any) -> ChatResponse:
        """Convert an Anthropic ``Message`` object to a typed ``ChatResponse``.

        Currently maps text blocks only.  Tool-use blocks (``stop_reason ==
        "tool_use"``) are logged as a warning until tool support is added.

        Args:
            resp: ``anthropic.types.Message`` object.

        Returns:
            Typed ``ChatResponse``.
        """
        text: str | None = None

        for block in resp.content:
            if block.type == "text":
                text = block.text
            elif block.type == "tool_use":
                # TOOL_USE: Anthropic tool calling is not yet mapped to
                # ToolCallInfo.  Implement when adding tool support.
                logger.warning(
                    "AnthropicConnector: tool_use block received but not yet "
                    "mapped to ToolCallInfo (tool id=%s name=%s)",
                    block.id,
                    block.name,
                )

        usage = UsageInfo(
            prompt_tokens=resp.usage.input_tokens,
            completion_tokens=resp.usage.output_tokens,
            total_tokens=resp.usage.input_tokens + resp.usage.output_tokens,
        )

        return ChatResponse(
            role="assistant",
            content=text,
            tool_calls=None,
            usage=usage,
        )
