"""Transition, Parallel fan-out, and StateGraph topology queries.

Defines the declarative graph structure: Transition edges, Parallel fan-out
markers, and StateGraph which holds the topology and provides query methods
used by StateGraphRunner during the BSP Apply&Route phase.

In Epic E010 only manually instantiated vertices are supported.
Auto-instantiation (VertexResolver singleton-per-class) will be added in E020.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from src.agentflow.statemachine.state import apply_patches
from src.agentflow.statemachine.vertex import StateVertex

if TYPE_CHECKING:
    from src.agentflow.statemachine.signal import EnumSignal  # noqa: F401

_logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class Transition:
    """A directed edge in the state graph.

    Args:
        from_node: Source vertex instance.
        signal: Routing signal emitted by from_node.run().
        to_target: Target — a StateVertex instance or a Parallel fan-out.
    """

    from_node: StateVertex
    signal: object  # EnumSignal at runtime — object keeps mypy strict happy
    to_target: StateVertex | Parallel


class Parallel:
    """Fan-out marker: activates all contained vertices in the next super-step.

    Args:
        *vertices: StateVertex instances to run in parallel.
    """

    def __init__(self, *vertices: StateVertex) -> None:
        self.vertices: tuple[StateVertex, ...] = vertices

    def expand(self) -> list[StateVertex]:
        """Return all contained vertex instances as a flat list.

        Returns:
            List of StateVertex instances — each will be scheduled for the
            next BSP super-step.
        """
        return list(self.vertices)


class StateGraph:
    """Immutable state graph holding topology and providing query methods.

    Accepts only pre-instantiated StateVertex objects in transitions.
    Passing a class (not an instance) raises TypeError with a helpful message
    pointing to Epic E020 for auto-instantiation support.

    Args:
        start: Starting vertex instance.
        transitions: List of Transition edges defining the graph.

    Raises:
        TypeError: If any transition contains a class rather than an instance.
    """

    def __init__(
        self,
        start: StateVertex,
        transitions: Sequence[Transition],
    ) -> None:
        self._start = start
        self._transitions = list(transitions)
        self._validate_no_classes()

    def _validate_no_classes(self) -> None:
        """Guard against passing classes instead of instances — E020 note."""
        for t in self._transitions:
            for field_name, node in [("from_node", t.from_node), ("to_target", t.to_target)]:
                if isinstance(node, type):
                    raise TypeError(
                        f"Transition {field_name}={node.__name__!r} is a class, not an instance. "
                        "Auto-instantiation will be added in Epic E020; "
                        "pass an instance (e.g. MyVertex()) for now."
                    )

    def resolve_start(self) -> StateVertex:
        """Return the starting vertex instance.

        Returns:
            The start vertex passed to __init__.
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
            For a Parallel: result of ``target.expand()``.
        """
        if isinstance(target, Parallel):
            return target.expand()
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
