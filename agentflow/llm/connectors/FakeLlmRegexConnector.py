"""Regex-rule-based fake LLM connector for deterministic testing.

``FakeLlmRegexConnector`` accepts a list of ``(pattern, response)`` pairs
in its constructor.  Each ``chat()`` call matches the last user message
against the patterns in order and returns the first matching response.
When no pattern matches, the ``default`` response is returned.

This makes it easy to define realistic fake behaviours without managing an
explicit response queue::

    from agentflow.llm.connectors import FakeLlmRegexConnector

    connector = FakeLlmRegexConnector(
        rules=[
            (r"weather", "It's sunny and 20°C."),
            (r"calculate|compute|\d+\s*[+\\-*/]", "The answer is 42."),
        ],
        default="I don't know.",
    )

Supports optional cache injection (inherited from ``LlmConnectorBase``).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from agentflow.llm.ChatResponse import ChatResponse
from agentflow.llm.LlmConnectorBase import LlmConnectorBase

if TYPE_CHECKING:
    from agentflow.llm.cache.LlmCacheBase import LlmCacheBase
    from agentflow.llm.LlmConfig import LlmConfig

logger = logging.getLogger(__name__)


class FakeLlmRegexConnector(LlmConnectorBase):
    """Fake LLM connector that matches the last user message against regex rules.

    Rules are evaluated in order; the first match wins.  When no rule matches,
    the ``default`` response is returned.

    Args:
        rules: List of ``(pattern, response)`` pairs.  Patterns are compiled
               with ``re.IGNORECASE | re.DOTALL``.
        default: Response string returned when no pattern matches.
        cache: Optional cache instance.  Defaults to ``None``.
    """

    def __init__(
        self,
        rules: list[tuple[str, str]],
        *,
        default: str = "OK.",
        cache: LlmCacheBase | None = None,
    ) -> None:
        super().__init__(cache=cache)
        self._rules: list[tuple[re.Pattern[str], str]] = [
            (re.compile(pattern, re.IGNORECASE | re.DOTALL), response)
            for pattern, response in rules
        ]
        self._default = default

    # ------------------------------------------------------------------
    # LlmConnectorBase interface
    # ------------------------------------------------------------------

    @property
    def config(self) -> LlmConfig:
        """Not implemented — FakeLlmRegexConnector has no real backend configuration.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("FakeLlmRegexConnector has no real LlmConfig")

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
        """Match the last user message against rules and return a response.

        Args:
            messages: Conversation history; only the last user message is matched.
            tools: Ignored.
            temperature: Ignored.
            model_override: Ignored.
            response_schema: Ignored — preset strings are returned as-is.
            max_tokens: Ignored.
            stop: Ignored.
            seed: Ignored.
            anthropic_cache_system: Ignored.

        Returns:
            ``ChatResponse`` whose content is the matching rule's response,
            or ``default`` when no pattern matches.
        """
        last_user = self._last_user_content(messages)
        for pattern, response in self._rules:
            if pattern.search(last_user):
                logger.debug("regex match: pattern=%r content=%.40r", pattern.pattern, response)
                return ChatResponse(role="assistant", content=response, tool_calls=None, usage=None)
        logger.debug("no regex match; using default: %.40r", self._default)
        return ChatResponse(role="assistant", content=self._default, tool_calls=None, usage=None)

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
        """Async counterpart — delegates synchronously (no I/O).

        Args:
            messages: Conversation history.
            tools: Ignored.
            temperature: Ignored.
            model_override: Ignored.
            response_schema: Ignored.
            max_tokens: Ignored.
            stop: Ignored.
            seed: Ignored.
            anthropic_cache_system: Ignored.

        Returns:
            ``ChatResponse`` from the matching rule or default.
        """
        return self._do_chat(
            messages, tools, temperature, model_override,
            response_schema, max_tokens, stop, seed, anthropic_cache_system,
        )

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _last_user_content(messages: list[dict[str, Any]]) -> str:
        """Extract the content of the last user-role message.

        Args:
            messages: Conversation history.

        Returns:
            Content string of the last user message, or empty string.
        """
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return str(msg.get("content", ""))
        return ""
