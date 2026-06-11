"""Transparent LLM connector pool for model-first vertex orchestration.

``LlmPool`` is the single user-facing LLM configuration object.  Users set
a cache (or accept the default) and the pool creates ``LlmConnector`` instances
on demand, keyed by model name.  Connectors are internal implementation details
and are not exposed to application code.

Usage::

    # Zero-config — uses ~/.cache/agentflow/llm/agentflow_pool.jsonl
    ctx = Context()

    # Custom cache per example/application
    from agentflow.llm.cache import LlmFileCache
    ctx = Context(pool=LlmPool(cache=LlmFileCache(__file__)))

    # No cache (useful in tests or when caching is undesirable)
    ctx = Context(pool=LlmPool())

    # Test helper — always returns the same fake connector
    ctx = Context(pool=LlmPool.from_connector(FakeLlmConnector()))

Pattern: Object Pool (GoF) — manages a family of LlmConnector instances,
creating them lazily on first use and reusing them on subsequent requests.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentflow.describable.describable import Describable

if TYPE_CHECKING:
    from agentflow.llm.LlmConnectorBase import LlmConnectorBase
    from agentflow.llm.cache.LlmCacheBase import LlmCacheBase

logger = logging.getLogger(__name__)

_DEFAULT_POOL_CACHE_NAME = "agentflow_pool"


class LlmPool(Describable):
    """Transparent pool that creates and reuses LLM connectors by model name.

    A single shared cache is injected into every connector the pool creates.
    This means all connectors share one cache file, distinguished by model
    and temperature in the cache key, so entries stay distinct per call configuration.

    Connectors managed by the pool are NOT ``Describable``; they do not
    appear in the composition graph.  Only the pool itself is visible.

    Args:
        cache: Optional cache instance shared across all connectors in this
               pool.  When ``None``, no caching is performed (live API calls
               every time).
    """

    def __init__(self, *, cache: LlmCacheBase | None = None) -> None:
        super().__init__()
        self._cache = cache
        self._connectors: dict[str, LlmConnectorBase] = {}
        # For fixed-connector pools (from_connector factory)
        self._fixed_connector: LlmConnectorBase | None = None

    # ------------------------------------------------------------------
    # Primary interface
    # ------------------------------------------------------------------

    def get_connector(self, model: str) -> LlmConnectorBase:
        """Return a connector for *model*, creating one if not yet pooled.

        When the pool was built via :meth:`from_connector`, that connector
        is always returned regardless of *model* (useful for testing).

        Args:
            model: LLM model name (e.g. ``"gpt-4o-mini"``).  Empty string
                   uses the environment default via ``LlmConfig.from_env()``.

        Returns:
            A ready ``LlmConnector`` with the pool's shared cache injected.
        """
        if self._fixed_connector is not None:
            return self._fixed_connector
        key = model or ""
        if key not in self._connectors:
            from agentflow.llm.connectors.LlmConnector import LlmConnector
            conn = LlmConnector(model=model, cache=self._cache)
            self._connectors[key] = conn
            logger.debug("llm_pool: created connector model=%r", conn.config.model)
        return self._connectors[key]

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def default(cls) -> LlmPool:
        """Return a pool with the default persistent file cache.

        Cache file: ``~/.cache/agentflow/llm/agentflow_pool.jsonl``.
        Shared across all applications that use the default pool.

        Returns:
            ``LlmPool`` with a ``LlmFileCache`` at the standard location.
        """
        from agentflow.llm.cache.LlmFileCache import LlmFileCache
        cache = LlmFileCache(_DEFAULT_POOL_CACHE_NAME)
        return cls(cache=cache)

    @classmethod
    def from_connector(cls, connector: LlmConnectorBase) -> LlmPool:
        """Create a pool that always returns *connector* for any model.

        Useful in unit tests where a ``FakeLlmConnector`` should be used
        regardless of which model the vertex requests.

        Args:
            connector: The connector to return for every ``get_connector()`` call.

        Returns:
            ``LlmPool`` that forwards all requests to *connector*.
        """
        pool = cls(cache=None)
        pool._fixed_connector = connector
        return pool

    # ------------------------------------------------------------------
    # Describable — visible in graph as a single box (no children)
    # ------------------------------------------------------------------

    def _get_own_attributes(self) -> dict[str, Any]:
        """Expose cache info and connector count in graph tooltip."""
        attrs = super()._get_own_attributes()
        if self._cache is not None:
            attrs["cache"] = type(self._cache).__name__
        attrs["connectors_active"] = len(self._connectors)
        return attrs

    def _extra_describable_children(self) -> dict[str, Any]:
        """Expose the cache as a nested box in the graph; hide connectors.

        Connectors are internal implementation details and are NOT shown.
        Only the shared cache (if set) appears as a nested Describable child.

        Returns:
            Dict with ``"cache"`` → cache instance when a cache is configured,
            otherwise empty dict.
        """
        if self._cache is not None and isinstance(self._cache, Describable):
            return {"cache": self._cache}
        return {}
