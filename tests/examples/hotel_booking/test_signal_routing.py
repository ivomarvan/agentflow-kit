"""Signal routing tests for pure-Python and mocked-LLM hotel vertices."""

from __future__ import annotations

import pytest

from agentflow.llm.connectors.FakeLlmConnector import FakeLlmConnector
from agentflow.statemachine.context import Context
from agentflow.statemachine.testing.fakes import make_fake_context

from examples.projects.hotel_booking.state import HotelSignal, HotelState
from examples.projects.hotel_booking.vertices import DataDispatcherVertex, OtherHandlerVertex


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatcher_all_missing_routes_need_name() -> None:
    state = HotelState()
    signal, _patch = await DataDispatcherVertex().run(state, Context())
    assert signal == HotelSignal.need_name


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatcher_name_present_routes_need_dates() -> None:
    state = HotelState(guest_name="Brown")
    signal, _patch = await DataDispatcherVertex().run(state, Context())
    assert signal == HotelSignal.need_dates


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatcher_dates_present_routes_need_capacity() -> None:
    state = HotelState(
        guest_name="Brown",
        check_in="2026-07-20",
        check_out="2026-07-22",
    )
    signal, _patch = await DataDispatcherVertex().run(state, Context())
    assert signal == HotelSignal.need_capacity


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatcher_all_present_routes_data_complete() -> None:
    state = HotelState(
        guest_name="Brown",
        check_in="2026-07-20",
        check_out="2026-07-22",
        capacity=2,
    )
    signal, _patch = await DataDispatcherVertex().run(state, Context())
    assert signal == HotelSignal.data_complete


@pytest.mark.unit
@pytest.mark.asyncio
async def test_other_handler_first_reminder_increments_count() -> None:
    fake = FakeLlmConnector()
    fake.queue_responses(['{"voice": "I can help with bookings."}'])
    ctx = make_fake_context(connector=fake)
    state = HotelState(
        messages=({"role": "user", "content": "What's the weather?"},),
        other_reminder_count=0,
    )
    signal, patch = await OtherHandlerVertex().run(state, ctx)
    assert signal == HotelSignal.reminder_sent
    assert patch.other_reminder_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_other_handler_second_reminder_routes_done() -> None:
    fake = FakeLlmConnector()
    fake.queue_responses(['{"voice": "Goodbye and thank you."}'])
    ctx = make_fake_context(connector=fake)
    state = HotelState(
        messages=({"role": "user", "content": "Tell me a joke."},),
        other_reminder_count=1,
    )
    signal, patch = await OtherHandlerVertex().run(state, ctx)
    assert signal == HotelSignal.done
    assert patch.other_reminder_count == 2
