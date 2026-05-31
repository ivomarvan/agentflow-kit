"""Deterministic fake LLM connector for tests and examples without real API calls.

``FakeLlmConnector`` serves responses from a preset queue; every ``chat()``
or ``achat()`` call consumes the next entry.  This makes tests fully
deterministic and free of network calls.

Because it inherits from ``LlmConnectorBase`` it also supports optional cache
injection — useful when you want to test the caching layer itself::

    fake = FakeLlmConnector(cache=LlmMemoryCache())
    fake.queue_responses(["hello", "world"])
    response = await fake.achat(messages)   # "hello" — also stored in cache
    response = await fake.achat(messages)   # "hello" — served from cache

Usage::

    from agentflow.llm.connectors import FakeLlmConnector

    connector = FakeLlmConnector()
    connector.queue_responses(["Paris is the capital of France.", "Done."])
"""

from __future__ import annotations

import logging
from collections import deque
from typing import TYPE_CHECKING, Any

from agentflow.llm.ChatResponse import ChatResponse
from agentflow.llm.LlmConnectorBase import LlmConnectorBase

if TYPE_CHECKING:
    from agentflow.llm.cache.LlmCacheBase import LlmCacheBase
    from agentflow.llm.LlmConfig import LlmConfig

logger = logging.getLogger(__name__)


class FakeLlmConnector(LlmConnectorBase):
    """Deterministic LLM connector that returns responses from a preset queue.

    Call ``queue_responses()`` before running to configure the sequence of
    responses.  A ``RuntimeError`` is raised when the queue is exhausted,
    preventing silent test failures.

    Args:
        cache: Optional cache.  When provided, responses are cached so that
               repeated identical requests are served without consuming from
               the queue.  Defaults to ``None``.
    """

    def __init__(self, *, cache: LlmCacheBase | None = None) -> None:
        super().__init__(cache=cache)
        self._queue: deque[str] = deque()

    # ------------------------------------------------------------------
    # LlmConnectorBase interface
    # ------------------------------------------------------------------

    @property
    def config(self) -> LlmConfig:
        """Not implemented — FakeLlmConnector has no real backend configuration.

        Raises:
            NotImplementedError: Always; callers should not inspect connector config.
        """
        raise NotImplementedError("FakeLlmConnector has no real LlmConfig")

    def _do_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        model_override: str | None,
    ) -> ChatResponse:
        """Return the next queued response.

        Args:
            messages: Ignored — fake connector does not call any LLM.
            tools: Ignored.
            temperature: Ignored.
            model_override: Ignored.

        Returns:
            ``ChatResponse`` with the next queued string as content.

        Raises:
            RuntimeError: When the response queue is empty.
        """
        if not self._queue:
            raise RuntimeError(
                "FakeLlmConnector queue is empty — call queue_responses() before running."
            )
        content = self._queue.popleft()
        logger.debug("fake response: content=%.40r", content)
        return ChatResponse(role="assistant", content=content, tool_calls=None, usage=None)

    async def _do_achat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        model_override: str | None,
    ) -> ChatResponse:
        """Async counterpart — delegates synchronously (no I/O).

        Args:
            messages: Ignored.
            tools: Ignored.
            temperature: Ignored.
            model_override: Ignored.

        Returns:
            ``ChatResponse`` with the next queued string as content.

        Raises:
            RuntimeError: When the response queue is empty.
        """
        return self._do_chat(messages, tools, temperature, model_override)

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------

    def queue_responses(self, responses: list[str]) -> None:
        """Append strings to the response queue.

        Args:
            responses: Ordered list of response strings.  Each ``chat()``
                       or ``achat()`` call consumes the next entry.
        """
        self._queue.extend(responses)

    @property
    def queue_size(self) -> int:
        """Number of responses remaining in the queue."""
        return len(self._queue)
