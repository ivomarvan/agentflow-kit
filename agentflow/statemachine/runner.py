"""StateGraphRunner — BSP super-step execution loop.

Implements the Bulk Synchronous Parallel (BSP) model:
  Compute (parallel via asyncio.gather)
  → Barrier (implicit in gather)
  → Apply (per-field reducer merge)
  → Route (set-based implicit join)

The loop terminates when all active nodes are End instances.
Vertex exceptions are caught by _safe_run and mapped to StdSignal.fail.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from agentflow.statemachine.checkpoint import CheckpointRecord, CheckpointStore
from agentflow.statemachine.context import Context
from agentflow.statemachine.hooks import NoOpHooks, RunnerHooks
from agentflow.statemachine.signal import StdSignal
from agentflow.statemachine.topology import StateGraph
from agentflow.statemachine.vertex import End, StateVertex

_logger = logging.getLogger(__name__)


class StateGraphRunner:
    """Executes a StateGraph using the Bulk Synchronous Parallel (BSP) model.

    Args:
        graph: StateGraph instance defining topology and transitions.
        context: Shared services injected into each vertex.
        hooks: Optional observability callbacks; defaults to NoOpHooks.
    """

    def __init__(
        self,
        graph: StateGraph,
        context: Context,
        hooks: RunnerHooks | None = None,
    ) -> None:
        self.graph = graph
        self.context = context
        # NoOpHooks satisfies RunnerHooks structurally via duck-typing on the Protocol.
        self.hooks: RunnerHooks = hooks if hooks is not None else NoOpHooks()

    async def run(self, initial_state: Any) -> Any:
        """Execute the graph from initial_state until all active nodes are End instances.

        BSP loop: for each super-step, all active non-End vertices run in
        parallel (Compute), results are gathered (Barrier), state patches
        are merged (Apply), and next active nodes are determined (Route).

        End vertices are executed last in the step in which they appear;
        the loop terminates immediately after that.

        Args:
            initial_state: Starting frozen dataclass state.

        Returns:
            Final state after the last super-step (after End node ran).
        """
        current_state = initial_state
        active_nodes: list[StateVertex] = [self.graph.resolve_start()]
        step = 0

        await self.hooks.on_run_start(current_state)

        while active_nodes:
            # End nodes are run last in this step, then the loop exits.
            end_nodes = [n for n in active_nodes if isinstance(n, End)]
            for end in end_nodes:
                await self._safe_run(end, current_state)
            active_nodes = [n for n in active_nodes if not isinstance(n, End)]
            if not active_nodes:
                break

            step += 1
            await self.hooks.on_super_step_start(step, current_state, active_nodes)

            # --- PHASE 1: COMPUTE (parallel) ---
            results: list[tuple[Any, Any]] = list(
                await asyncio.gather(
                    *(self._safe_run(node, current_state) for node in active_nodes)
                )
            )

            # --- PHASE 2: BARRIER already happened (gather synchronises) ---

            node_results = [
                (node, signal, patch)
                for node, (signal, patch) in zip(active_nodes, results, strict=True)
            ]
            await self.hooks.on_super_step_results(step, node_results)

            # --- PHASE 3A: APPLY (per-field reducers) ---
            patches = [patch for _, patch in results]
            current_state = self.graph.apply_patches(current_state, patches)

            # --- PHASE 3B: ROUTE (set-based implicit join) ---
            next_set: set[StateVertex] = set()
            for node, (signal, _) in zip(active_nodes, results, strict=True):
                for target in self.graph.get_targets(node, signal):
                    for vertex in self.graph.expand_target(target):
                        next_set.add(vertex)

            await self.hooks.on_super_step_end(step, current_state, next_set)
            self.context.step += 1
            active_nodes = list(next_set)

        await self.hooks.on_run_end(current_state)
        return current_state

    def run_sync(self, initial_state: Any) -> Any:
        """Synchronous entry point — runs the entire graph in a new event loop.

        Convenience wrapper for CLI scripts and tests that do not manage an event
        loop themselves. Uses asyncio.run() internally, which means it cannot be
        called from within an already-running event loop (e.g. plain Jupyter cells).

        Args:
            initial_state: Starting frozen dataclass state.

        Returns:
            Final state after the last super-step.
        """
        return asyncio.run(self.run(initial_state))

    async def run_until(
        self,
        initial_state: Any,
        predicate: Callable[[int, Any, list[StateVertex]], bool],
        *,
        store: CheckpointStore,
        run_id: str,
    ) -> Any:
        """Run BSP loop; save checkpoint after each step; stop when predicate is True.

        Identical to run() except: after each super-step, saves a CheckpointRecord
        and evaluates predicate(step, state, next_active_nodes). When predicate
        returns True, the loop pauses and current state is returned.

        Use runner.resume(store, run_id, from_step) to continue execution.

        Args:
            initial_state: Starting state.
            predicate: (step, state, active_nodes) -> bool. True = pause here.
            store: CheckpointStore used to persist checkpoints.
            run_id: Unique run identifier for checkpoint keys.

        Returns:
            State at time of pause (or final state if predicate never True).
        """
        current_state = initial_state
        active_nodes: list[StateVertex] = [self.graph.resolve_start()]
        step = 0

        await self.hooks.on_run_start(current_state)

        while active_nodes:
            end_nodes = [n for n in active_nodes if isinstance(n, End)]
            for end in end_nodes:
                await self._safe_run(end, current_state)
            active_nodes = [n for n in active_nodes if not isinstance(n, End)]
            if not active_nodes:
                break

            step += 1
            await self.hooks.on_super_step_start(step, current_state, active_nodes)

            results: list[tuple[Any, Any]] = list(
                await asyncio.gather(
                    *(self._safe_run(node, current_state) for node in active_nodes)
                )
            )

            node_results = [
                (node, signal, patch)
                for node, (signal, patch) in zip(active_nodes, results, strict=True)
            ]
            await self.hooks.on_super_step_results(step, node_results)

            patches = [patch for _, patch in results]
            current_state = self.graph.apply_patches(current_state, patches)

            next_set: set[StateVertex] = set()
            for node, (signal, _) in zip(active_nodes, results, strict=True):
                for target in self.graph.get_targets(node, signal):
                    for vertex in self.graph.expand_target(target):
                        next_set.add(vertex)

            await self.hooks.on_super_step_end(step, current_state, next_set)
            self.context.step += 1
            active_nodes = list(next_set)

            await store.save(
                CheckpointRecord(
                    run_id=run_id,
                    step=step,
                    state=current_state,
                    active_node_names=[type(n).__name__ for n in active_nodes],
                )
            )
            if predicate(step, current_state, active_nodes):
                await self.hooks.on_run_end(current_state)
                return current_state

        await self.hooks.on_run_end(current_state)
        return current_state

    async def resume(
        self,
        store: CheckpointStore,
        run_id: str,
        from_step: int,
    ) -> Any:
        """Resume execution from a checkpoint saved by run_until().

        Loads the checkpoint at (run_id, from_step), resolves active_node_names
        to StateVertex instances via graph._resolver.lookup_by_name(), then
        continues the BSP loop from there.

        Args:
            store: Same CheckpointStore used in run_until().
            run_id: Same run_id used in run_until().
            from_step: The step to resume from (checkpoint must exist).

        Returns:
            Final state after the graph completes.

        Raises:
            KeyError: If the checkpoint for (run_id, from_step) does not exist.
            ValueError: If a vertex name from the checkpoint cannot be resolved.
        """
        record = await store.load(run_id, from_step)
        active_nodes: list[StateVertex] = []
        for name in record.active_node_names:
            vertex = self.graph._resolver.lookup_by_name(name)
            if vertex is None:
                raise ValueError(
                    f"Cannot resolve checkpoint vertex {name!r} — "
                    "ensure the same graph is used for both run_until and resume."
                )
            active_nodes.append(vertex)

        current_state = record.state
        step = from_step

        await self.hooks.on_run_start(current_state)

        while active_nodes:
            end_nodes = [n for n in active_nodes if isinstance(n, End)]
            for end in end_nodes:
                await self._safe_run(end, current_state)
            active_nodes = [n for n in active_nodes if not isinstance(n, End)]
            if not active_nodes:
                break

            step += 1
            await self.hooks.on_super_step_start(step, current_state, active_nodes)

            results: list[tuple[Any, Any]] = list(
                await asyncio.gather(
                    *(self._safe_run(node, current_state) for node in active_nodes)
                )
            )

            node_results = [
                (node, signal, patch)
                for node, (signal, patch) in zip(active_nodes, results, strict=True)
            ]
            await self.hooks.on_super_step_results(step, node_results)

            patches = [patch for _, patch in results]
            current_state = self.graph.apply_patches(current_state, patches)

            next_set: set[StateVertex] = set()
            for node, (signal, _) in zip(active_nodes, results, strict=True):
                for target in self.graph.get_targets(node, signal):
                    for vertex in self.graph.expand_target(target):
                        next_set.add(vertex)

            await self.hooks.on_super_step_end(step, current_state, next_set)
            self.context.step += 1
            active_nodes = list(next_set)

        await self.hooks.on_run_end(current_state)
        return current_state

    async def _safe_run(self, node: StateVertex, state: Any) -> tuple[Any, Any]:
        """Execute a vertex with exception handling.

        Maps any unexpected exception to (StdSignal.fail, _EmptyPatch()) so that
        a single vertex failure does not crash the entire super-step. Calls
        hooks.on_vertex_error before returning the failure tuple.

        Args:
            node: Vertex to execute.
            state: Current state snapshot.

        Returns:
            Tuple (signal, patch). On exception: (StdSignal.fail, _EmptyPatch()).
        """
        try:
            result: tuple[Any, Any] = await node.run(state, self.context)
            return result
        except Exception as exc:
            _logger.exception(
                "Vertex failed: node=%s exc_type=%s",
                type(node).__name__,
                type(exc).__name__,
            )
            await self.hooks.on_vertex_error(node, exc)
            from agentflow.statemachine.vertex import _EmptyPatch  # noqa: PLC0415

            return StdSignal.fail, _EmptyPatch()
