"""Redis-backed CheckpointStore for agentflow.statemachine.

Requires: uv pip install -e ".[redis-backend]"  (redis[asyncio]>=5.0)

Key scheme:
  agentflow:chk:{run_id}:{step:04d}  → JSON string with full checkpoint payload
  agentflow:steps:{run_id}           → Redis sorted set (score=step, member=step)

Usage:
    async with RedisCheckpointStore(url="redis://localhost:6379") as store:
        runner = StateGraphRunner(graph, ctx)
        state = await runner.run_until(initial_state, predicate, store=store, run_id="r1")
        final = await runner.resume(store, "r1", from_step=3)
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from typing import Any

from agentflow.statemachine.checkpoint import CheckpointRecord


class RedisCheckpointStore:
    """Async Redis checkpoint store using redis.asyncio client.

    Args:
        url: Redis connection URL (default: "redis://localhost:6379").
        state_factory: Optional callable(class_qualname: str, data: dict) -> Any.
                       Required to reconstruct typed state objects on load.
                       Without it, load() returns state as raw dict.
    """

    _KEY_PREFIX = "agentflow:chk"
    _STEPS_PREFIX = "agentflow:steps"

    def __init__(
        self,
        url: str = "redis://localhost:6379",
        state_factory: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> None:
        self._url = url
        self._state_factory = state_factory
        self._client: Any = None  # redis.asyncio.Redis, typed as Any to avoid hard import

    async def connect(self) -> None:
        """Open Redis connection.

        Raises:
            ImportError: If redis[asyncio] is not installed.
        """
        try:
            import redis.asyncio as aioredis  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "redis[asyncio] is required for RedisCheckpointStore. "
                'Install with: uv pip install -e ".[redis-backend]"'
            ) from exc
        self._client = aioredis.from_url(self._url, decode_responses=True)

    async def close(self) -> None:
        """Close the Redis connection. Safe to call even if connect() was never called."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> RedisCheckpointStore:
        """Async context manager: connect on enter."""
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager: close on exit."""
        await self.close()

    async def save(self, record: CheckpointRecord) -> None:
        """Persist a checkpoint to Redis.

        Uses a pipeline+transaction to atomically write the JSON blob and update
        the sorted-set step index.

        Args:
            record: CheckpointRecord to store; state must be a dataclass instance.

        Raises:
            RuntimeError: If connect() has not been called.
        """
        self._require_connected()
        payload = {
            "run_id": record.run_id,
            "step": record.step,
            "__state_type__": type(record.state).__qualname__,
            "state": dataclasses.asdict(record.state),
            "active_node_names": record.active_node_names,
        }
        chk_key = self._chk_key(record.run_id, record.step)
        steps_key = f"{self._STEPS_PREFIX}:{record.run_id}"
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.set(chk_key, json.dumps(payload))
            pipe.zadd(steps_key, {str(record.step): record.step})
            await pipe.execute()

    async def load(self, run_id: str, step: int) -> CheckpointRecord:
        """Retrieve a checkpoint from Redis.

        Args:
            run_id: Run identifier.
            step: Super-step number.

        Returns:
            CheckpointRecord with state reconstructed via state_factory (if provided)
            or as a raw dict when state_factory is None.

        Raises:
            KeyError: If no checkpoint exists for (run_id, step).
            RuntimeError: If connect() has not been called.
        """
        self._require_connected()
        chk_key = self._chk_key(run_id, step)
        raw = await self._client.get(chk_key)
        if raw is None:
            raise KeyError(f"No checkpoint: run_id={run_id!r} step={step}")
        data: dict[str, Any] = json.loads(raw)
        state_type: str = data["__state_type__"]
        state_data: dict[str, Any] = data["state"]
        state: Any = (
            self._state_factory(state_type, state_data)
            if self._state_factory is not None
            else state_data
        )
        return CheckpointRecord(
            run_id=run_id,
            step=step,
            state=state,
            active_node_names=data["active_node_names"],
        )

    async def list_steps(self, run_id: str) -> list[int]:
        """Return all saved step numbers for a run, ascending.

        Args:
            run_id: Run identifier.

        Returns:
            Sorted list of step numbers; empty list when no checkpoints exist.

        Raises:
            RuntimeError: If connect() has not been called.
        """
        self._require_connected()
        steps_key = f"{self._STEPS_PREFIX}:{run_id}"
        members = await self._client.zrange(steps_key, 0, -1)
        return [int(m) for m in members]

    def _chk_key(self, run_id: str, step: int) -> str:
        return f"{self._KEY_PREFIX}:{run_id}:{step:04d}"

    def _require_connected(self) -> None:
        if self._client is None:
            raise RuntimeError(
                "RedisCheckpointStore is not connected. "
                "Call await store.connect() or use as async context manager."
            )
