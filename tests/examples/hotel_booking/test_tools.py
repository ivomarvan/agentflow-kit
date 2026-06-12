"""Unit tests for hotel booking agentflow tools."""

from __future__ import annotations

from datetime import date

import pytest

from examples.projects.hotel_booking.booking_store import BookingStore
from examples.projects.hotel_booking.live_state import build_initial_hotel_state
from examples.projects.hotel_booking.tools import (
    CalculatePriceTool,
    CancelReservationTool,
    CheckAvailabilityTool,
    CreateReservationTool,
    FindAlternativesTool,
    FindReservationTool,
    GetRoomDetailsTool,
)


@pytest.fixture
def store() -> BookingStore:
    return BookingStore(build_initial_hotel_state())


@pytest.fixture
def tools(store: BookingStore) -> dict[str, object]:
    return {
        "availability": CheckAvailabilityTool(store),
        "details": GetRoomDetailsTool(store),
        "price": CalculatePriceTool(store),
        "create": CreateReservationTool(store),
        "cancel": CancelReservationTool(store),
        "find": FindReservationTool(store),
        "alternatives": FindAlternativesTool(store),
    }


@pytest.mark.unit
def test_check_availability_returns_results(tools: dict[str, object]) -> None:
    result = tools["availability"].execute("2026-07-20", "2026-07-22", "2")  # type: ignore[union-attr]
    assert "Blue" in result or "Green" in result


@pytest.mark.unit
def test_check_availability_no_rooms(tools: dict[str, object]) -> None:
    result = tools["availability"].execute("2026-07-20", "2026-07-22", "10")  # type: ignore[union-attr]
    assert result == "No rooms available"


@pytest.mark.unit
def test_get_room_details_valid(tools: dict[str, object]) -> None:
    result = tools["details"].execute("red")  # type: ignore[union-attr]
    assert "3 beds" in result
    assert "120" in result


@pytest.mark.unit
def test_get_room_details_invalid(tools: dict[str, object]) -> None:
    result = tools["details"].execute("purple")  # type: ignore[union-attr]
    assert "Unknown" in result


@pytest.mark.unit
def test_calculate_price(tools: dict[str, object]) -> None:
    result = tools["price"].execute("red", "2026-07-20", "2026-07-23")  # type: ignore[union-attr]
    assert "360" in result


@pytest.mark.unit
def test_create_reservation_success(tools: dict[str, object]) -> None:
    result = tools["create"].execute("white", "Smith", "2026-07-20", "2026-07-22")  # type: ignore[union-attr]
    assert "Reservation confirmed" in result
    assert "ID:" in result


@pytest.mark.unit
def test_create_reservation_conflict(tools: dict[str, object]) -> None:
    result = tools["create"].execute("blue", "Brown", "2026-07-08", "2026-07-10")  # type: ignore[union-attr]
    assert "not available" in result.lower() or "available" in result.lower()


@pytest.mark.unit
def test_create_reservation_bad_date(tools: dict[str, object]) -> None:
    result = tools["create"].execute("white", "Smith", "2026-07-20", "not-a-date")  # type: ignore[union-attr]
    assert "Invalid date" in result


@pytest.mark.unit
def test_cancel_reservation_success(tools: dict[str, object], store: BookingStore) -> None:
    created = store.create_reservation("white", "Smith", date(2026, 7, 20), date(2026, 7, 22))
    result = tools["cancel"].execute(created.reservation_id)  # type: ignore[union-attr]
    assert "cancelled" in result.lower()


@pytest.mark.unit
def test_cancel_reservation_not_found(tools: dict[str, object]) -> None:
    result = tools["cancel"].execute("00000000-0000-0000-0000-000000000000")  # type: ignore[union-attr]
    assert "not found" in result.lower()


@pytest.mark.unit
def test_find_reservation_by_name(tools: dict[str, object]) -> None:
    result = tools["find"].execute(guest_name="Novak")  # type: ignore[union-attr]
    assert "Novak" in result


@pytest.mark.unit
def test_find_alternatives_returns_options(tools: dict[str, object]) -> None:
    result = tools["alternatives"].execute("blue", "2026-07-08", "2026-07-11")  # type: ignore[union-attr]
    assert "Alternatives:" in result
