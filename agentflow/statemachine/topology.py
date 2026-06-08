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
from typing import TYPE_CHECKING, Any

from agentflow.describable.describable import Describable
from agentflow.statemachine.resolver import VertexResolver
from agentflow.statemachine.state import apply_patches
from agentflow.statemachine.vertex import End, StateVertex

if TYPE_CHECKING:
    from agentflow.describable.graph import Edge, Graph, Vertex
    from agentflow.statemachine.signal import EnumSignal  # noqa: F401

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


class StateGraph(Describable):  # type: ignore[misc]
    """Immutable state graph holding topology and providing query methods.

    Accepts both pre-instantiated StateVertex objects and bare StateVertex
    subclasses in transitions and as the start node. Classes are
    auto-instantiated via VertexResolver (singleton-per-class) at build time.

    Args:
        start: Starting vertex — a StateVertex instance or subclass.
        transitions: List of Transition edges defining the graph.
        initialized_vertexes: Optional list of pre-instantiated vertices to
            use instead of auto-creating new instances. When the class of a
            vertex in transitions matches an entry here, the provided instance
            is used rather than calling cls().

    Raises:
        ValueError: If any class in start or transitions has required
            constructor parameters without default values.
    """

    def __init__(
        self,
        start: type[StateVertex] | StateVertex,
        transitions: Sequence[Transition],
        initialized_vertexes: list[StateVertex] | None = None,
    ) -> None:
        super().__init__()
        self._resolver = VertexResolver()
        if initialized_vertexes:
            self._resolver.seed(initialized_vertexes)
        self._start = self._resolver.resolve(start)
        self._transitions = self._normalize_transitions(transitions)
        self._analyze_asymmetric_joins()

    @staticmethod
    def _can_reach(
        src: StateVertex,
        dst: StateVertex,
        successors: dict[StateVertex, list[StateVertex]],
    ) -> bool:
        """Return True if *dst* is reachable from *src* via forward successor edges.

        Uses a visited set so cycles terminate. *src* itself does not count as
        reaching *dst* unless there is an actual edge path of length >= 1.

        Args:
            src: Start vertex for forward traversal.
            dst: Target vertex to reach.
            successors: Adjacency map from normalized transitions.

        Returns:
            True when a forward path from *src* to *dst* exists.
        """
        stack = list(successors.get(src, []))
        visited: set[StateVertex] = set()
        while stack:
            cur = stack.pop()
            if cur is dst:
                return True
            if cur in visited:
                continue
            visited.add(cur)
            stack.extend(successors.get(cur, []))
        return False

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

        # Warn only when forward (non-back-edge) predecessors have unequal depths.
        for node in join_nodes:
            preds = in_edges[node]
            forward_preds = [p for p in preds if not self._can_reach(node, p, successors)]
            if len(forward_preds) < 2:
                continue
            depths = [distances.get(p, -1) for p in forward_preds]
            if len(set(depths)) > 1:
                _logger.warning(
                    "Node %r has %d incoming transitions from branches of different depths "
                    "(%s). It may run multiple times per cycle. If barrier semantics are "
                    "needed, ensure branch symmetry or use an explicit Join (not yet "
                    "implemented).",
                    node.__class__.__name__,
                    len(forward_preds),
                    ", ".join(
                        f"{p.__class__.__name__}=depth{d}"
                        for p, d in zip(forward_preds, depths, strict=False)
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

    @property
    def vertices(self) -> list[StateVertex]:
        """Return all resolved vertex instances registered in this graph.

        Includes every vertex that has been resolved (auto-instantiated or
        pre-seeded) by the internal ``VertexResolver``.  Useful for GUI
        tooling that needs to iterate over configurable graph nodes.

        Returns:
            List of ``StateVertex`` instances in registration order.
        """
        return list(self._resolver._name_index.values())

    def get_targets(self, node: StateVertex, signal: object) -> list[StateVertex | Parallel]:
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
            t.to_target for t in self._transitions if t.from_node is node and t.signal is signal
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

    # ------------------------------------------------------------------
    # Describable — topology graph override
    # ------------------------------------------------------------------

    def get_graph(self) -> Graph:
        """Build a topology Graph: one Vertex per unique node, one Edge per transition.

        Overrides ``Describable.get_graph()`` to produce a state-machine
        topology graph rather than a composition tree.  The root vertex
        summarises the whole graph; its children are the individual node
        vertices.  Directed edges represent transitions labelled with
        signal names.

        Returns:
            ``Graph`` whose root children = topology nodes, edges = transitions.
        """
        from agentflow.describable.graph import Graph, Vertex

        nodes = self._collect_topology_nodes()
        node_ids = self._build_node_ids(nodes)

        vertices = [self._make_node_vertex(n, node_ids, is_start=(n is self._start)) for n in nodes]
        edges = self._make_topology_edges(node_ids)

        root = Vertex(
            id="StateGraph",
            label="StateGraph",
            description={"nodes": len(nodes), "transitions": len(self._transitions)},
            children=vertices,
        )
        return Graph(root=root, edges=edges)

    def _build_vertex(self, vertex_id: str) -> Vertex:
        """Expose topology nodes as children when StateGraph is embedded in a parent.

        When a parent Describable (e.g. ExampleApp) calls _build_vertex() on this
        StateGraph, the returned Vertex includes the topology nodes as children,
        making them visible in the composite graph visualization.

        Args:
            vertex_id: Dot-path identifier from the parent, e.g. "MyApp.graph".

        Returns:
            Vertex whose children are the topology nodes (same as get_graph().root.children).
        """
        from agentflow.describable.describable import Describable
        from agentflow.describable.graph import Vertex  # noqa: F811 — local import avoids circular

        topology = self.get_graph()
        source_file, source_line = Describable._class_source_location(type(self))
        return Vertex(
            id=vertex_id,
            label=type(self).__name__,
            description=self.get_description_item_dict(),
            children=list(topology.root.children),
            source_file=source_file,
            source_line=source_line,
        )

    def _collect_topology_nodes(self) -> list[StateVertex]:
        """Collect all unique StateVertex instances referenced by this graph.

        Iterates over ``self._start`` and all normalized transitions,
        expanding ``Parallel`` fan-outs via the resolver.  Deduplicates
        by object identity (``id()``).

        Returns:
            Ordered list of unique ``StateVertex`` instances.
        """
        seen: set[int] = set()
        nodes: list[StateVertex] = []

        def _add(node: StateVertex) -> None:
            if id(node) not in seen:
                seen.add(id(node))
                nodes.append(node)

        _add(self._start)
        for t in self._transitions:
            _add(t.from_node)
            if isinstance(t.to_target, Parallel):
                for branch in t.to_target.expand(self._resolver):
                    _add(branch)
            else:
                _add(t.to_target)

        return nodes

    def _build_node_ids(self, nodes: list[StateVertex]) -> dict[int, str]:
        """Assign a unique string ID to every node, handling class-name collisions.

        When all nodes have distinct class names, each ID equals the class
        name.  When multiple instances share a class name, each gets an
        indexed suffix: ``ClassName_0``, ``ClassName_1``, …

        Args:
            nodes: Ordered list of unique ``StateVertex`` instances.

        Returns:
            Dict mapping ``id(node)`` → unique string ID.
        """
        # Count how many nodes share each class name.
        name_counts: dict[str, int] = {}
        for node in nodes:
            cls_name = type(node).__name__
            name_counts[cls_name] = name_counts.get(cls_name, 0) + 1

        name_index: dict[str, int] = {}
        node_ids: dict[int, str] = {}
        for node in nodes:
            cls_name = type(node).__name__
            if name_counts[cls_name] == 1:
                node_ids[id(node)] = cls_name
            else:
                i = name_index.get(cls_name, 0)
                node_ids[id(node)] = f"{cls_name}_{i}"
                name_index[cls_name] = i + 1

        return node_ids

    def _make_node_vertex(
        self,
        node: StateVertex,
        node_ids: dict[int, str],
        *,
        is_start: bool,
    ) -> Vertex:
        """Create a topology Vertex for a single node.

        The vertex description contains only the class docstring (if any).
        The class name is already the vertex label and is not repeated.

        Args:
            node: The ``StateVertex`` instance to represent.
            node_ids: ID mapping from ``_build_node_ids()``.
            is_start: Whether this node is the graph start node.

        Returns:
            ``Vertex`` with topology metadata in ``description`` and ``attributes``.
        """
        import inspect

        from agentflow.describable.describable import Describable
        from agentflow.describable.graph import Vertex

        cls_name = type(node).__name__
        source_file, source_line = Describable._class_source_location(type(node))
        attributes: dict[str, Any] = {}
        if is_start:
            attributes["is_start"] = True
        if isinstance(node, End):
            attributes["is_end"] = True

        doc = inspect.getdoc(type(node)) or ""
        description: dict[str, Any] = {}
        if doc:
            description["description"] = doc

        return Vertex(
            id=node_ids[id(node)],
            label=cls_name,
            description=description,
            attributes=attributes,
            source_file=source_file,
            source_line=source_line,
        )

    def _make_topology_edges(self, node_ids: dict[int, str]) -> list[Edge]:
        """Build the list of directed edges from normalized transitions.

        Each transition produces one Edge, except for ``Parallel`` targets
        which fan out to one Edge per branch.

        Args:
            node_ids: ID mapping from ``_build_node_ids()``.

        Returns:
            List of ``Edge`` objects for ``Graph.edges``.
        """
        from agentflow.describable.graph import Edge

        edges: list[Edge] = []
        for t in self._transitions:
            from_id = node_ids[id(t.from_node)]
            label = getattr(t.signal, "name", str(t.signal))

            if isinstance(t.to_target, Parallel):
                for branch in t.to_target.expand(self._resolver):
                    edges.append(
                        Edge(
                            from_id=from_id,
                            to_id=node_ids[id(branch)],
                            label=label,
                            attributes={"parallel": True},
                        )
                    )
            else:
                edges.append(Edge(from_id=from_id, to_id=node_ids[id(t.to_target)], label=label))

        return edges

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
