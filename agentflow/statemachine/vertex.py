"""StateVertex, LlmStateVertex, and terminal node implementations.

StateVertex is the Pydantic BaseModel base for all graph nodes.
Subclasses that call ctx.llm_for_model() should inherit from LlmStateVertex,
which adds model and temperature as configurable parameters.

Terminal nodes (End, StdEnd) extend StateVertex directly — no LLM fields needed.

Example — pure state-transformation vertex (no LLM):

    class ToolExecutionVertex(StateVertex):
        tools: Annotated[str, Field(description="Tool registry key.")] = "default"

        async def run(self, state, ctx):
            ...

Example — LLM vertex with model + temperature:

    class MyLlmVertex(LlmStateVertex):
        max_steps: Annotated[int, Field(ge=1, description="Max LLM calls.")] = 10

        async def run(self, state, ctx):
            response = await ctx.llm_for_model(self.model).achat(...)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from agentflow.describable.describable import Describable
from agentflow.statemachine.signal import StdSignal

if TYPE_CHECKING:
    from agentflow.statemachine.context import Context

_logger = logging.getLogger(__name__)

_PYDANTIC_INTERNAL_ATTRS = frozenset({
    "model_fields",
    "model_config",
    "model_fields_set",
    "__dict__",
    "__pydantic_fields_set__",
    "__pydantic_extra__",
    "__pydantic_private__",
})


class StateVertex(Describable, BaseModel):
    """Abstract base for all graph nodes (no LLM fields).

    Subclass and implement run(). Class-level Annotated[T, Field(...)] attributes
    are automatically treated as constructor parameters with validation.

    For vertices that call ctx.llm_for_model(), inherit from LlmStateVertex instead.

    All default parameter values must be provided (or the class must be in
    StateGraph.initialized_vertexes) for auto-instantiation to work.

    Inherits from Describable so GUI tooling can call get_config_schema(),
    get_param_values(), and set_params() to inspect and edit parameters at
    runtime.
    """

    model_config = ConfigDict(
        frozen=False,                # run() may assign self.x = ... at runtime
        extra="allow",               # runtime attributes (e.g. self._cache) OK
        arbitrary_types_allowed=True,
    )

    # Restore Python's identity-based hash (Pydantic sets __hash__=None for mutable models).
    # StateVertex instances are used as dict keys and set members in the graph topology.
    __hash__ = object.__hash__  # type: ignore[assignment]

    def _get_own_attributes(self) -> dict[str, Any]:
        """Include Pydantic declared fields in the description/tooltip.

        Pydantic v2 stores field values in __dict__ but the base
        Describable._get_own_attributes() skips private attrs and Describable
        children.  Here we explicitly add all Pydantic model fields so that
        parameters like model, temperature, max_steps etc. appear in tooltips.
        """
        attrs = super()._get_own_attributes()
        for field_name in type(self).model_fields:
            value = getattr(self, field_name, None)
            if isinstance(value, Describable):
                continue
            attrs[field_name] = value
        return attrs

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Execute this vertex for one BSP super-step.

        Override in subclasses. Must return (signal, patch).

        Args:
            state: Current immutable state snapshot.
            ctx:   Shared services (LLM pool, tools, logger, run_id, stats).

        Returns:
            Tuple of (EnumSignal, StatePatch).

        Raises:
            NotImplementedError: Always — subclasses must override this method.
        """
        raise NotImplementedError(
            f"{type(self).__name__}.run() must be implemented"
        )


class LlmStateVertex(StateVertex):
    """StateVertex subclass for nodes that call ctx.llm_for_model().

    Adds two Pydantic fields that are configurable via the GUI Inspector:

        model: str      — LLM model name (e.g. 'gpt-4o-mini').
                          Empty string → use the pool's environment default.
        temperature: float — Sampling temperature (0 = deterministic, 2 = creative).

    Inherit from this class whenever a vertex issues LLM requests:

        class MyVertex(LlmStateVertex):
            async def run(self, state, ctx):
                response = await ctx.llm_for_model(self.model).achat(
                    messages, temperature=self.temperature
                )
    """

    model: Annotated[str, Field(
        description=(
            "LLM model name (e.g. 'gpt-4o-mini'). "
            "Empty string = use Context pool's environment default."
        ),
        json_schema_extra={"x-model-select": True},
    )] = ""
    temperature: Annotated[float, Field(
        ge=0.0,
        le=2.0,
        description="LLM sampling temperature (0 = deterministic, 2 = creative).",
    )] = 0.2


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
