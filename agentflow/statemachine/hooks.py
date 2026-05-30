"""RunnerHooks protocol and default observability implementations.

RunnerHooks defines asynchronous callbacks invoked at key points of the BSP
execution loop. NoOpHooks is the default (used when no hooks are provided).
LoggingHooks provides structured DEBUG/INFO logs for development use.
RecorderHooks captures full super-step history for post-run test assertions.
LiveGraphHooks records active-node snapshots per super-step for visualization.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from agentflow.describable.graph import Graph
    from agentflow.statemachine.topology import StateGraph
    from agentflow.statemachine.vertex import StateVertex


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

    async def on_super_step_results(
        self,
        step: int,
        node_results: list[tuple[StateVertex, Any, Any]],
    ) -> None:
        """Called after Compute phase, before Apply — provides raw per-vertex results.

        Args:
            step: Super-step counter (1-based).
            node_results: List of (vertex, signal, patch) tuples — one per active vertex.
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

    async def on_super_step_results(
        self,
        step: int,
        node_results: list[tuple[StateVertex, Any, Any]],
    ) -> None:
        """Called after Compute phase with per-vertex results; no-op.

        Args:
            step: Super-step counter (1-based).
            node_results: List of (vertex, signal, patch) tuples.
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

    async def on_super_step_results(
        self,
        step: int,
        node_results: list[tuple[StateVertex, Any, Any]],
    ) -> None:
        """Called after Compute phase; logs each vertex's signal at DEBUG level.

        Args:
            step: Super-step counter (1-based).
            node_results: List of (vertex, signal, patch) tuples.
        """
        for node, signal, _ in node_results:
            self._logger.debug(
                "vertex_result: step=%d node=%s signal=%s",
                step,
                type(node).__name__,
                signal,
            )

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


@dataclasses.dataclass
class SuperStepRecord:
    """Full record of one BSP super-step captured by RecorderHooks.

    Fields are populated incrementally across three callbacks:
    - on_super_step_start  → step, state_before, active_nodes
    - on_super_step_results → results
    - on_super_step_end    → state_after, next_active

    Attributes:
        step: Super-step counter (1-based).
        state_before: State snapshot at the start of the super-step.
        active_nodes: List of vertices executed in this super-step.
        results: Per-vertex (vertex, signal, patch) tuples.
        state_after: State after applying all patches; None until on_super_step_end.
        next_active: Vertices scheduled for the next super-step.
    """

    step: int
    state_before: object
    active_nodes: list[StateVertex]
    results: list[tuple[StateVertex, Any, Any]] = dataclasses.field(default_factory=list)
    state_after: object | None = None
    next_active: set[StateVertex] = dataclasses.field(default_factory=set)


class RecorderHooks:
    """Records full execution history for post-run assertions in tests.

    Implements all RunnerHooks callbacks. Super-step callbacks build a
    SuperStepRecord incrementally; on_super_step_end archives it to history.
    on_run_start, on_run_end, and on_vertex_error are no-ops.

    Attributes:
        history: List of SuperStepRecord, one per completed super-step,
                 in execution order.
    """

    def __init__(self) -> None:
        self.history: list[SuperStepRecord] = []
        self._pending: dict[int, SuperStepRecord] = {}

    async def on_run_start(self, state: object) -> None:
        """Called once before the BSP loop starts; no-op.

        Args:
            state: Initial state passed to runner.run().
        """
        return None

    async def on_super_step_start(
        self,
        step: int,
        state: object,
        active: list[StateVertex],
    ) -> None:
        """Create a pending SuperStepRecord for this super-step.

        Args:
            step: Super-step counter (1-based).
            state: Current state snapshot.
            active: List of vertices about to be executed.
        """
        self._pending[step] = SuperStepRecord(
            step=step,
            state_before=state,
            active_nodes=list(active),
        )

    async def on_super_step_results(
        self,
        step: int,
        node_results: list[tuple[StateVertex, Any, Any]],
    ) -> None:
        """Store per-vertex results in the pending record for this super-step.

        Args:
            step: Super-step counter (1-based).
            node_results: List of (vertex, signal, patch) tuples.
        """
        self._pending[step].results = node_results

    async def on_super_step_end(
        self,
        step: int,
        state: object,
        next_active: set[StateVertex],
    ) -> None:
        """Finalize and archive the pending SuperStepRecord.

        Args:
            step: Super-step counter (same as on_super_step_start).
            state: New state after applying patches.
            next_active: Set of vertices scheduled for the next super-step.
        """
        record = self._pending.pop(step)
        record.state_after = state
        record.next_active = next_active
        self.history.append(record)

    async def on_run_end(self, state: object) -> None:
        """Called once after the BSP loop completes; no-op.

        Args:
            state: Final state after the last super-step.
        """
        return None

    async def on_vertex_error(self, node: StateVertex, exc: Exception) -> None:
        """Called when a vertex raises an exception; no-op.

        Args:
            node: The vertex that raised the exception.
            exc: The exception that was raised.
        """
        return None


class LiveGraphHooks:
    """RunnerHooks that records active-node snapshots per super-step for visualization.

    Each entry in ``snapshots`` corresponds to one completed super-step and holds
    the set of vertex class names that were active at the START of that step.

    Use ``get_snapshot_graph(graph, step)`` to get a ``Graph`` with those
    vertices' ``attributes["active"]`` set to ``True`` — suitable for
    passing to ``GraphRenderer.to_dot()`` for colored visualization.

    Attributes:
        snapshots: list of (step_number, active_class_names) tuples.
    """

    def __init__(self) -> None:
        self.snapshots: list[tuple[int, frozenset[str]]] = []
        self._pending_step: int = 0
        self._pending_active: frozenset[str] = frozenset()

    async def on_run_start(self, state: object) -> None:
        """Called once before the BSP loop starts; no-op.

        Args:
            state: Initial state passed to runner.run().
        """
        return None

    async def on_run_end(self, state: object) -> None:
        """Called once after the BSP loop completes; no-op.

        Args:
            state: Final state after the last super-step.
        """
        return None

    async def on_super_step_start(
        self, step: int, state: object, active: list[StateVertex]
    ) -> None:
        """Record which vertices are active at the start of this super-step.

        Args:
            step: Super-step counter (1-based).
            state: Current state snapshot.
            active: List of vertices about to be executed.
        """
        self._pending_step = step
        self._pending_active = frozenset(type(n).__name__ for n in active)

    async def on_super_step_results(
        self,
        step: int,
        node_results: list[tuple[StateVertex, Any, Any]],
    ) -> None:
        """Called after Compute phase with per-vertex results; no-op.

        Args:
            step: Super-step counter (1-based).
            node_results: List of (vertex, signal, patch) tuples.
        """
        return None

    async def on_super_step_end(
        self, step: int, state: object, next_active: set[StateVertex]
    ) -> None:
        """Archive the pending snapshot when the super-step completes.

        Args:
            step: Super-step counter (same as on_super_step_start).
            state: New state after applying patches.
            next_active: Set of vertices scheduled for the next super-step.
        """
        self.snapshots.append((self._pending_step, self._pending_active))

    async def on_vertex_error(self, node: StateVertex, exc: Exception) -> None:
        """Called when a vertex raises an exception; no-op.

        Args:
            node: The vertex that raised the exception.
            exc: The exception that was raised.
        """
        return None

    def get_snapshot_graph(
        self, graph: StateGraph, step: int
    ) -> Graph:
        """Return graph.get_graph() with active nodes marked in attributes.

        Args:
            graph: The StateGraph that was run.
            step: 1-based step index into self.snapshots.

        Returns:
            Deep-copied Graph with Vertex.attributes["active"] = True for
            active nodes at the given step.
        """
        import copy

        g = copy.deepcopy(graph.get_graph())
        active_names: frozenset[str] = (
            self.snapshots[step - 1][1] if 1 <= step <= len(self.snapshots) else frozenset()
        )
        for v in g.root.children:
            if v.label in active_names:
                v.attributes["active"] = True
        return g
