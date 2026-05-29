"""Shared runtime services injected into every vertex run() call.

Context carries the LLM connector, tool registry, logger, and a unique run
identifier. It also exposes run_sync() to bridge blocking sync code into the
async BSP loop — used until Epic E040 converts LlmConnector to async-first.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.agentflow.llm.LlmConnector import LlmConnector
from src.agentflow.tools.ToolRegistry import ToolRegistry


@dataclass
class Context:
    """Shared services container injected into every StateVertex.run() call.

    Args:
        connector: LLM connector for all LLM calls within the graph run.
        tools: Optional tool registry; None if the graph uses no tools.
        logger: Logger instance; defaults to 'statemachine' logger.
        run_id: Unique identifier for this graph run; auto-generated if omitted.
    """

    connector: LlmConnector
    tools: ToolRegistry | None = None
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("statemachine"))
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    async def run_sync(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run a blocking sync callable from an async vertex without blocking the event loop.

        Wraps fn(*args, **kwargs) in asyncio.to_thread so the BSP event loop
        remains unblocked while waiting for slow sync I/O (LLM calls, tools).
        Remains useful after Epic E040 for user-supplied sync libraries.

        Args:
            fn: Synchronous callable to execute in a thread pool.
            *args: Positional arguments forwarded to fn.
            **kwargs: Keyword arguments forwarded to fn.

        Returns:
            Return value of fn(*args, **kwargs).
        """
        return await asyncio.to_thread(fn, *args, **kwargs)
