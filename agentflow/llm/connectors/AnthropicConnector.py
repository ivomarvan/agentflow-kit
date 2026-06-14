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

Structured output (``response_schema``):
  Anthropic has no native ``response_format`` equivalent.  When a schema is
  supplied, this connector appends a concise JSON instruction to the system
  prompt, asking the model to respond exclusively with valid JSON matching
  the schema.  This is less strict than OpenAI Structured Outputs but works
  reliably with Claude models.

Tool-call support for Anthropic is planned as a follow-up (see TOOL_USE note
in ``_parse_response``).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from agentflow.llm.ChatResponse import ChatResponse, UsageInfo
from agentflow.llm.LlmConfig import LlmConfig
from agentflow.llm.LlmConnectorBase import LlmConnectorBase

logger = logging.getLogger(__name__)

_MAX_TOKENS_DEFAULT = 4096


class AnthropicConnector(LlmConnectorBase):
    """LlmConnectorBase implementation for the Anthropic (Claude) backend.

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
        super().__init__()
        self._config = config
        self._client = anthropic.Anthropic(api_key=config.api_key)
        # Lazy-initialised on first _do_achat() call to avoid startup overhead
        # when only the sync path is used.
        self._async_client_cache: anthropic.AsyncAnthropic | None = None
        logger.debug(
            "AnthropicConnector ready: model=%s",
            config.model,
        )

    # ------------------------------------------------------------------
    # Async client — lazy property (Pattern: Lazy Initialization)
    # ------------------------------------------------------------------

    @property
    def _async_client(self) -> anthropic.AsyncAnthropic:
        """Return the shared ``AsyncAnthropic`` client, creating it on first access.

        Returns:
            Configured ``AsyncAnthropic`` client instance.
        """
        if self._async_client_cache is None:
            self._async_client_cache = anthropic.AsyncAnthropic(api_key=self._config.api_key)
        return self._async_client_cache

    # ------------------------------------------------------------------
    # LlmConnectorBase interface
    # ------------------------------------------------------------------

    @property
    def config(self) -> LlmConfig:
        return self._config

    def _do_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        model_override: str | None,
        response_schema: type | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        seed: int | None = None,
        anthropic_cache_system: bool = False,
    ) -> ChatResponse:
        """Send a chat request to the Anthropic Messages API.

        Args:
            messages: OpenAI-format message list.
            tools: Tool definitions (not yet implemented — logged as warning).
            temperature: Sampling temperature (0.0 – 1.0).
            model_override: Per-call model name override.
            response_schema: Optional Pydantic BaseModel subclass; a JSON schema
                instruction is appended to the system prompt.
            max_tokens: Maximum output tokens.  Defaults to ``_MAX_TOKENS_DEFAULT``.
            stop: Stop sequences passed as ``stop_sequences`` to the Anthropic API.
            seed: Ignored — Anthropic does not support a seed parameter.
            anthropic_cache_system: When ``True``, marks the system message for
                Anthropic prompt caching (``cache_control: ephemeral``).

        Returns:
            ``ChatResponse`` with role, content, and usage.

        Raises:
            anthropic.APIError: On API-level errors (network, auth, quota).
        """
        model = model_override or self._config.model

        if tools:
            logger.warning(
                "AnthropicConnector: tools parameter is not yet implemented "
                "(%d tools ignored)", len(tools)
            )
        if seed is not None:
            logger.debug("AnthropicConnector: seed=%d ignored (not supported by Anthropic)", seed)

        kwargs = self._build_messages_kwargs(
            model, messages, temperature, response_schema,
            max_tokens, stop, anthropic_cache_system,
        )
        logger.debug(
            "Anthropic request: model=%s messages=%d system=%s schema=%s cache=%s",
            model, len(kwargs["messages"]), bool(kwargs.get("system")),
            response_schema.__name__ if response_schema else None,
            anthropic_cache_system,
        )
        resp = self._client.messages.create(**kwargs)
        response = self._parse_response(resp)
        logger.debug(
            "Anthropic response: stop_reason=%s has_content=%s usage=%s",
            resp.stop_reason, bool(response.content), response.usage,
        )
        return response

    async def _do_achat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        model_override: str | None,
        response_schema: type | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        seed: int | None = None,
        anthropic_cache_system: bool = False,
    ) -> ChatResponse:
        """Async counterpart to _do_chat() — uses AsyncAnthropic client natively.

        Args:
            messages: OpenAI-format message list.
            tools: Tool definitions (not yet implemented — logged as warning).
            temperature: Sampling temperature (0.0 – 1.0).
            model_override: Per-call model name override.
            response_schema: Optional Pydantic BaseModel subclass for structured output.
            max_tokens: Maximum output tokens.
            stop: Stop sequences.
            seed: Ignored (Anthropic does not support seed).
            anthropic_cache_system: Mark system message for Anthropic prompt caching.

        Returns:
            ``ChatResponse`` with role, content, and usage.

        Raises:
            anthropic.APIError: On API-level errors (network, auth, quota).
        """
        model = model_override or self._config.model

        if tools:
            logger.warning(
                "AnthropicConnector: tools parameter is not yet implemented "
                "(%d tools ignored)", len(tools)
            )
        if seed is not None:
            logger.debug("AnthropicConnector: seed=%d ignored (not supported by Anthropic)", seed)

        kwargs = self._build_messages_kwargs(
            model, messages, temperature, response_schema,
            max_tokens, stop, anthropic_cache_system,
        )
        logger.debug(
            "Anthropic async request: model=%s messages=%d system=%s schema=%s cache=%s",
            model, len(kwargs["messages"]), bool(kwargs.get("system")),
            response_schema.__name__ if response_schema else None,
            anthropic_cache_system,
        )
        resp = await self._async_client.messages.create(**kwargs)
        response = self._parse_response(resp)
        logger.debug(
            "Anthropic async response: stop_reason=%s has_content=%s usage=%s",
            resp.stop_reason, bool(response.content), response.usage,
        )
        return response

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_messages_kwargs(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        response_schema: type | None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        anthropic_cache_system: bool = False,
    ) -> dict[str, Any]:
        """Assemble the kwargs dict for an Anthropic ``messages.create`` call.

        Extracts system messages into the dedicated ``system=`` parameter.
        When ``response_schema`` is provided, appends a JSON schema instruction
        to the system prompt — Anthropic has no native ``response_format``
        equivalent, so prompt-level instruction is the standard workaround.
        When ``anthropic_cache_system`` is ``True``, the system parameter is
        encoded as a list of content blocks with ``cache_control: ephemeral``
        to enable Anthropic's prompt caching feature.

        Args:
            model: Resolved model name.
            messages: Full OpenAI-format message list including system entries.
            temperature: Sampling temperature.
            response_schema: Optional Pydantic BaseModel subclass.
            max_tokens: Maximum output tokens; uses ``_MAX_TOKENS_DEFAULT`` when ``None``.
            stop: Stop sequences passed as ``stop_sequences``; omitted when ``None``.
            anthropic_cache_system: When ``True``, marks the system content block
                for Anthropic prompt caching.

        Returns:
            Keyword argument dict ready to unpack into ``messages.create(**kwargs)``.
        """
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        user_messages = [m for m in messages if m["role"] != "system"]

        if response_schema is not None:
            schema_json = json.dumps(response_schema.model_json_schema(), indent=2)
            system_parts.append(
                f"Respond ONLY with a single valid JSON object that strictly matches "
                f"this schema. No explanation, no markdown fences, no extra text:\n{schema_json}"
            )

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens if max_tokens is not None else _MAX_TOKENS_DEFAULT,
            "temperature": temperature,
            "messages": user_messages,
        }
        if system_parts:
            system_text = "\n\n".join(system_parts)
            if anthropic_cache_system:
                # Encode as content block list to attach cache_control.
                kwargs["system"] = [
                    {
                        "type": "text",
                        "text": system_text,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
                kwargs["system"] = system_text
        if stop is not None:
            kwargs["stop_sequences"] = stop
        return kwargs

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
