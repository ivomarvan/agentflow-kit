"""In-memory LLM response cache — fast, no persistence, lost on process exit.

Useful for:
  - Unit tests that want to verify cache behaviour without disk I/O.
  - Short-lived scripts where persistence across runs is not needed.

Thread-safe via ``threading.RLock``.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from agentflow.llm.cache.LlmCacheBase import LlmCacheBase
from agentflow.llm.ChatResponse import ChatResponse

logger = logging.getLogger(__name__)


class LlmMemoryCache(LlmCacheBase):
    """LRU-like in-memory cache for ``ChatResponse`` objects.

    Entries are stored in insertion order.  When ``max_size`` is reached,
    the entry with the lowest hit count (oldest on tie) is evicted.

    Args:
        max_size: Maximum number of entries to keep.  Defaults to 500.
    """

    def __init__(self, max_size: int = 500) -> None:
        super().__init__()
        self._max_size = max_size
        self._lock = threading.RLock()
        self._store: dict[str, tuple[ChatResponse, int]] = {}  # key → (response, hits)
        self._order: list[str] = []  # insertion order for eviction tiebreak

    # ------------------------------------------------------------------
    # LlmCacheBase interface
    # ------------------------------------------------------------------

    def get(self, key: str) -> ChatResponse | None:
        """Return cached response and increment hit counter, or ``None``.

        Args:
            key: SHA-256 hex cache key.

        Returns:
            Cached ``ChatResponse``, or ``None`` on miss.
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            response, hits = entry
            self._store[key] = (response, hits + 1)
            logger.debug("cache hit: key=%.16s… hits=%d", key, hits + 1)
            return response

    def put(self, key: str, response: ChatResponse) -> None:
        """Store *response*; evict the least-used entry if at capacity.

        Args:
            key: SHA-256 hex cache key.
            response: Response to store.
        """
        with self._lock:
            if key in self._store:
                return  # already present (race condition guard)
            if len(self._store) >= self._max_size:
                self._evict()
            self._store[key] = (response, 0)
            self._order.append(key)
            logger.debug("cache store: key=%.16s… size=%d", key, len(self._store))

    def clear(self) -> None:
        """Remove all cached entries."""
        with self._lock:
            self._store.clear()
            self._order.clear()
        logger.info("memory cache cleared")

    @property
    def size(self) -> int:
        """Number of entries currently in the cache."""
        with self._lock:
            return len(self._store)

    # ------------------------------------------------------------------
    # Describable
    # ------------------------------------------------------------------

    def _get_own_attributes(self) -> dict[str, Any]:
        attrs = super()._get_own_attributes()
        attrs["size"] = self.size
        attrs["max_size"] = self._max_size
        return attrs

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _evict(self) -> None:
        """Evict the entry with the lowest hit count (oldest key on tie)."""
        if not self._order:
            return
        victim_key = min(
            self._order,
            key=lambda k: (self._store[k][1], self._order.index(k)),
        )
        del self._store[victim_key]
        self._order.remove(victim_key)
        logger.debug("cache evict: key=%.16s…", victim_key)
