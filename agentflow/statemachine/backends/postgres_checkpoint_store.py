"""PostgreSQL-backed CheckpointStore for agentflow.statemachine.

Requires: uv pip install -e ".[postgres]"  (asyncpg>=0.29)

Usage:
    async with PostgresCheckpointStore(dsn="postgresql://user:pass@host/db") as store:
        runner = StateGraphRunner(graph, ctx)
        state = await runner.run_until(initial_state, predicate, store=store, run_id="r1")
        # ... later ...
        final = await runner.resume(store, "r1", from_step=3)
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from typing import Any

from agentflow.statemachine.checkpoint import CheckpointRecord


class PostgresCheckpointStore:
    """Async PostgreSQL checkpoint store using asyncpg connection pool.

    Creates the `agentflow_checkpoints` table automatically on first connect.

    Args:
        dsn: PostgreSQL connection string (e.g. "postgresql://user:pass@host/db").
        state_factory: Optional callable(class_qualname: str, data: dict) -> Any.
                       Required to reconstruct typed state objects on load.
                       Without it, load() returns state as raw dict.
    """

    _TABLE = "agentflow_checkpoints"
    _DDL = """
        CREATE TABLE IF NOT EXISTS agentflow_checkpoints (
            run_id        TEXT    NOT NULL,
            step          INTEGER NOT NULL,
            state_type    TEXT    NOT NULL,
            state_json    TEXT    NOT NULL,
            active_nodes  JSONB   NOT NULL,
            created_at    TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (run_id, step)
        )
    """

    def __init__(
        self,
        dsn: str,
        state_factory: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> None:
        self._dsn = dsn
        self._state_factory = state_factory
        self._pool: Any = None  # asyncpg.Pool, typed as Any to avoid hard import

    async def connect(self) -> None:
        """Open connection pool and ensure the checkpoints table exists.

        Raises:
            ImportError: If asyncpg is not installed.
            asyncpg.PostgresConnectionError: If the DSN is invalid or server unreachable.
        """
        try:
            import asyncpg  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "asyncpg is required for PostgresCheckpointStore. "
                'Install with: uv pip install -e ".[postgres]"'
            ) from exc

        self._pool = await asyncpg.create_pool(self._dsn)
        async with self._pool.acquire() as conn:
            await conn.execute(self._DDL)

    async def close(self) -> None:
        """Close the connection pool.

        Safe to call even if connect() was never called.
        """
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def __aenter__(self) -> "PostgresCheckpointStore":
        """Async context manager: connect on enter."""
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager: close on exit."""
        await self.close()

    async def save(self, record: CheckpointRecord) -> None:
        """Persist a checkpoint record to PostgreSQL.

        Uses INSERT ... ON CONFLICT DO UPDATE to allow idempotent re-saves.

        Args:
            record: The CheckpointRecord to store; state must be a dataclass instance.

        Raises:
            RuntimeError: If connect() has not been called.
        """
        self._require_connected()
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agentflow_checkpoints
                    (run_id, step, state_type, state_json, active_nodes)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                ON CONFLICT (run_id, step) DO UPDATE
                    SET state_type   = EXCLUDED.state_type,
                        state_json   = EXCLUDED.state_json,
                        active_nodes = EXCLUDED.active_nodes
                """,
                record.run_id,
                record.step,
                type(record.state).__qualname__,
                json.dumps(dataclasses.asdict(record.state)),
                json.dumps(record.active_node_names),
            )

    async def load(self, run_id: str, step: int) -> CheckpointRecord:
        """Retrieve a checkpoint from PostgreSQL.

        Args:
            run_id: Run identifier.
            step: Super-step number.

        Returns:
            CheckpointRecord with state reconstructed via state_factory (if provided).

        Raises:
            KeyError: If no checkpoint exists for (run_id, step).
            RuntimeError: If connect() has not been called.
        """
        self._require_connected()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT state_type, state_json, active_nodes "
                "FROM agentflow_checkpoints "
                "WHERE run_id = $1 AND step = $2",
                run_id,
                step,
            )
        if row is None:
            raise KeyError(f"No checkpoint: run_id={run_id!r} step={step}")
        state_type: str = row["state_type"]
        state_data: dict[str, Any] = json.loads(row["state_json"])
        state: Any = (
            self._state_factory(state_type, state_data)
            if self._state_factory is not None
            else state_data
        )
        active_nodes: list[str] = json.loads(row["active_nodes"])
        return CheckpointRecord(
            run_id=run_id,
            step=step,
            state=state,
            active_node_names=active_nodes,
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
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT step FROM agentflow_checkpoints WHERE run_id = $1 ORDER BY step",
                run_id,
            )
        return [row["step"] for row in rows]

    def _require_connected(self) -> None:
        if self._pool is None:
            raise RuntimeError(
                "PostgresCheckpointStore is not connected. "
                "Call await store.connect() or use as async context manager."
            )
