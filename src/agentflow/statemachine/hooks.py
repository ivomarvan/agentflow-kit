"""RunnerHooks protocol and default observability implementations.

RunnerHooks defines asynchronous callbacks invoked at key points of the BSP
execution loop. NoOpHooks is the default (used when no hooks are provided).
LoggingHooks provides structured DEBUG/INFO logs for development use.
Full RecorderHooks with step history will be added in Epic E030.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.agentflow.statemachine.vertex import StateVertex


@runtime_checkable
class RunnerHooks(Protocol):
    """Async callback interface for observing StateGraphRunner execution.

    All methods are called by the runner at specific points in the BSP loop.
    Implementations must be awaitable (async def). The default implementation
    is NoOpHooks which does nothing for all callbacks.
    """

    async def on_run_start(self, state: object) -> None:
        """Called once before the BSP loop starts.

        Args:
            state: Initial state passed to runner.run().
        """
        ...

    async def on_super_step_start(
        self, step: int, state: object, active: list[StateVertex]
    ) -> None:
        """Called at the beginning of each super-step (Compute phase).

        Args:
            step: Super-step counter (1-based).
            state: Current state snapshot.
            active: List of vertices about to be executed.
        """
        ...

    async def on_vertex_error(self, node: StateVertex, exc: Exception) -> None:
        """Called when a vertex raises an unexpected exception.

        Args:
            node: The vertex that raised the exception.
            exc: The exception that was raised.
        """
        ...

    async def on_super_step_end(
        self, step: int, state: object, next_active: set[StateVertex]
    ) -> None:
        """Called after Apply&Route phase, with updated state and next active nodes.

        Args:
            step: Super-step counter (same as on_super_step_start).
            state: New state after applying patches.
            next_active: Set of vertices scheduled for the next super-step.
        """
        ...

    async def on_run_end(self, state: object) -> None:
        """Called once after the BSP loop completes (End node reached).

        Args:
            state: Final state after the last super-step.
        """
        ...


class NoOpHooks:
    """Default no-op implementation of RunnerHooks — all callbacks do nothing.

    Used as the default when no hooks are provided to StateGraphRunner.
    Zero overhead: all methods immediately return None.
    """

    async def on_run_start(self, state: object) -> None:
        """Called once before the BSP loop starts; no-op.

        Args:
            state: Initial state passed to runner.run().
        """
        return None

    async def on_super_step_start(
        self, step: int, state: object, active: list[StateVertex]
    ) -> None:
        """Called at the beginning of each super-step; no-op.

        Args:
            step: Super-step counter (1-based).
            state: Current state snapshot.
            active: List of vertices about to be executed.
        """
        return None

    async def on_vertex_error(self, node: StateVertex, exc: Exception) -> None:
        """Called when a vertex raises an exception; no-op.

        Args:
            node: The vertex that raised the exception.
            exc: The exception that was raised.
        """
        return None

    async def on_super_step_end(
        self, step: int, state: object, next_active: set[StateVertex]
    ) -> None:
        """Called after Apply&Route phase; no-op.

        Args:
            step: Super-step counter (same as on_super_step_start).
            state: New state after applying patches.
            next_active: Set of vertices scheduled for the next super-step.
        """
        return None

    async def on_run_end(self, state: object) -> None:
        """Called once after the BSP loop completes; no-op.

        Args:
            state: Final state after the last super-step.
        """
        return None


class LoggingHooks:
    """RunnerHooks implementation that emits structured log records.

    Uses DEBUG for per-vertex detail and INFO for super-step milestones.
    Vertex errors are logged at ERROR level with full exception traceback.

    Args:
        name: Logger name; defaults to 'statemachine.runner'.
    """

    def __init__(self, name: str = "statemachine.runner") -> None:
        self._logger = logging.getLogger(name)

    async def on_run_start(self, state: object) -> None:
        """Called once before the BSP loop starts; logs at INFO level.

        Args:
            state: Initial state passed to runner.run().
        """
        self._logger.info("run_start: state_type=%s", type(state).__name__)

    async def on_super_step_start(
        self, step: int, state: object, active: list[StateVertex]
    ) -> None:
        """Called at the beginning of each super-step; logs active vertices at DEBUG.

        Args:
            step: Super-step counter (1-based).
            state: Current state snapshot.
            active: List of vertices about to be executed.
        """
        node_names = [type(n).__name__ for n in active]
        self._logger.debug("super_step_start: step=%d active=%s", step, node_names)

    async def on_vertex_error(self, node: StateVertex, exc: Exception) -> None:
        """Called when a vertex raises an unexpected exception; logs at ERROR with traceback.

        Args:
            node: The vertex that raised the exception.
            exc: The exception that was raised.
        """
        self._logger.error(
            "vertex_error: node=%s exc_type=%s exc=%s",
            type(node).__name__,
            type(exc).__name__,
            exc,
            exc_info=exc,
        )

    async def on_super_step_end(
        self, step: int, state: object, next_active: set[StateVertex]
    ) -> None:
        """Called after Apply&Route phase; logs next active vertices at INFO.

        Args:
            step: Super-step counter (same as on_super_step_start).
            state: New state after applying patches.
            next_active: Set of vertices scheduled for the next super-step.
        """
        node_names = [type(n).__name__ for n in next_active]
        self._logger.info("super_step_end: step=%d next_active=%s", step, node_names)

    async def on_run_end(self, state: object) -> None:
        """Called once after the BSP loop completes; logs at INFO level.

        Args:
            state: Final state after the last super-step.
        """
        self._logger.info("run_end: final_state_type=%s", type(state).__name__)
