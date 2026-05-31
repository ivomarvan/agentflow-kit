"""Persistent JSONL-based LLM response cache with LFU eviction.

``LlmFileCache`` stores each cached (request → response) pair as one JSON
line in a file whose name is derived automatically from the calling script.
This means every example / application gets its own cache file without any
manual configuration.

Cache file location
-------------------
The default cache directory is ``~/.cache/agentflow/llm/``.  The file name
is ``<caller_script_stem>.jsonl``, e.g.::

    ~/.cache/agentflow/llm/04_blog_pipeline.jsonl

Usage::

    from agentflow.llm.cache import LlmFileCache
    from agentflow import LlmConnector

    # In an example or application file:
    connector = LlmConnector(cache=LlmFileCache(__file__))

Eviction policy
---------------
When the cache reaches ``max_size`` entries, the entry with the **lowest
rating** (cumulative hit count) is evicted.  Ties are broken by insertion
order — the oldest entry with the lowest rating is removed first.

Storage format
--------------
One JSON object per line::

    {"id": 1, "rating": 3, "key": "sha256...",
     "messages": [...], "tools": [...], "response": {...}}

Thread-safe via ``threading.RLock``; safe for both synchronous and async use.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from agentflow.llm.cache.LlmCacheBase import LlmCacheBase
from agentflow.llm.ChatResponse import (
    ChatResponse,
    ToolCallFunction,
    ToolCallInfo,
    UsageInfo,
)

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "agentflow" / "llm"


class LlmFileCache(LlmCacheBase):
    """Persistent JSONL cache for LLM responses.

    The cache file is named after the calling script and stored in a
    platform-appropriate user cache directory.

    Args:
        caller_file: Path of the script that owns this cache, typically
                     ``__file__``.  Used to derive the cache filename.
        cache_dir: Override the directory where the cache file is stored.
                   Defaults to ``~/.cache/agentflow/llm/``.
        max_size: Maximum number of entries.  When exceeded, the entry
                  with the lowest rating (oldest on tie) is evicted.
    """

    def __init__(
        self,
        caller_file: str | Path,
        *,
        cache_dir: Path | None = None,
        max_size: int = 500,
    ) -> None:
        super().__init__()
        stem = Path(caller_file).stem
        self._cache_file = (cache_dir or _DEFAULT_CACHE_DIR) / f"{stem}.jsonl"
        self._max_size = max_size
        self._lock = threading.RLock()
        self._entries: list[dict[str, Any]] = []
        self._lookup: dict[str, dict[str, Any]] = {}
        self._next_id: int = 1
        self._load()

    # ------------------------------------------------------------------
    # LlmCacheBase interface
    # ------------------------------------------------------------------

    def get(self, key: str) -> ChatResponse | None:
        """Return the cached response and increment its rating, or ``None``.

        Args:
            key: SHA-256 hex cache key.

        Returns:
            Cached ``ChatResponse``, or ``None`` on miss.
        """
        with self._lock:
            entry = self._lookup.get(key)
            if entry is None:
                return None
            entry["rating"] += 1
            self._save()
            logger.debug("cache hit: key=%.16s… rating=%d", key, entry["rating"])
            return _deserialize_response(entry["response"])

    def put(self, key: str, response: ChatResponse) -> None:
        """Store *response*; evict the lowest-rated entry if at capacity.

        Args:
            key: SHA-256 hex cache key.
            response: Response to store.
        """
        with self._lock:
            if key in self._lookup:
                return  # race-condition guard
            if len(self._entries) >= self._max_size:
                self._evict()
            entry: dict[str, Any] = {
                "id": self._next_id,
                "rating": 0,
                "key": key,
                "response": _serialize_response(response),
            }
            self._next_id += 1
            self._entries.append(entry)
            self._lookup[key] = entry
            self._save()
            logger.debug(
                "cache store: key=%.16s… size=%d/%d",
                key, len(self._entries), self._max_size,
            )

    def clear(self) -> None:
        """Remove all entries from memory and delete the cache file."""
        with self._lock:
            self._entries.clear()
            self._lookup.clear()
            self._next_id = 1
            if self._cache_file.exists():
                self._cache_file.unlink()
        logger.info("cache cleared: file=%s", self._cache_file)

    @property
    def size(self) -> int:
        """Number of entries currently in the cache."""
        with self._lock:
            return len(self._entries)

    # ------------------------------------------------------------------
    # Describable
    # ------------------------------------------------------------------

    def _get_own_attributes(self) -> dict[str, Any]:
        attrs = super()._get_own_attributes()
        attrs["cache_file"] = str(self._cache_file)
        attrs["size"] = self.size
        attrs["max_size"] = self._max_size
        return attrs

    # ------------------------------------------------------------------
    # Private — I/O
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load entries from the JSONL file if it exists."""
        if not self._cache_file.exists():
            return
        loaded = errors = 0
        with self._lock:
            try:
                lines = self._cache_file.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        self._entries.append(entry)
                        self._lookup[entry["key"]] = entry
                        self._next_id = max(self._next_id, entry["id"] + 1)
                        loaded += 1
                    except (json.JSONDecodeError, KeyError):
                        errors += 1
            except OSError as exc:
                logger.warning("cache load failed: file=%s err=%s", self._cache_file, exc)
                return
        if errors:
            logger.warning("cache load: skipped %d malformed entries", errors)
        logger.info("cache loaded: file=%s entries=%d", self._cache_file, loaded)

    def _save(self) -> None:
        """Rewrite the JSONL file with all current entries (must hold lock)."""
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            lines = [json.dumps(e, ensure_ascii=False) for e in self._entries]
            self._cache_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as exc:
            logger.error("cache save failed: file=%s err=%s", self._cache_file, exc)

    def _evict(self) -> None:
        """Remove the entry with the lowest (rating, id) pair."""
        if not self._entries:
            return
        victim = min(self._entries, key=lambda e: (e["rating"], e["id"]))
        self._entries.remove(victim)
        del self._lookup[victim["key"]]
        logger.debug(
            "cache evict: id=%d rating=%d key=%.16s…",
            victim["id"], victim["rating"], victim["key"],
        )


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _serialize_response(response: ChatResponse) -> dict[str, Any]:
    """Convert ``ChatResponse`` to a JSON-serialisable dict.

    Args:
        response: Response from the LLM backend.

    Returns:
        Plain dict suitable for JSONL storage.
    """
    tool_calls = None
    if response.tool_calls:
        tool_calls = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                    **tc.function.extra,
                },
                **tc.extra,
            }
            for tc in response.tool_calls
        ]
    usage = None
    if response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }
    return {
        "role": response.role,
        "content": response.content,
        "tool_calls": tool_calls,
        "usage": usage,
    }


def _deserialize_response(data: dict[str, Any]) -> ChatResponse:
    """Reconstruct a ``ChatResponse`` from a previously serialised dict.

    Args:
        data: Dict produced by ``_serialize_response()``.

    Returns:
        Reconstructed ``ChatResponse``.
    """
    tool_calls = None
    if data.get("tool_calls"):
        tool_calls = [
            ToolCallInfo(
                id=tc["id"],
                type=tc.get("type", "function"),
                function=ToolCallFunction(
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"],
                    extra={
                        k: v for k, v in tc["function"].items()
                        if k not in ("name", "arguments")
                    },
                ),
                extra={k: v for k, v in tc.items() if k not in ("id", "type", "function")},
            )
            for tc in data["tool_calls"]
        ]
    usage = None
    if data.get("usage"):
        u = data["usage"]
        usage = UsageInfo(
            prompt_tokens=u["prompt_tokens"],
            completion_tokens=u["completion_tokens"],
            total_tokens=u["total_tokens"],
        )
    return ChatResponse(
        role=data["role"],
        content=data.get("content"),
        tool_calls=tool_calls,
        usage=usage,
    )
