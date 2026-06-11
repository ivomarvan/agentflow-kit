"""Unit tests for LlmPool."""
from __future__ import annotations

import pytest

from agentflow.llm.LlmPool import LlmPool
from agentflow.llm.connectors.FakeLlmConnector import FakeLlmConnector


@pytest.mark.unit
class TestLlmPoolConstruction:
    def test_default_construction(self) -> None:
        """LlmPool() constructs without arguments."""
        pool = LlmPool()
        assert isinstance(pool, LlmPool)
        assert pool._cache is None

    def test_construction_with_cache(self) -> None:
        """LlmPool(cache=...) stores the cache instance."""
        from agentflow.llm.cache.LlmMemoryCache import LlmMemoryCache
        cache = LlmMemoryCache()
        pool = LlmPool(cache=cache)
        assert pool._cache is cache

    def test_default_classmethod_returns_pool_with_cache(self) -> None:
        """LlmPool.default() returns a pool with a non-None cache."""
        pool = LlmPool.default()
        assert isinstance(pool, LlmPool)
        assert pool._cache is not None


@pytest.mark.unit
class TestLlmPoolFromConnector:
    def test_from_connector_creates_pool(self) -> None:
        """LlmPool.from_connector() returns an LlmPool."""
        fake = FakeLlmConnector()
        pool = LlmPool.from_connector(fake)
        assert isinstance(pool, LlmPool)

    def test_from_connector_always_returns_same_connector(self) -> None:
        """Fixed pool ignores model and always returns the injected connector."""
        fake = FakeLlmConnector()
        pool = LlmPool.from_connector(fake)
        assert pool.get_connector("gpt-4o") is fake
        assert pool.get_connector("gemini-3.5") is fake
        assert pool.get_connector("") is fake

    def test_from_connector_different_instances_are_independent(self) -> None:
        """Two from_connector pools are independent."""
        fake_a = FakeLlmConnector()
        fake_b = FakeLlmConnector()
        pool_a = LlmPool.from_connector(fake_a)
        pool_b = LlmPool.from_connector(fake_b)
        assert pool_a.get_connector("any") is fake_a
        assert pool_b.get_connector("any") is fake_b


@pytest.mark.unit
class TestLlmPoolDescribable:
    def test_extra_describable_children_is_empty(self) -> None:
        """Connectors are internal — pool exposes no children in graph."""
        pool = LlmPool()
        assert pool._extra_describable_children() == {}

    def test_own_attributes_includes_connectors_active(self) -> None:
        """_get_own_attributes() reports connectors_active count."""
        pool = LlmPool()
        attrs = pool._get_own_attributes()
        assert "connectors_active" in attrs
        assert attrs["connectors_active"] == 0

    def test_own_attributes_includes_cache_type_when_set(self) -> None:
        """_get_own_attributes() reports cache class name when cache is set."""
        from agentflow.llm.cache.LlmMemoryCache import LlmMemoryCache
        pool = LlmPool(cache=LlmMemoryCache())
        attrs = pool._get_own_attributes()
        assert attrs.get("cache") == "LlmMemoryCache"
