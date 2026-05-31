"""Unit tests for AgentEvent, EventBus, and related event infrastructure."""
from __future__ import annotations

import asyncio

import pytest

from agentflow import (
    AgentEvent,
    EventBus,
    LogEvent,
    LoggingEventHandler,
    RunCompleteEvent,
    StepStartEvent,
)
from agentflow.events import EventHandler
from agentflow.statemachine import Context
from agentflow.statemachine.testing import FakeLlmConnector


class _RecordingHandler:
    """Captures events for assertions."""

    def __init__(self) -> None:
        self.received: list[AgentEvent] = []

    async def on_event(self, event: AgentEvent) -> None:
        self.received.append(event)


@pytest.mark.unit
def test_event_bus_subscribe_and_emit() -> None:
    """subscribe() + emit() should call the handler with the event."""
    bus = EventBus()
    handler = _RecordingHandler()
    bus.subscribe(handler)

    event = AgentEvent(event_type="test.event")
    asyncio.run(bus.emit(event))

    assert len(handler.received) == 1
    assert handler.received[0].event_type == "test.event"


@pytest.mark.unit
def test_event_bus_history() -> None:
    """Emitted events should appear in bus.history."""
    bus = EventBus()
    e1 = AgentEvent(event_type="first")
    e2 = AgentEvent(event_type="second")
    asyncio.run(bus.emit(e1))
    asyncio.run(bus.emit(e2))

    history = bus.history
    assert len(history) == 2
    assert history[0].event_type == "first"
    assert history[1].event_type == "second"


@pytest.mark.unit
def test_event_bus_history_is_snapshot() -> None:
    """bus.history should return a copy — mutating it should not affect the bus."""
    bus = EventBus()
    asyncio.run(bus.emit(AgentEvent(event_type="x")))
    snapshot = bus.history
    snapshot.clear()
    assert len(bus.history) == 1


@pytest.mark.unit
def test_logging_event_handler_is_default() -> None:
    """A new EventBus should start with LoggingEventHandler subscribed."""
    bus = EventBus()
    assert any(isinstance(h, LoggingEventHandler) for h in bus._handlers)


@pytest.mark.unit
def test_context_has_event_bus() -> None:
    """Context() should have an event_bus attribute of type EventBus."""
    ctx = Context(connector=FakeLlmConnector())
    assert hasattr(ctx, "event_bus")
    assert isinstance(ctx.event_bus, EventBus)


@pytest.mark.unit
def test_context_event_bus_is_independent() -> None:
    """Each Context instance should get its own EventBus."""
    ctx1 = Context(connector=FakeLlmConnector())
    ctx2 = Context(connector=FakeLlmConnector())
    assert ctx1.event_bus is not ctx2.event_bus


@pytest.mark.unit
def test_custom_agent_event_subclass() -> None:
    """Users should be able to define custom AgentEvent subclasses."""

    class ReservationEvent(AgentEvent):
        event_type: str = "app.reservation"
        booking_id: str

    bus = EventBus()
    handler = _RecordingHandler()
    bus.subscribe(handler)

    event = ReservationEvent(booking_id="R-123")
    asyncio.run(bus.emit(event))

    assert len(handler.received) == 1
    received = handler.received[0]
    assert isinstance(received, ReservationEvent)
    assert received.event_type == "app.reservation"
    assert received.booking_id == "R-123"  # type: ignore[attr-defined]


@pytest.mark.unit
def test_event_bus_unsubscribe() -> None:
    """unsubscribe() should stop the handler from receiving future events."""
    bus = EventBus()
    handler = _RecordingHandler()
    bus.subscribe(handler)
    bus.unsubscribe(handler)

    asyncio.run(bus.emit(AgentEvent(event_type="after.unsub")))
    assert len(handler.received) == 0


@pytest.mark.unit
def test_step_start_event_fields() -> None:
    """StepStartEvent should carry vertex and step fields."""
    event = StepStartEvent(vertex="Research", step=2)
    assert event.event_type == "agentflow.step_start"
    assert event.vertex == "Research"
    assert event.step == 2


@pytest.mark.unit
def test_run_complete_event_result() -> None:
    """RunCompleteEvent should carry an optional result string."""
    event = RunCompleteEvent(result="All done.")
    assert event.event_type == "agentflow.run_complete"
    assert event.result == "All done."

    event_no_result = RunCompleteEvent()
    assert event_no_result.result is None


@pytest.mark.unit
def test_event_handler_protocol_satisfied() -> None:
    """_RecordingHandler should satisfy the EventHandler Protocol."""
    handler = _RecordingHandler()
    assert isinstance(handler, EventHandler)


@pytest.mark.unit
def test_log_event_fields() -> None:
    """LogEvent should carry level, message, and logger_name."""
    event = LogEvent(level="INFO", message="All systems go", logger_name="app.core")
    assert event.event_type == "agentflow.log"
    assert event.level == "INFO"
    assert event.message == "All systems go"
    assert event.logger_name == "app.core"
