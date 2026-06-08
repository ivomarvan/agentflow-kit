"""Shared runtime services injected into every vertex run() call.

Context carries the LLM connector, tool registry, logger, and a unique run
identifier. It also exposes run_sync() to bridge blocking sync code into the
async BSP loop. For LLM calls, prefer ``await ctx.connector.achat(...)``
directly — achat() is the preferred async path since Epic E040.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agentflow.describable.describable import Describable
from agentflow.events import EventBus
from agentflow.llm.LlmConnector import LlmConnector
from agentflow.statemachine.run_stats import RunStats
from agentflow.tools.ToolRegistry import ToolRegistry


@dataclass
class Context(Describable):
    """Shared services container injected into every StateVertex.run() call.

    Args:
        connector: LLM connector for all LLM calls within the graph run.
            Optional; use llm_connectors dict for multi-connector graphs.
        tools: Optional tool registry; None if the graph uses no tools.
        logger: Logger instance; defaults to 'statemachine' logger.
        run_id: Unique identifier for this graph run; auto-generated if omitted.
        event_bus: Domain event bus for publishing step/log/result events.
        llm_connectors: Named LLM connectors for multi-LLM graphs.
        tool_registries: Named tool registries for multi-registry graphs.
        stats: Accumulated run statistics; updated by LlmConnectorBase.
        step: Current BSP super-step counter; incremented by StateGraphRunner.
    """

    connector: LlmConnector | None = None
    tools: ToolRegistry | None = None
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("statemachine"))
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    event_bus: EventBus = field(default_factory=EventBus)
    llm_connectors: dict[str, Any] = field(default_factory=dict)
    tool_registries: dict[str, ToolRegistry] = field(default_factory=dict)
    stats: RunStats = field(default_factory=RunStats)
    step: int = 0

    def __post_init__(self) -> None:
        # @dataclass generates __init__ without calling super().__init__(), so
        # we initialise the Describable internals manually here.
        object.__setattr__(self, "name", type(self).__name__)
        object.__setattr__(self, "description", inspect.getdoc(type(self)) or "")

    # ------------------------------------------------------------------
    # Multi-connector / multi-registry access
    # ------------------------------------------------------------------

    def llm(self, key: str = "default") -> Any:
        """Return LLM connector by key from llm_connectors dict.

        Falls back to self.connector for backward compatibility when
        llm_connectors is empty or does not contain the requested key.

        Args:
            key: Named connector key; defaults to "default".

        Returns:
            LLM connector instance.

        Raises:
            ValueError: If no connector is available under the given key
                and no fallback connector is set.
        """
        if self.llm_connectors:
            conn = self.llm_connectors.get(key)
            if conn is None:
                self.logger.warning(
                    "LLM connector key=%r not found; falling back to 'default'", key
                )
                conn = self.llm_connectors.get("default")
            if conn is not None:
                return conn
        # backward compat: fall back to legacy connector field
        if self.connector is not None:
            return self.connector
        raise ValueError(
            f"No LLM connector available (key={key!r}). Set llm_connectors in Context."
        )

    def llm_for_model(self, model: str) -> Any:
        """Return the connector whose active model matches *model*.

        Lookup order:
        1. Scan llm_connectors.values() for the first connector where
           conn.config.model == model.
        2. Fall back to llm() (default connector) when model is empty.
        3. Create a transient LlmConnector(model=model) when no named
           connector matches — log a warning so users can add one for caching.

        Args:
            model: LLM model name (e.g. 'gpt-4o-mini'). Empty string uses the
                default connector.

        Returns:
            LLM connector instance.

        Raises:
            ValueError: Propagated from llm() if no connector is available at all.
        """
        if not model:
            return self.llm()
        for conn in self.llm_connectors.values():
            if hasattr(conn, "config") and conn.config.model == model:
                return conn
        # No named connector matches — create transient without cache
        self.logger.warning(
            "No connector found for model=%r; creating transient connector "
            "(no cache). Add LlmConnector(model=%r) to Context.llm_connectors "
            "to enable caching.",
            model,
            model,
        )
        from agentflow.llm.connectors.LlmConnector import LlmConnector  # avoid circular import
        return LlmConnector(model=model)

    def get_tools(self, key: str = "default") -> ToolRegistry:
        """Return tool registry by key from tool_registries dict.

        Falls back to self.tools for backward compatibility when
        tool_registries is empty or does not contain the requested key.

        Args:
            key: Named registry key; defaults to "default".

        Returns:
            ToolRegistry instance.

        Raises:
            ValueError: If no registry is available under the given key
                and no fallback tools field is set.
        """
        if self.tool_registries:
            reg = self.tool_registries.get(key)
            if reg is None:
                self.logger.warning(
                    "Tool registry key=%r not found; falling back to 'default'", key
                )
                reg = self.tool_registries.get("default")
            if reg is not None:
                return reg
        if self.tools is not None:
            return self.tools
        raise ValueError(
            f"No tool registry available (key={key!r}). Set tool_registries in Context."
        )

    def exceeded(self, n: int) -> bool:
        """Return True if the current step count >= n.

        Args:
            n: Step threshold to compare against.

        Returns:
            True when self.step >= n.
        """
        return self.step >= n

    # ------------------------------------------------------------------
    # Async helpers
    # ------------------------------------------------------------------

    async def run_sync(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run a blocking sync callable from an async vertex without blocking the event loop.

        Wraps fn(*args, **kwargs) in asyncio.to_thread so the BSP event loop
        remains unblocked while waiting for slow sync I/O. Useful for
        user-supplied sync libraries that cannot be awaited directly.

        Args:
            fn: Synchronous callable to execute in a thread pool.
            *args: Positional arguments forwarded to fn.
            **kwargs: Keyword arguments forwarded to fn.

        Returns:
            Return value of fn(*args, **kwargs).
        """
        return await asyncio.to_thread(fn, *args, **kwargs)

    # ------------------------------------------------------------------
    # Describable — expose connectors and registries in composition graph
    # ------------------------------------------------------------------

    def _extra_describable_children(self) -> dict[str, Any]:
        """Expose LLM connectors and tool registries as nested boxes in the graph.

        Named connectors and registries appear inside the Context box so the
        full application composition is visible in graph visualisations.

        Returns:
            Dict mapping display name → Describable child instance.
        """
        children: dict[str, Any] = {}
        # Named connectors from the dict (new API)
        for name, conn in self.llm_connectors.items():
            if isinstance(conn, Describable):
                children[name] = conn
        # Legacy single connector
        if self.connector is not None and isinstance(self.connector, Describable):
            children.setdefault("connector", self.connector)
        # Named tool registries
        for name, reg in self.tool_registries.items():
            display = f"tools_{name}" if name != "default" else "tools"
            if isinstance(reg, Describable):
                children[display] = reg
        # Legacy single registry
        if self.tools is not None and isinstance(self.tools, Describable):
            children.setdefault("tools", self.tools)
        return children
