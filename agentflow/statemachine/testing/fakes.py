"""Fake implementations for deterministic testing of state machine graphs.

FakeVertex, FakeLlmConnector, and make_fake_context allow tests to run
state graphs without real LLM calls or complex vertex logic.
"""

from __future__ import annotations

import logging
from typing import Any

from agentflow.llm.connectors.FakeLlmConnector import FakeLlmConnector
from agentflow.statemachine.context import Context
from agentflow.statemachine.vertex import StateVertex

# Re-export so callers can still do:
#   from agentflow.statemachine.testing.fakes import FakeLlmConnector
__all__ = ["FakeVertex", "FakeLlmConnector", "make_fake_context"]


class FakeVertex(StateVertex):
    """Configurable stub vertex that returns a preset signal and patch.

    Counts how many times run() was called — useful for asserting
    fan-out/fan-in behaviour and cycle termination.

    Args:
        signal: The EnumSignal value to return from run().
        patch: The patch object to return from run().
        name: Optional display name for debugging.
        call_count: Shared mutable list; each run() call appends 1.
                    Pass the same list across multiple fakes to aggregate
                    counts without subclassing.
    """

    def __init__(
        self,
        signal: Any,
        patch: Any,
        *,
        name: str | None = None,
        call_count: list[int] | None = None,
    ) -> None:
        super().__init__()
        self._signal = signal
        self._patch = patch
        self._name = name or type(self).__name__
        self._call_count: list[int] = call_count if call_count is not None else []
        self.calls: int = 0

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Return the configured signal and patch, increment call counters.

        Args:
            state: Current state snapshot (ignored by the fake).
            ctx: Shared context (ignored by the fake).

        Returns:
            Tuple of (signal, patch) as configured in __init__.
        """
        self.calls += 1
        self._call_count.append(1)
        return self._signal, self._patch

    def __repr__(self) -> str:
        return f"FakeVertex(name={self._name!r}, calls={self.calls})"


def make_fake_context(**overrides: Any) -> Context:
    """Create a Context with FakeLlmConnector and sensible test defaults.

    Args:
        **overrides: Any Context field to override (pool, tools, logger, run_id).
            For backward compat, a ``connector`` key is converted to
            ``pool=LlmPool.from_connector(connector)`` automatically.

    Returns:
        Context instance ready for use in tests without real LLM calls.
    """
    from agentflow.llm.LlmPool import LlmPool

    defaults: dict[str, Any] = {
        "pool": LlmPool.from_connector(FakeLlmConnector()),
        "logger": logging.getLogger("statemachine.test"),
        "run_id": "test-run-id",
    }
    # backward compat: connector= kwarg → pool
    if "connector" in overrides:
        conn = overrides.pop("connector")
        overrides.setdefault("pool", LlmPool.from_connector(conn))
    defaults.update(overrides)
    return Context(**defaults)
