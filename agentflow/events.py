"""Domain events for agentflow — emitted by vertices, tools, and the runner.

The EventBus collects all events for a run and notifies registered handlers.
It always starts with a LoggingEventHandler so events are visible in logs
even when no custom handler is registered.

Usage::

    from agentflow.events import EventBus, StepStartEvent

    bus = EventBus()
    await bus.emit(StepStartEvent(vertex="Research", step=1))

    # Subscribe a custom handler
    class MyHandler:
        async def on_event(self, event: AgentEvent) -> None:
            print(event.event_type, event.model_dump())

    bus.subscribe(MyHandler())
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class AgentEvent(BaseModel):
    """Base for all domain events emitted by vertices and tools.

    Subclass to define application-specific events (e.g. ReservationEvent).
    The event_type field is used by the GUI to select the correct renderer.

    Attributes:
        event_type: Dot-separated event identifier, e.g. 'agentflow.step_start'.
        timestamp: UTC datetime when the event was created.
        run_id: Unique identifier of the graph run that emitted this event.
    """

    event_type: str
    timestamp: datetime = Field(default_factory=datetime.now)
    run_id: str = ""


class StepStartEvent(AgentEvent):
    """Emitted by the runner when a super-step begins.

    Attributes:
        vertex: Name of the active vertex.
        step: Super-step index (0-based).
    """

    event_type: str = "agentflow.step_start"
    vertex: str
    step: int


class StepEndEvent(AgentEvent):
    """Emitted by the runner when a super-step completes.

    Attributes:
        vertex: Name of the vertex that just ran.
        step: Super-step index (0-based).
        signal: String representation of the routing signal returned.
    """

    event_type: str = "agentflow.step_end"
    vertex: str
    step: int
    signal: str


class QuestionSentEvent(AgentEvent):
    """Emitted by the GUI server when the user submits a question.

    Attributes:
        question: The prompt text submitted by the user.
    """

    event_type: str = "agentflow.question_sent"
    question: str


class LogEvent(AgentEvent):
    """Log message forwarded from a vertex into the event stream.

    Attributes:
        level: Log level string: DEBUG / INFO / WARNING / ERROR.
        message: Human-readable log message.
        logger_name: Python logger name that produced this message.
    """

    event_type: str = "agentflow.log"
    level: str
    message: str
    logger_name: str = ""


class RunCompleteEvent(AgentEvent):
    """Emitted when run_workflow() finishes successfully.

    Attributes:
        result: Optional summary string returned by run_workflow().
    """

    event_type: str = "agentflow.run_complete"
    result: str | None = None


class RunErrorEvent(AgentEvent):
    """Emitted when run_workflow() raises an unhandled exception.

    Attributes:
        message: Error message from the exception.
    """

    event_type: str = "agentflow.run_error"
    message: str


@runtime_checkable
class EventHandler(Protocol):
    """Protocol for event handlers registered on the EventBus.

    Implement this protocol to receive events from the bus.
    """

    async def on_event(self, event: AgentEvent) -> None:
        """Handle a single domain event.

        Args:
            event: The emitted event instance.
        """
        ...


class LoggingEventHandler:
    """Default handler — writes every event to the Python logging system.

    Registered automatically as the first subscriber on every new EventBus.
    Events are logged at DEBUG level under the 'agentflow.events' logger.
    """

    async def on_event(self, event: AgentEvent) -> None:
        """Log event at DEBUG level.

        Args:
            event: The emitted event instance.
        """
        logging.getLogger("agentflow.events").debug(
            "event type=%s data=%s", event.event_type, event.model_dump()
        )


class EventBus:
    """Collects domain events, notifies all registered handlers, and keeps a history.

    Always starts with a LoggingEventHandler as the default subscriber.
    Additional handlers can be added via subscribe().

    Usage::

        bus = EventBus()
        await bus.emit(RunCompleteEvent(result="OK"))
        print(bus.history)
    """

    def __init__(self) -> None:
        self._handlers: list[EventHandler] = [LoggingEventHandler()]
        self._history: list[AgentEvent] = []

    def subscribe(self, handler: EventHandler) -> None:
        """Add a handler to receive future events.

        Args:
            handler: Object implementing the EventHandler protocol.
        """
        self._handlers.append(handler)

    def unsubscribe(self, handler: EventHandler) -> None:
        """Remove a previously registered handler.

        Args:
            handler: Handler instance to remove.

        Raises:
            ValueError: If the handler is not currently subscribed.
        """
        self._handlers.remove(handler)

    async def emit(self, event: AgentEvent) -> None:
        """Append event to history and notify all registered handlers.

        Args:
            event: The event to emit.
        """
        self._history.append(event)
        for handler in self._handlers:
            await handler.on_event(event)

    @property
    def history(self) -> list[AgentEvent]:
        """Return a snapshot of all events emitted since bus creation.

        Returns:
            A new list containing all emitted AgentEvent instances in order.
        """
        return list(self._history)
