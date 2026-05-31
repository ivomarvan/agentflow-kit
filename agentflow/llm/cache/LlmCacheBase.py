"""Abstract base class for LLM response caches.

All cache implementations must extend ``LlmCacheBase`` and implement
``get()`` and ``put()``.  The cache key is a SHA-256 hex digest of the
serialised (messages, tools) pair — computed by
``agentflow.llm.LlmConnectorBase._make_cache_key()``.

Available implementations:
  - ``LlmMemoryCache``  — in-process dict, lost on restart (testing / ephemeral use)
  - ``LlmFileCache``    — persistent JSONL file with LFU eviction

Example::

    from agentflow.llm.cache import LlmFileCache, LlmMemoryCache
    from agentflow import LlmConnector

    connector = LlmConnector(cache=LlmFileCache(__file__))
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING

from agentflow.describable.describable import Describable

if TYPE_CHECKING:
    from agentflow.llm.ChatResponse import ChatResponse


class LlmCacheBase(Describable):
    """Abstract interface for all LLM response caches.

    Implementations are responsible for thread/async safety and for
    serialising/deserialising ``ChatResponse`` objects as needed.
    """

    @abstractmethod
    def get(self, key: str) -> ChatResponse | None:
        """Return the cached response for *key*, or ``None`` on miss.

        Args:
            key: SHA-256 hex digest cache key.

        Returns:
            Cached ``ChatResponse``, or ``None`` when absent.
        """
        ...

    @abstractmethod
    def put(self, key: str, response: ChatResponse) -> None:
        """Store *response* under *key*.

        Args:
            key: SHA-256 hex digest cache key.
            response: ``ChatResponse`` to store.
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """Remove all cached entries."""
        ...

    @property
    @abstractmethod
    def size(self) -> int:
        """Number of entries currently in the cache."""
        ...
