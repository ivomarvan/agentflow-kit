"""StateVertex ABC and End/StdEnd terminal nodes.

All user-defined graph nodes inherit from StateVertex. The runner identifies
the end of execution by isinstance(node, End) — no magic sentinels needed,
so custom end nodes (e.g. AnswerEnd) integrate naturally.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from src.agentflow.statemachine.signal import StdSignal

if TYPE_CHECKING:
    from src.agentflow.statemachine.context import Context


class StateVertex(ABC):
    """Abstract base class for all graph nodes.

    Each subclass implements run() which receives the current state snapshot
    and the shared context, then returns a routing signal + state patch.
    All constructor parameters MUST have default values to support
    auto-instantiation in Epic E020.
    """

    @abstractmethod
    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Execute this vertex for one BSP super-step.

        Args:
            state: Current immutable state snapshot (frozen dataclass).
            ctx: Shared services (LLM connector, tools, logger, run_id).

        Returns:
            Tuple of (EnumSignal, StatePatch) — signal routes the next step,
            patch describes state mutations.
        """


class End(StateVertex):
    """Marker base class for terminal nodes.

    The runner detects end-of-run by isinstance(active_node, End).
    Subclass End to add custom termination logic (logging, notifications, cleanup).
    """

    @abstractmethod
    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]: ...


class StdEnd(End):
    """Default terminal node — does nothing, returns an empty patch.

    Use StdEnd when no custom end logic is needed. The runner will stop
    the BSP loop after StdEnd.run() completes.
    """

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Return done signal with empty patch to terminate the run.

        Args:
            state: Current state (ignored).
            ctx: Shared context (ignored).

        Returns:
            Tuple (StdSignal.done, empty StatePatch-compatible object).
        """
        # Import here to avoid circular: vertex.py <- state.py (StatePatch not yet defined)
        # StdEnd returns a minimal sentinel; T040 will wire proper StatePatch.
        return StdSignal.done, _EmptyPatch()


class _EmptyPatch:
    """Minimal sentinel patch returned by StdEnd before StatePatch is available."""
