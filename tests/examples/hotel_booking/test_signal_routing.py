"""Signal routing tests for Hotel Booking pure-Python vertices and LLM stubs.

Tests cover AvailabilityVertex (StateVertex, no LLM) and OtherHandlerVertex
(LlmStateVertex) using FakeLlmConnector for deterministic LLM responses.
"""

from __future__ import annotations

import pytest

from agentflow.statemachine.testing.fakes import FakeLlmConnector, make_fake_context

from examples.projects.hotel_booking.booking_store import BookingStore
from examples.projects.hotel_booking.live_state import build_initial_hotel_state
from examples.projects.hotel_booking.state import (
    HotelBookingSignal,
    HotelBookingState,
    Order,
)
from examples.projects.hotel_booking.vertices.availability_vertex import AvailabilityVertex
from examples.projects.hotel_booking.vertices.other_handler_vertex import OtherHandlerVertex


@pytest.fixture
def store() -> BookingStore:
    """Fresh seeded store for each test."""
    return BookingStore(build_initial_hotel_state())


# ---------------------------------------------------------------------------
# AvailabilityVertex — no LLM, tests are fully deterministic
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_availability_free_room_emits_available(store: BookingStore) -> None:
    """White room on a conflict-free date should emit available + set total_price."""
    state = HotelBookingState(
        order=Order(
            action="NEW_BOOKING",
            selected_room_id="white",
            guest_name="Brown",
            check_in="2026-07-20",
            check_out="2026-07-22",
            capacity=1,
        )
    )
    ctx = make_fake_context()
    signal, patch = await AvailabilityVertex(store=store).run(state, ctx)

    assert signal == HotelBookingSignal.available
    assert patch.order is not None and patch.order is not ...  # type: ignore[truthy-bool]
    assert patch.order.total_price > 0  # price should be computed


@pytest.mark.unit
@pytest.mark.asyncio
async def test_availability_occupied_room_emits_unavailable(store: BookingStore) -> None:
    """Blue room conflicts with the Dvorakova seed reservation (Jul 8–11)."""
    state = HotelBookingState(
        order=Order(
            action="NEW_BOOKING",
            selected_room_id="blue",
            guest_name="Brown",
            check_in="2026-07-08",
            check_out="2026-07-10",
            capacity=2,
        )
    )
    ctx = make_fake_context()
    signal, patch = await AvailabilityVertex(store=store).run(state, ctx)

    assert signal == HotelBookingSignal.unavailable
    assert isinstance(patch.final_response, str) and len(patch.final_response) > 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_availability_invalid_dates_emits_unavailable(store: BookingStore) -> None:
    """Malformed dates should return unavailable with an error message."""
    state = HotelBookingState(
        order=Order(
            action="NEW_BOOKING",
            selected_room_id="red",
            guest_name="Brown",
            check_in="not-a-date",
            check_out="2026-07-22",
            capacity=1,
        )
    )
    ctx = make_fake_context()
    signal, patch = await AvailabilityVertex(store=store).run(state, ctx)

    assert signal == HotelBookingSignal.unavailable


# ---------------------------------------------------------------------------
# OtherHandlerVertex — LLM vertex; uses FakeLlmConnector
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_other_handler_emits_done() -> None:
    """Off-topic message → OtherHandlerVertex always emits done."""
    fake = FakeLlmConnector()
    fake.queue_responses(['{"user_question": "Mohu vam pomoci s rezervaci."}'])
    ctx = make_fake_context(connector=fake)
    state = HotelBookingState(
        messages=({"role": "user", "content": "Jaké je dnes počasí?"},)
    )
    signal, patch = await OtherHandlerVertex().run(state, ctx)

    assert signal == HotelBookingSignal.done
    assert patch.final_response == "Mohu vam pomoci s rezervaci."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_other_handler_llm_parse_error_still_emits_done() -> None:
    """Garbled LLM output should not crash — vertex returns done with error patch."""
    fake = FakeLlmConnector()
    fake.queue_responses(["this is not valid json at all"])
    ctx = make_fake_context(connector=fake)
    state = HotelBookingState(
        messages=({"role": "user", "content": "Řekni mi vtip."},)
    )
    signal, patch = await OtherHandlerVertex().run(state, ctx)

    assert signal == HotelBookingSignal.done
