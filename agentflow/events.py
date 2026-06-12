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
from typing import Any, Protocol, runtime_checkable

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
        detail: Serialized input state fields for the GUI details panel (field -> full value).
    """

    event_type: str = "agentflow.step_start"
    vertex: str
    step: int
    detail: dict[str, Any] = Field(default_factory=dict)


class StepEndEvent(AgentEvent):
    """Emitted by the runner when a super-step completes.

    Attributes:
        vertex: Name of the vertex that just ran.
        step: Super-step index (0-based).
        signal: String representation of the routing signal returned.
        detail: Serialized patch fields for the GUI details panel (field -> full value).
        from_cache: True when all LLM calls in this step were served from cache.
    """

    event_type: str = "agentflow.step_end"
    vertex: str
    step: int
    signal: str
    detail: dict[str, Any] = Field(default_factory=dict)
    from_cache: bool = False


class ToolCallEvent(AgentEvent):
    """Emitted by the tracking connector for each tool invocation.

    Attributes:
        tool_name: Name of the tool that was called.
        step: Current BSP super-step index when the call was made.
        inputs: Full argument dict passed to the tool (structured, not truncated).
        output: Full string result returned by the tool (not truncated).
    """

    event_type: str = "agentflow.tool_call"
    tool_name: str
    step: int = 0
    inputs: dict[str, Any] = Field(default_factory=dict)
    output: str = ""


class LlmCallEvent(AgentEvent):
    """Emitted by the tracking connector just before each achat() call.

    Provides full visibility into what is sent to the LLM: the complete
    message history, the list of tools offered, and the temperature used.

    Attributes:
        model: Resolved model identifier used for this call.
        messages: Full OpenAI-format message list sent to the LLM.
        tools: List of tool schemas offered, or None if no tools.
        temperature: Sampling temperature forwarded to the backend.
    """

    event_type: str = "agentflow.llm_call"
    model: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[dict[str, Any]] | None = None
    temperature: float = 0.2


class LlmResponseEvent(AgentEvent):
    """Emitted by the tracking connector after each achat() call completes.

    Provides full visibility into what the LLM returned: the text content,
    any tool calls requested, token usage, and whether the result came from cache.

    Attributes:
        model: Resolved model identifier that produced this response.
        content: Text content of the response (None when only tool_calls).
        tool_calls: List of serialised tool call dicts, or None.
        usage: Token usage breakdown {prompt, completion, total}, or None.
        from_cache: True when the response was served from the LLM cache.
    """

    event_type: str = "agentflow.llm_response"
    model: str
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    usage: dict[str, int] | None = None
    from_cache: bool = False


class RunStatsEvent(AgentEvent):
    """Emitted by the runner at the end of a run with timing and token usage summary.

    Attributes:
        elapsed_ms: Total wall-clock time of the run in milliseconds.
        total_tokens: Sum of all prompt + completion tokens.
        prompt_tokens: Total prompt tokens.
        completion_tokens: Total completion tokens.
        llm_calls: Number of live LLM API calls (cache misses).
        cache_hits: Number of responses served from cache.
        by_model: Per-model breakdown: model -> {prompt, completion, total, calls}.
    """

    event_type: str = "agentflow.run_stats"
    elapsed_ms: float
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0
    cache_hits: int = 0
    by_model: dict[str, dict[str, int]] = Field(default_factory=dict)


class StateUpdateEvent(AgentEvent):
    """Emitted when the live application world-state changes (e.g. after a tool call).

    The GUI ``StateViewerPanel`` component consumes this event to show a live
    visualisation of the external state (smart-home room layout, hotel occupancy, …).

    Attributes:
        state_data: Current state serialised via ``model_dump()``
            (dict with field names as keys).
        display_schema: Display schema produced by ``extract_display_schema()``
            — sent only on the first event of a run to avoid redundant data;
            ``None`` on subsequent events.
    """

    event_type: str = "agentflow.state_update"
    state_data: dict[str, Any] = Field(default_factory=dict)
    display_schema: dict[str, Any] | None = None


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
