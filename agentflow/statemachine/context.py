"""Shared runtime services injected into every vertex run() call.

Context carries the LLM pool, tool registry, logger, and a unique run
identifier. It also exposes run_sync() to bridge blocking sync code into the
async BSP loop. For LLM calls, use ``await ctx.llm_for_model(self.model).achat(...)``
which resolves the appropriate connector from the pool automatically.
"""

from __future__ import annotations

import asyncio
import inspect
import json as _json
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


async def _emit_live_state(ctx: Any) -> None:
    """Emit StateUpdateEvent for ctx.live_state if one is registered.

    Sends the display schema on the first emission of a run (to initialise the
    GUI widget), then only state_data on subsequent emissions.

    Args:
        ctx: Context instance — reads live_state and _live_state_schema_sent.
    """
    if ctx.live_state is None:
        return
    if not hasattr(ctx.live_state, "model_dump"):
        return

    from agentflow.events import StateUpdateEvent
    from agentflow.gui.state_viewer import extract_display_schema

    schema_sent: bool = object.__getattribute__(ctx, "_live_state_schema_sent")
    schema = None
    if not schema_sent:
        schema = extract_display_schema(type(ctx.live_state))
        object.__setattr__(ctx, "_live_state_schema_sent", True)

    await ctx.event_bus.emit(StateUpdateEvent(
        state_data=ctx.live_state.model_dump(),
        display_schema=schema,
    ))


class _TrackedConnector:
    """Thin proxy that records token usage and emits tool-call events.

    Wraps any LlmConnectorBase so that every achat() call updates ctx.stats
    and every tool execution inside achat_with_tools() emits a ToolCallEvent.
    All other attributes and methods are forwarded transparently via __getattr__.

    Pattern: Proxy (GoF) — intercepts achat / achat_with_tools; delegates the rest.
    """

    def __init__(self, connector: Any, model: str, ctx: Context) -> None:
        # Use object.__setattr__ to avoid infinite __getattr__ recursion.
        object.__setattr__(self, "_connector", connector)
        object.__setattr__(self, "_model", model)
        object.__setattr__(self, "_ctx", ctx)

    # ------------------------------------------------------------------
    # Intercepted methods
    # ------------------------------------------------------------------

    async def achat(self, messages: list, tools: list | None = None,
                    temperature: float = 0.2, model_override: str | None = None) -> Any:
        """Forward to connector.achat() and record token usage."""
        ctx: Context = object.__getattribute__(self, "_ctx")
        connector = object.__getattribute__(self, "_connector")
        model: str = object.__getattribute__(self, "_model")
        effective_model = model_override or model

        # Check cache before calling to distinguish hit vs. miss.
        cache = getattr(connector, "_cache", None)
        cache_hit = False
        if cache is not None:
            from agentflow.llm.LlmConnectorBase import _make_cache_key
            effective_model = model_override or connector.config.model
            key = _make_cache_key(messages, tools, model=effective_model, temperature=temperature)
            cache_hit = cache.get(key) is not None

        from agentflow.events import LlmCallEvent, LlmResponseEvent
        await ctx.event_bus.emit(LlmCallEvent(
            model=effective_model,
            messages=list(messages),
            tools=list(tools) if tools else None,
            temperature=temperature,
        ))

        response = await connector.achat(messages, tools, temperature, model_override)
        ctx.stats.record(model, response.usage, cache_hit=cache_hit)
        # Update per-step counters used by runner to set StepEndEvent.from_cache.
        if cache_hit:
            ctx._step_cache_hits += 1
        else:
            ctx._step_llm_calls += 1

        tool_calls_data = None
        if response.tool_calls:
            tool_calls_data = [
                {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
                for tc in response.tool_calls
            ]
        usage_data = None
        if response.usage:
            usage_data = {
                "prompt": response.usage.prompt_tokens,
                "completion": response.usage.completion_tokens,
                "total": response.usage.total_tokens,
            }
        await ctx.event_bus.emit(LlmResponseEvent(
            model=effective_model,
            content=response.content,
            tool_calls=tool_calls_data,
            usage=usage_data,
            from_cache=cache_hit,
        ))

        return response

    async def achat_with_tools(
        self,
        messages: list,
        registry: Any,
        max_rounds: int = 10,
        temperature: float = 0.2,
        log: logging.Logger | None = None,
    ) -> Any:
        """Tool-calling loop with per-achat token tracking and ToolCallEvent emission.

        Reimplements LlmConnectorBase.achat_with_tools() so that:
        - each internal achat() call is tracked via self.achat() (usage recorded)
        - each tool execution emits a ToolCallEvent on ctx.event_bus
        - after each tool call, if ctx.live_state is set, emits StateUpdateEvent
        """
        from agentflow.events import ToolCallEvent

        ctx: Context = object.__getattribute__(self, "_ctx")
        _log = log or logging.getLogger(__name__)
        current_messages = list(messages)

        # Emit initial live state (with schema on first call of the run)
        await _emit_live_state(ctx)

        for _ in range(max_rounds):
            response = await self.achat(current_messages, tools=registry.schemas(),
                                        temperature=temperature)
            if not response.has_tool_calls:
                return response

            current_messages.append(response.to_message_dict())
            for tc in (response.tool_calls or []):
                try:
                    args: dict[str, Any] = _json.loads(tc.arguments or "{}")
                except _json.JSONDecodeError:
                    args = {}
                args_fmt = ", ".join(f"{k}={v!r}" for k, v in args.items())
                _log.info("tool_call: %s(%s)", tc.name, args_fmt)
                try:
                    result = registry.execute(tc.name, tc.arguments or "{}")
                except Exception as exc:
                    result = f"ERROR: {exc}"
                _log.info("tool_result: %s → %.120s", tc.name, result)

                await ctx.event_bus.emit(ToolCallEvent(
                    tool_name=tc.name,
                    step=ctx.step,
                    inputs=args,
                    output=str(result),
                ))

                # Emit updated live state after each tool modifies the world
                await _emit_live_state(ctx)

                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": result,
                })

        _log.warning("achat_with_tools: max_rounds=%d reached", max_rounds)
        return await self.achat(current_messages, temperature=temperature)

    def __getattr__(self, name: str) -> Any:
        """Delegate all other attribute access to the wrapped connector."""
        return getattr(object.__getattribute__(self, "_connector"), name)


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
    live_state: Any = None
    """Optional Pydantic BaseModel instance — updated by tools; emitted as
    StateUpdateEvent after each tool call to drive the GUI StateViewerPanel."""
    run_errors: list[str] = field(default_factory=list)
    """Accumulated clean error messages from vertex failures (latest last).
    Populated by StateGraphRunner._safe_run(); read by AgentApp._extract_result()
    to surface meaningful error text instead of a raw state repr."""

    def __post_init__(self) -> None:
        # @dataclass generates __init__ without calling super().__init__(), so
        # we initialise the Describable internals manually here.
        object.__setattr__(self, "name", type(self).__name__)
        object.__setattr__(self, "description", inspect.getdoc(type(self)) or "")
        # Track whether display schema has been sent for live_state in this run.
        object.__setattr__(self, "_live_state_schema_sent", False)
        # Elapsed time set by runner.run() at end; read by server.py for RunStatsEvent.
        object.__setattr__(self, "_run_elapsed_ms", 0.0)
        # Per-step cache/live call counters reset by runner before each step.
        object.__setattr__(self, "_step_cache_hits", 0)
        object.__setattr__(self, "_step_llm_calls", 0)

    # ------------------------------------------------------------------
    # LLM access via pool
    # ------------------------------------------------------------------

    def llm_for_model(self, model: str) -> Any:
        """Return a tracked connector for *model* from the pool.

        The returned connector is wrapped in _TrackedConnector, which records
        token usage into ctx.stats and emits ToolCallEvent during tool loops.

        Args:
            model: LLM model name (e.g. 'gpt-4o-mini'). Empty string uses
                the environment default connector.

        Returns:
            _TrackedConnector proxy ready for ``achat()`` / ``achat_with_tools()`` calls.
        """
        connector = self.pool.get_connector(model)
        try:
            resolved_model = model or connector.config.model
        except (NotImplementedError, AttributeError):
            resolved_model = model or type(connector).__name__
        return _TrackedConnector(connector, resolved_model, self)

    def llm(self, key: str = "default") -> Any:
        """Return the default tracked LLM connector from the pool.

        The *key* parameter is accepted for backward compatibility but
        ignored — the pool resolves connectors by model name, not by key.
        Use ``llm_for_model(model)`` in new code.

        Args:
            key: Ignored (kept for backward compat with old connector-key API).

        Returns:
            Default tracked connector from the pool.
        """
        connector = self.pool.get_connector("")
        try:
            resolved_model = connector.config.model
        except (NotImplementedError, AttributeError):
            resolved_model = type(connector).__name__
        return _TrackedConnector(connector, resolved_model, self)

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
