"""Python logging handler that forwards log records to the AgentFlow EventBus.

Attach an instance to a Python logger at the start of a workflow run so that
all application log messages appear as ``LogEvent`` items in the GUI event log.
Detach after the run to stop forwarding.

Pattern: Adapter — adapts Python's ``logging.Handler`` interface to the
EventBus observer protocol.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentflow.events import EventBus


class EventBusLoggingHandler(logging.Handler):
    """Logging handler that emits ``LogEvent`` instances onto an EventBus.

    Attach to any Python logger (typically the ``agentflow`` root logger) to
    route log records into the GUI event stream.  The handler schedules the
    async ``bus.emit()`` coroutine on the running event loop so it is safe to
    call from synchronous code inside an async context.

    Args:
        bus: The EventBus to emit ``LogEvent`` objects on.
        level: Minimum log level to forward (default: ``logging.DEBUG``).
    """

    def __init__(self, bus: EventBus, level: int = logging.DEBUG) -> None:
        super().__init__(level)
        self._bus = bus

    def emit(self, record: logging.LogRecord) -> None:
        """Convert *record* to a ``LogEvent`` and schedule it on the bus.

        Uses ``asyncio.get_event_loop().call_soon_threadsafe`` so the handler
        is safe to use even when called from a non-async context.

        Args:
            record: The log record produced by the Python logging framework.
        """
        from agentflow.events import LogEvent

        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()

        event = LogEvent(
            level=record.levelname,
            message=message,
            logger_name=record.name,
        )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no event loop — skip silently

        loop.call_soon_threadsafe(
            lambda: loop.create_task(self._bus.emit(event))
        )
