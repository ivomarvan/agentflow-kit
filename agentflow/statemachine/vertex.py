"""StateVertex and terminal node implementations.

StateVertex is a Pydantic BaseModel so subclasses can declare configurable
parameters as class-level Annotated[T, Field(...)] attributes:

    class MyVertex(StateVertex):
        max_steps: Annotated[int, Field(ge=1, description="...")] = 10

        async def run(self, state, ctx):
            ...self.max_steps...

No __init__ needed — Pydantic generates it automatically with validation.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from agentflow.describable.describable import Describable
from agentflow.statemachine.signal import StdSignal

if TYPE_CHECKING:
    from agentflow.statemachine.context import Context

_logger = logging.getLogger(__name__)


class StateVertex(Describable, BaseModel):
    """Abstract base for all graph nodes.

    Subclass and implement run(). Class-level Annotated[T, Field(...)] attributes
    are automatically treated as constructor parameters with validation.

    All default parameter values must be provided (or the class must be in
    StateGraph.initialized_vertexes) for auto-instantiation to work.

    Inherits from Describable so GUI tooling can call get_config_schema(),
    get_param_values(), and set_params() to inspect and edit parameters at
    runtime.  Because Describable.__init__ accepts **kwargs and forwards them
    to BaseModel.__init__, cooperative multiple inheritance works without any
    extra plumbing in StateVertex.
    """

    model_config = ConfigDict(
        frozen=False,                # run() may assign self.x = ... at runtime
        extra="allow",               # runtime attributes (e.g. self._cache) OK
        arbitrary_types_allowed=True,
    )

    # Restore Python's identity-based hash (Pydantic sets __hash__=None for mutable models).
    # StateVertex instances are used as dict keys and set members in the graph topology.
    __hash__ = object.__hash__  # type: ignore[assignment]

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Execute this vertex for one BSP super-step.

        Override in subclasses. Must return (signal, patch).

        Args:
            state: Current immutable state snapshot.
            ctx:   Shared services (LLM connectors, tools, logger, run_id, stats).

        Returns:
            Tuple of (EnumSignal, StatePatch).

        Raises:
            NotImplementedError: Always — subclasses must override this method.
        """
        raise NotImplementedError(
            f"{type(self).__name__}.run() must be implemented"
        )


class End(StateVertex):
    """Marker base class for terminal nodes.

    The runner detects end-of-run by isinstance(active_node, End).
    Subclass to add custom termination logic.
    """

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Termination stub — override in concrete End subclasses.

        Args:
            state: Current state.
            ctx:   Shared context.

        Returns:
            Tuple of (EnumSignal, StatePatch).

        Raises:
            NotImplementedError: Always — subclasses must override this method.
        """
        raise NotImplementedError(
            f"{type(self).__name__}.run() must be implemented"
        )


class StdEnd(End):
    """Standard terminal node — signals done with an empty patch."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Return done signal with empty patch to terminate the run.

        Args:
            state: Current state (ignored).
            ctx:   Shared context (ignored).

        Returns:
            Tuple (StdSignal.done, empty StatePatch-compatible object).
        """
        return StdSignal.done, _EmptyPatch()


class _EmptyPatch:
    """Sentinel patch that applies no changes to any state."""
    pass
