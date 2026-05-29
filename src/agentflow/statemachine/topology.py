"""Transition, Parallel fan-out, and StateGraph topology queries.

Defines the declarative graph structure: Transition edges, Parallel fan-out
markers, and StateGraph which holds the topology and provides query methods
used by StateGraphRunner during the BSP Apply&Route phase.

Starting from Epic E020, bare StateVertex subclasses (classes, not instances)
are accepted everywhere and auto-instantiated via VertexResolver
(singleton-per-class semantics).
"""

from __future__ import annotations

import dataclasses
import logging
from collections import deque
from collections.abc import Sequence
from typing import TYPE_CHECKING

from src.agentflow.statemachine.resolver import VertexResolver
from src.agentflow.statemachine.state import apply_patches
from src.agentflow.statemachine.vertex import StateVertex

if TYPE_CHECKING:
    from src.agentflow.statemachine.signal import EnumSignal  # noqa: F401

_logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class Transition:
    """A directed edge in the state graph.

    Args:
        from_node: Source vertex — a StateVertex instance or subclass.
        signal: Routing signal emitted by from_node.run().
        to_target: Target — a StateVertex instance/class or a Parallel fan-out.
    """

    from_node: type[StateVertex] | StateVertex
    signal: object  # EnumSignal at runtime — object keeps mypy strict happy
    to_target: type[StateVertex] | StateVertex | Parallel


class Parallel:
    """Fan-out marker: activates all contained vertices in the next super-step.

    Args:
        *vertices: StateVertex instances or subclasses to run in parallel.
    """

    def __init__(self, *vertices: type[StateVertex] | StateVertex) -> None:
        self.vertices: tuple[type[StateVertex] | StateVertex, ...] = vertices

    def expand(self, resolver: VertexResolver) -> list[StateVertex]:
        """Expand and auto-instantiate all branches via resolver.

        Args:
            resolver: VertexResolver for singleton-per-class lookups.

        Returns:
            List of resolved StateVertex instances — each will be scheduled
            for the next BSP super-step.
        """
        return [resolver.resolve(v) for v in self.vertices]


class StateGraph:
    """Immutable state graph holding topology and providing query methods.

    Accepts both pre-instantiated StateVertex objects and bare StateVertex
    subclasses in transitions and as the start node. Classes are
    auto-instantiated via VertexResolver (singleton-per-class) at build time.

    Args:
        start: Starting vertex — a StateVertex instance or subclass.
        transitions: List of Transition edges defining the graph.

    Raises:
        ValueError: If any class in start or transitions has required
            constructor parameters without default values.
    """

    def __init__(
        self,
        start: type[StateVertex] | StateVertex,
        transitions: Sequence[Transition],
    ) -> None:
        self._resolver = VertexResolver()
        self._start = self._resolver.resolve(start)
        self._transitions = self._normalize_transitions(transitions)
        self._analyze_asymmetric_joins()

    def _analyze_asymmetric_joins(self) -> None:
        """Warn about nodes with incoming edges from branches of different depth.

        Builds an in-edge map and successor map from normalized transitions,
        then runs a forward BFS from the start node to compute shortest-path
        distances. For each node with more than one predecessor, emits a
        WARNING if the predecessor distances differ — indicating that one fan-out
        branch is longer than another and the join node may run multiple times
        per cycle.

        Cycles (e.g. Review → Research) are handled safely by a visited set in
        the BFS, ensuring the traversal always terminates.
        """
        # Build in_edges and successors; expand Parallel targets to individual vertices.
        in_edges: dict[StateVertex, list[StateVertex]] = {}
        successors: dict[StateVertex, list[StateVertex]] = {}

        for t in self._transitions:
            from_node = self._resolver.resolve(t.from_node)
            if isinstance(t.to_target, Parallel):
                targets = t.to_target.expand(self._resolver)
            else:
                targets = [self._resolver.resolve(t.to_target)]

            for target in targets:
                successors.setdefault(from_node, []).append(target)
                in_edges.setdefault(target, []).append(from_node)

        # Only join nodes (multiple predecessors) can exhibit asymmetry.
        join_nodes = [node for node, preds in in_edges.items() if len(preds) > 1]
        if not join_nodes:
            return

        # Forward BFS from start; visited set prevents re-processing in cycles.
        distances: dict[StateVertex, int] = {self._start: 0}
        bfs_queue: deque[StateVertex] = deque([self._start])
        visited: set[StateVertex] = {self._start}

        while bfs_queue:
            current = bfs_queue.popleft()
            for neighbor in successors.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    distances[neighbor] = distances[current] + 1
                    bfs_queue.append(neighbor)

        # Warn whenever a join node's predecessors have unequal depths.
        for node in join_nodes:
            preds = in_edges[node]
            depths = [distances.get(p, -1) for p in preds]
            if len(set(depths)) > 1:
                _logger.warning(
                    "Node %r has %d incoming transitions from branches of different depths "
                    "(%s). It may run multiple times per cycle. If barrier semantics are "
                    "needed, ensure branch symmetry or use an explicit Join (not yet "
                    "implemented).",
                    node.__class__.__name__,
                    len(preds),
                    ", ".join(
                        f"{p.__class__.__name__}=depth{d}"
                        for p, d in zip(preds, depths, strict=False)
                    ),
                )

    def _normalize_transitions(self, transitions: Sequence[Transition]) -> list[Transition]:
        """Resolve all class references in transitions to singleton instances.

        For each Transition:
        - from_node: resolved via self._resolver (class or instance → instance).
        - to_target: if Parallel, kept as-is (expanded lazily in expand_target);
          otherwise resolved via self._resolver.

        Args:
            transitions: Raw transitions, possibly containing class references.

        Returns:
            New list of Transition objects with all non-Parallel references resolved.
        """
        normalized: list[Transition] = []
        for t in transitions:
            resolved_from = self._resolver.resolve(t.from_node)
            resolved_to: StateVertex | Parallel
            if isinstance(t.to_target, Parallel):
                resolved_to = t.to_target
            else:
                resolved_to = self._resolver.resolve(t.to_target)
            normalized.append(
                Transition(from_node=resolved_from, signal=t.signal, to_target=resolved_to)
            )
        return normalized

    def resolve_start(self) -> StateVertex:
        """Return the starting vertex instance.

        Returns:
            The start vertex (auto-instantiated if a class was given).
        """
        return self._start

    def get_targets(
        self, node: StateVertex, signal: object
    ) -> list[StateVertex | Parallel]:
        """Return all targets reachable from node via signal.

        Uses identity comparison (``is``) for both node and signal so that
        Enum member singletons behave correctly as signal keys.

        Args:
            node: Source vertex whose transitions to search.
            signal: Signal value to match (by identity).

        Returns:
            List of targets (StateVertex or Parallel instances) for matching
            transitions. Empty list if no matching transition found.
        """
        return [
            t.to_target
            for t in self._transitions
            if t.from_node is node and t.signal is signal
        ]

    def expand_target(self, target: StateVertex | Parallel) -> list[StateVertex]:
        """Expand a target to a flat list of concrete vertex instances.

        Args:
            target: Either a single StateVertex or a Parallel fan-out.

        Returns:
            For a StateVertex: ``[target]``.
            For a Parallel: result of ``target.expand(self._resolver)``.
        """
        if isinstance(target, Parallel):
            return target.expand(self._resolver)
        return [target]

    def apply_patches(self, state: object, patches: Sequence[object]) -> object:
        """Merge patches into a new state instance using per-field reducers.

        Delegates to the standalone apply_patches() function from state.py.

        Args:
            state: Current frozen dataclass state.
            patches: Sequence of StatePatch-like objects.

        Returns:
            New state instance with merged patches.
        """
        return apply_patches(state, patches)
