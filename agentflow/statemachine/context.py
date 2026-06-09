"""Shared runtime services injected into every vertex run() call.

Context carries the LLM pool, tool registry, logger, and a unique run
identifier. It also exposes run_sync() to bridge blocking sync code into the
async BSP loop. For LLM calls, use ``await ctx.llm_for_model(self.model).achat(...)``
which resolves the appropriate connector from the pool automatically.
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
from agentflow.llm.LlmPool import LlmPool
from agentflow.statemachine.run_stats import RunStats
from agentflow.tools.ToolRegistry import ToolRegistry


@dataclass
class Context(Describable):
    """Shared services container injected into every StateVertex.run() call.

    Args:
        pool: LLM connector pool; manages connector creation and caching
            transparently.  Defaults to ``LlmPool.default()`` which uses
            ``~/.cache/agentflow/llm/agentflow_pool.jsonl``.
        tools: Optional tool registry; None if the graph uses no tools.
        logger: Logger instance; defaults to 'statemachine' logger.
        run_id: Unique identifier for this graph run; auto-generated if omitted.
        event_bus: Domain event bus for publishing step/log/result events.
        tool_registries: Named tool registries for multi-registry graphs.
        stats: Accumulated run statistics; updated by LlmConnectorBase.
        step: Current BSP super-step counter; incremented by StateGraphRunner.
    """

    pool: LlmPool = field(default_factory=LlmPool.default)
    tools: ToolRegistry | None = None
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("statemachine"))
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    event_bus: EventBus = field(default_factory=EventBus)
    tool_registries: dict[str, ToolRegistry] = field(default_factory=dict)
    stats: RunStats = field(default_factory=RunStats)
    step: int = 0

    def __post_init__(self) -> None:
        # @dataclass generates __init__ without calling super().__init__(), so
        # we initialise the Describable internals manually here.
        object.__setattr__(self, "name", type(self).__name__)
        object.__setattr__(self, "description", inspect.getdoc(type(self)) or "")

    # ------------------------------------------------------------------
    # LLM access via pool
    # ------------------------------------------------------------------

    def llm_for_model(self, model: str) -> Any:
        """Return a connector for *model* from the pool.

        Args:
            model: LLM model name (e.g. 'gpt-4o-mini'). Empty string uses
                the environment default connector.

        Returns:
            LLM connector instance ready for ``achat()`` / ``chat()`` calls.
        """
        return self.pool.get_connector(model)

    def llm(self, key: str = "default") -> Any:
        """Return the default LLM connector from the pool.

        The *key* parameter is accepted for backward compatibility but
        ignored — the pool resolves connectors by model name, not by key.
        Use ``llm_for_model(model)`` in new code.

        Args:
            key: Ignored (kept for backward compat with old connector-key API).

        Returns:
            Default LLM connector from the pool.
        """
        return self.pool.get_connector("")

    # ------------------------------------------------------------------
    # Tool registry access
    # ------------------------------------------------------------------

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
    # Describable — expose pool and tool registries in composition graph
    # ------------------------------------------------------------------

    def _extra_describable_children(self) -> dict[str, Any]:
        """Expose LlmPool and tool registries as nested boxes in the graph.

        Returns:
            Dict mapping display name → Describable child instance.
        """
        children: dict[str, Any] = {}
        # LLM pool — single box representing all LLM connections
        if isinstance(self.pool, Describable):
            children["pool"] = self.pool
        # Named tool registries
        for name, reg in self.tool_registries.items():
            display = f"tools_{name}" if name != "default" else "tools"
            if isinstance(reg, Describable):
                children[display] = reg
        # Legacy single registry
        if self.tools is not None and isinstance(self.tools, Describable):
            children.setdefault("tools", self.tools)
        return children
