"""Checkpoint persistence for agentflow.statemachine.

Provides CheckpointRecord (snapshot dataclass), CheckpointStore (pluggable Protocol),
InMemoryCheckpointStore (in-process implementation for tests and short-lived workflows),
and JsonFileCheckpointStore (file-backed persistence for cross-process resume).
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass
class CheckpointRecord:
    """Snapshot of graph execution state after one super-step.

    Args:
        run_id: Unique identifier for the run that produced this checkpoint.
        step: Super-step number (1-based) at which the snapshot was taken.
        state: The frozen dataclass state after this step completes.
        active_node_names: Class names of vertices that will be active in the next step.
    """

    run_id: str
    step: int
    state: Any
    active_node_names: list[str]


# Pattern: Strategy (GoF) — runtime algorithm selection via Protocol
@runtime_checkable
class CheckpointStore(Protocol):
    """Protocol for pluggable checkpoint persistence backends.

    Implementations must satisfy all three coroutines to be structurally
    compatible. Decorated with @runtime_checkable to allow isinstance() checks.
    """

    async def save(self, record: CheckpointRecord) -> None:
        """Persist a checkpoint record.

        Args:
            record: The CheckpointRecord to store, keyed by (run_id, step).
        """
        ...

    async def load(self, run_id: str, step: int) -> CheckpointRecord:
        """Retrieve a previously saved checkpoint.

        Args:
            run_id: Run identifier used when the record was saved.
            step: Super-step number used when the record was saved.

        Returns:
            The CheckpointRecord matching (run_id, step).

        Raises:
            KeyError: If no record exists for (run_id, step).
        """
        ...

    async def list_steps(self, run_id: str) -> list[int]:
        """Return all saved step numbers for a run, in ascending order.

        Args:
            run_id: Run identifier to query.

        Returns:
            Sorted list of step numbers; empty list when no checkpoints exist.
        """
        ...


class InMemoryCheckpointStore:
    """Thread-safe in-memory CheckpointStore for testing and short-lived workflows.

    Stores CheckpointRecord objects directly without serialization.
    Satisfies CheckpointStore structurally (runtime_checkable Protocol).
    """

    def __init__(self) -> None:
        self._data: dict[tuple[str, int], CheckpointRecord] = {}

    async def save(self, record: CheckpointRecord) -> None:
        """Persist a checkpoint record in memory.

        Args:
            record: The CheckpointRecord to store; overwrites any prior record
                    with the same (run_id, step) key.
        """
        self._data[(record.run_id, record.step)] = record

    async def load(self, run_id: str, step: int) -> CheckpointRecord:
        """Retrieve a previously saved checkpoint from memory.

        Args:
            run_id: Run identifier used when the record was saved.
            step: Super-step number used when the record was saved.

        Returns:
            The CheckpointRecord matching (run_id, step).

        Raises:
            KeyError: If no record exists for the given (run_id, step).
        """
        try:
            return self._data[(run_id, step)]
        except KeyError:
            raise KeyError(f"No checkpoint: run_id={run_id!r} step={step}") from None

    async def list_steps(self, run_id: str) -> list[int]:
        """Return all saved step numbers for a run, in ascending order.

        Args:
            run_id: Run identifier to query.

        Returns:
            Sorted list of step numbers; empty list when no checkpoints exist.
        """
        return sorted(s for (r, s) in self._data if r == run_id)


class JsonFileCheckpointStore:
    """Persists checkpoints as JSON files: <base_dir>/<run_id>/<step:04d>.json.

    State serialization uses dataclasses.asdict(). Provide state_factory to
    reconstruct state objects on load; without it, load() returns the raw dict
    for state (useful for testing or when state is already a dict).

    Satisfies CheckpointStore structurally (runtime_checkable Protocol).

    Args:
        base_dir: Root directory for checkpoint files. Created on first save.
        state_factory: Optional callable(class_qualname: str, data: dict) -> Any.
                       Required for load() to reconstruct typed state objects.
    """

    def __init__(
        self,
        base_dir: str | Path = "./checkpoints",
        state_factory: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> None:
        self._base = Path(base_dir)
        self._state_factory = state_factory

    async def save(self, record: CheckpointRecord) -> None:
        """Persist a checkpoint record as a JSON file.

        Creates the directory structure (run_id subdirectory) on first save.
        File I/O is dispatched to a thread pool to avoid blocking the event loop.

        Args:
            record: The CheckpointRecord to persist; state must be a dataclass instance.
        """
        path = self._path(record.run_id, record.step)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "run_id": record.run_id,
            "step": record.step,
            "__state_type__": type(record.state).__qualname__,
            "state": dataclasses.asdict(record.state),
            "active_node_names": record.active_node_names,
        }
        text = json.dumps(payload, indent=2)
        await asyncio.to_thread(path.write_text, text, "utf-8")

    async def load(self, run_id: str, step: int) -> CheckpointRecord:
        """Retrieve a checkpoint from disk.

        Args:
            run_id: Run identifier used when the record was saved.
            step: Super-step number used when the record was saved.

        Returns:
            CheckpointRecord with state reconstructed via state_factory (if provided)
            or as a raw dict when state_factory is None.

        Raises:
            KeyError: If no checkpoint file exists for (run_id, step).
        """
        path = self._path(run_id, step)
        if not path.exists():
            raise KeyError(f"No checkpoint: run_id={run_id!r} step={step}")
        raw = await asyncio.to_thread(path.read_text, "utf-8")
        data: dict[str, Any] = json.loads(raw)
        state_type: str = data["__state_type__"]
        state: Any = (
            self._state_factory(state_type, data["state"])
            if self._state_factory is not None
            else data["state"]
        )
        return CheckpointRecord(
            run_id=data["run_id"],
            step=data["step"],
            state=state,
            active_node_names=data["active_node_names"],
        )

    async def list_steps(self, run_id: str) -> list[int]:
        """Return all saved step numbers for a run, in ascending order.

        Scans the run_id subdirectory for JSON files and extracts step numbers
        from filenames (format: <step:04d>.json).

        Args:
            run_id: Run identifier to query.

        Returns:
            Sorted list of step numbers; empty list when no checkpoints exist.
        """
        run_dir = self._base / run_id
        if not run_dir.exists():
            return []
        return sorted(int(p.stem) for p in run_dir.glob("*.json"))

    def _path(self, run_id: str, step: int) -> Path:
        return self._base / run_id / f"{step:04d}.json"
