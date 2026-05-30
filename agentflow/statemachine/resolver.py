"""VertexResolver — singleton-per-class registry for StateVertex auto-instantiation."""
from __future__ import annotations

import inspect
import logging

from agentflow.statemachine.vertex import StateVertex

logger = logging.getLogger(__name__)


# Pattern: Flyweight (GoF) — one instance per class within a graph lifetime.
class VertexResolver:
    """Singleton-per-class registry for StateVertex auto-instantiation.

    Maintains a cache of StateVertex instances keyed by class. When resolve()
    is called with a class, it creates a new instance on first access and
    returns the cached instance on subsequent calls (Flyweight semantics).
    Each VertexResolver instance is scoped to one StateGraph lifetime.

    Args: none (created per-StateGraph).
    """

    def __init__(self) -> None:
        self._store: dict[type[StateVertex], StateVertex] = {}
        # Name index for lookup_by_name(); first-registration-wins per class name.
        self._name_index: dict[str, StateVertex] = {}

    def resolve(self, v: type[StateVertex] | StateVertex) -> StateVertex:
        """Return v if it is already an instance; otherwise auto-instantiate.

        If v is a StateVertex instance it is returned unchanged (identity).
        Also registers the instance in the name index (first registration per
        class name wins) so that lookup_by_name() can locate it later.

        If v is a StateVertex subclass, the resolver checks the internal cache:
        on first access it validates the constructor, creates an instance, and
        stores it; subsequent calls return the same cached instance.

        Args:
            v: A StateVertex instance or a subclass of StateVertex.

        Returns:
            StateVertex instance — either v itself or the cached/new instance.

        Raises:
            ValueError: If v is a class whose __init__ has parameters without
                default values.
        """
        if isinstance(v, StateVertex):
            # Maintain name index without changing return-value identity.
            cls_name = type(v).__name__
            if cls_name not in self._name_index:
                self._name_index[cls_name] = v
            return v

        cls: type[StateVertex] = v
        if cls not in self._store:
            self._validate_constructor(cls)
            instance = cls()
            self._store[cls] = instance
            self._name_index[cls.__name__] = instance
            logger.debug("Auto-instantiated: class=%s", cls.__name__)

        return self._store[cls]

    def _validate_constructor(self, cls: type[StateVertex]) -> None:
        """Validate that all constructor parameters have default values.

        Uses inspect.signature to examine every parameter of cls.__init__,
        skipping 'self'. Raises immediately on the first parameter without
        a default value.

        Args:
            cls: StateVertex subclass whose constructor is to be validated.

        Raises:
            ValueError: If any parameter lacks a default value.
        """
        sig = inspect.signature(cls)
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            if param.default is inspect.Parameter.empty:
                raise ValueError(
                    f"Cannot auto-instantiate {cls.__name__}: parameter '{name}' has no "
                    "default value. Add a default or pass an instance directly."
                )

    def clear(self) -> None:
        """Remove all cached instances — for test isolation.

        After clear() the next resolve() call for any class will create a
        brand-new instance instead of returning the previously cached one.
        """
        self._store.clear()
        self._name_index.clear()
        logger.debug("VertexResolver cache cleared")

    def lookup_by_name(self, name: str) -> StateVertex | None:
        """Return the registered instance whose class __name__ matches, or None.

        Searches the name index populated by resolve(). For graphs using instance-
        based vertices, first-registration-wins when multiple instances share the
        same class name — use unique subclasses for each node when resume() is needed.

        Args:
            name: The class __name__ to look up (e.g. 'Research', 'StdEnd').

        Returns:
            The registered StateVertex instance, or None if not found.
        """
        return self._name_index.get(name)
