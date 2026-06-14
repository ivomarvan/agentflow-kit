"""Concrete LlmConnector implementation for all OpenAI-compatible backends.

Handles: openai, ollama, gemini, deepseek — every backend that speaks the
OpenAI Chat Completions API.  Uses the ``openai.OpenAI`` SDK with a custom
``base_url`` where needed.

The response is normalised into a ``ChatResponse`` value object so the rest
of the application never depends on the openai SDK types directly.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from openai import AsyncOpenAI, OpenAI

from agentflow.llm.ChatResponse import ChatResponse, ToolCallFunction, ToolCallInfo, UsageInfo
from agentflow.llm.LlmConfig import LlmConfig
from agentflow.llm.LlmConnectorBase import LlmConnectorBase

logger = logging.getLogger(__name__)


def _to_openai_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively adapt a Pydantic JSON schema for OpenAI Structured Outputs.

    OpenAI strict mode requires every object node to have:
      - ``additionalProperties: false``
      - all property keys present in ``required``

    Pydantic ``model_json_schema()`` omits both by default, so this function
    adds them throughout the entire schema tree (``properties``, ``$defs``,
    ``anyOf``/``allOf``/``oneOf``, array ``items``).

    Args:
        schema: Raw JSON schema dict produced by ``model_json_schema()``.

    Returns:
        A new dict (deep copy) conforming to OpenAI strict schema rules.
    """
    schema = dict(schema)

    if "properties" in schema:
        # Ensure every property key appears in required.
        existing_required: set[str] = set(schema.get("required", []))
        schema["required"] = sorted(existing_required | set(schema["properties"].keys()))
        schema["additionalProperties"] = False
        schema["properties"] = {
            k: _to_openai_strict_schema(v) for k, v in schema["properties"].items()
        }

    # Recurse into sub-schemas.
    for key in ("anyOf", "allOf", "oneOf"):
        if key in schema:
            schema[key] = [_to_openai_strict_schema(s) for s in schema[key]]
    if "items" in schema:
        schema["items"] = _to_openai_strict_schema(schema["items"])
    if "$defs" in schema:
        schema["$defs"] = {k: _to_openai_strict_schema(v) for k, v in schema["$defs"].items()}

    return schema


class OpenAiConnector(LlmConnectorBase):
    """LlmConnectorBase implementation for all OpenAI-compatible backends.

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
        # Lazy-initialised on first _do_achat() call to avoid startup overhead
        # when only the sync path is used.
        self._async_client_cache: AsyncOpenAI | None = None
        logger.debug(
            "OpenAiConnector ready: backend=%s model=%s",
            config.backend,
            config.model,
        )

    # ------------------------------------------------------------------
    # LlmConnectorBase interface
    # ------------------------------------------------------------------

    @property
    def config(self) -> LlmConfig:
        return self._config

    # ------------------------------------------------------------------
    # Async client — lazy property (Pattern: Lazy Initialization)
    # ------------------------------------------------------------------

    @property
    def _async_client(self) -> AsyncOpenAI:
        """Return the shared ``AsyncOpenAI`` client, creating it on first access.

        Returns:
            Configured ``AsyncOpenAI`` client instance.
        """
        if self._async_client_cache is None:
            kwargs: dict[str, Any] = {
                "timeout": self._config.timeout,
                "api_key": self._config.api_key or "local",
            }
            if self._config.base_url:
                kwargs["base_url"] = self._config.base_url
            self._async_client_cache = AsyncOpenAI(**kwargs)
        return self._async_client_cache

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
        """Send a chat completion request and return a normalised response.

        Args:
            messages: OpenAI-format message list.
            tools: Optional list of OpenAI-format tool definitions.
            temperature: Sampling temperature.
            model_override: Per-call model name override.
            response_schema: Optional Pydantic BaseModel for structured JSON output.
            max_tokens: Maximum output tokens, or None for backend default.
            stop: Stop sequences; generation halts at the first match.
            seed: Random seed for reproducible output.
            anthropic_cache_system: Ignored for OpenAI backends.

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
        kwargs = self._build_chat_kwargs(
            model, messages, tools, temperature, response_schema, max_tokens, stop, seed,
        )
        resp = self._client.chat.completions.create(**kwargs)
        response = self._parse_response(resp.choices[0].message, resp.usage)
        logger.debug(
            "LLM response: has_content=%s has_tool_calls=%s usage=%s",
            bool(response.content), response.has_tool_calls, response.usage,
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
        """Async counterpart to _do_chat() — uses AsyncOpenAI client natively.

        Args:
            messages: OpenAI-format message list.
            tools: Optional tool definitions.
            temperature: Sampling temperature.
            model_override: Per-call model name override.
            response_schema: Optional Pydantic BaseModel for structured JSON output.
            max_tokens: Maximum output tokens.
            stop: Stop sequences.
            seed: Random seed for reproducible output.
            anthropic_cache_system: Ignored for OpenAI backends.

        Returns:
            ``ChatResponse`` with role, content, tool_calls, and usage.

        Raises:
            openai.OpenAIError: On API-level errors (network, auth, quota).
        """
        model = model_override or self._config.model
        logger.debug(
            "LLM async request: backend=%s model=%s messages=%d tools=%d",
            self._config.backend, model, len(messages), len(tools) if tools else 0,
        )
        kwargs = self._build_chat_kwargs(
            model, messages, tools, temperature, response_schema, max_tokens, stop, seed,
        )
        resp = await self._async_client.chat.completions.create(**kwargs)
        response = self._parse_response(resp.choices[0].message, resp.usage)
        logger.debug(
            "LLM async response: has_content=%s has_tool_calls=%s usage=%s",
            bool(response.content), response.has_tool_calls, response.usage,
        )
        return response

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_reasoning_model(model: str) -> bool:
        """Return True for OpenAI reasoning models that do not accept ``temperature``.

        The ``o1``, ``o3``, ``o4`` (and future ``oN``) series use a different
        inference mechanism and reject the ``temperature`` parameter with a
        400 BadRequestError.  The pattern matches any model whose name starts
        with ``o`` followed by a digit (e.g. ``o1``, ``o1-mini``, ``o3-mini``).

        Args:
            model: Model name string.

        Returns:
            ``True`` when the model does not support ``temperature``.
        """
        return bool(re.match(r"^o\d", model))

    def _build_chat_kwargs(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        response_schema: type | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """Assemble the kwargs dict for a ``chat.completions.create`` call.

        Omits ``temperature`` for reasoning models that reject the parameter.
        When ``response_schema`` is a Pydantic BaseModel subclass, adds
        ``response_format`` with the JSON schema for Structured Outputs.

        Args:
            model: Resolved model name (after override).
            messages: OpenAI-format message list.
            tools: Optional tool definitions; adds ``tool_choice`` when present.
            temperature: Sampling temperature (ignored for reasoning models).
            response_schema: Optional Pydantic BaseModel subclass.  When set,
                instructs the API to return JSON matching the schema.
            max_tokens: Maximum output tokens; omitted when ``None``.
            stop: Stop sequences; omitted when ``None``.
            seed: Deterministic seed; omitted when ``None``.

        Returns:
            Keyword argument dict ready to unpack into ``create(**kwargs)``.
        """
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if not self._is_reasoning_model(model):
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if response_schema is not None:
            # OpenAI Structured Outputs — compatible with gpt-4o-2024-08-06+
            # and Gemini via the OpenAI-compatible endpoint.
            # Strict mode requires additionalProperties=false and all keys in
            # required on every object node — Pydantic doesn't add these by default.
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema.__name__,
                    "schema": _to_openai_strict_schema(response_schema.model_json_schema()),
                    "strict": True,
                },
            }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if stop is not None:
            kwargs["stop"] = stop
        if seed is not None:
            kwargs["seed"] = seed
        return kwargs

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
