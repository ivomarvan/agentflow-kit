"""Tests for the extended _make_cache_key function (T106-01)."""
from __future__ import annotations

import pytest

from agentflow.llm.LlmConnectorBase import _make_cache_key


_MESSAGES = [{"role": "user", "content": "hello"}]
_TOOLS: list[dict] | None = None


@pytest.mark.unit
class TestCacheKeyExtended:
    def test_cache_key_differs_by_model(self) -> None:
        """Two calls with different model names must produce different cache keys."""
        key1 = _make_cache_key(_MESSAGES, _TOOLS, model="gpt-4o", temperature=0.2)
        key2 = _make_cache_key(_MESSAGES, _TOOLS, model="gpt-4o-mini", temperature=0.2)
        assert key1 != key2

    def test_cache_key_differs_by_temperature(self) -> None:
        """Two calls with different temperatures must produce different cache keys."""
        key1 = _make_cache_key(_MESSAGES, _TOOLS, model="gpt-4o", temperature=0.2)
        key2 = _make_cache_key(_MESSAGES, _TOOLS, model="gpt-4o", temperature=0.8)
        assert key1 != key2

    def test_cache_key_identical_inputs_produce_same_key(self) -> None:
        """Identical inputs must produce the same deterministic key."""
        key1 = _make_cache_key(_MESSAGES, _TOOLS, model="gpt-4o", temperature=0.5)
        key2 = _make_cache_key(_MESSAGES, _TOOLS, model="gpt-4o", temperature=0.5)
        assert key1 == key2

    def test_cache_key_is_64_char_hex_string(self) -> None:
        """SHA-256 output is a 64-character lowercase hex string."""
        key = _make_cache_key(_MESSAGES, _TOOLS, model="gpt-4o", temperature=0.2)
        assert len(key) == 64
        assert key == key.lower()
        assert all(c in "0123456789abcdef" for c in key)

    def test_cache_key_differs_by_messages(self) -> None:
        """Two calls with different messages must produce different cache keys."""
        msgs1 = [{"role": "user", "content": "question A"}]
        msgs2 = [{"role": "user", "content": "question B"}]
        key1 = _make_cache_key(msgs1, _TOOLS, model="gpt-4o", temperature=0.2)
        key2 = _make_cache_key(msgs2, _TOOLS, model="gpt-4o", temperature=0.2)
        assert key1 != key2

    def test_cache_key_with_tools_differs_from_without(self) -> None:
        """Calls with and without tools must produce different keys."""
        tools = [{"type": "function", "function": {"name": "get_weather"}}]
        key1 = _make_cache_key(_MESSAGES, None, model="gpt-4o", temperature=0.2)
        key2 = _make_cache_key(_MESSAGES, tools, model="gpt-4o", temperature=0.2)
        assert key1 != key2
