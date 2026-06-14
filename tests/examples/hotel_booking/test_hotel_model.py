"""Unit tests for HotelBookingModel LiveModel."""

from __future__ import annotations

from datetime import date

import pytest

from examples.projects.hotel_booking.hotel_booking_model import HotelBookingModel, install_hotel_model


@pytest.fixture
def model() -> HotelBookingModel:
    """Fresh wired HotelBookingModel for each test."""
    return install_hotel_model(HotelBookingModel())


@pytest.mark.unit
def test_initial_state_has_four_rooms(model: HotelBookingModel) -> None:
    assert len(model.state.rooms) == 4


@pytest.mark.unit
def test_initial_state_has_seed_reservations(model: HotelBookingModel) -> None:
    red = next(room for room in model.state.rooms if room.room_id == "red")
    assert len(red.reservations) >= 1


@pytest.mark.unit
def test_check_availability_returns_rooms(model: HotelBookingModel) -> None:
    result = model.check_availability("2026-07-20", "2026-07-22", 1)
    assert "Room" in result or "room" in result.lower()


@pytest.mark.unit
def test_check_availability_bad_date(model: HotelBookingModel) -> None:
    result = model.check_availability("not-a-date", "2026-07-22", 1)
    assert "Invalid date" in result


@pytest.mark.unit
def test_get_room_details_red(model: HotelBookingModel) -> None:
    result = model.get_room_details("red")
    assert "3 beds" in result


@pytest.mark.unit
def test_get_room_details_unknown(model: HotelBookingModel) -> None:
    result = model.get_room_details("purple")
    assert "Unknown room" in result


@pytest.mark.unit
def test_create_reservation_success(model: HotelBookingModel) -> None:
    result = model.create_reservation(
        "white", "Test Guest", "2026-07-20", "2026-07-21"
    )
    assert "Reservation confirmed" in result
    assert "ID:" in result


@pytest.mark.unit
def test_create_reservation_updates_state(model: HotelBookingModel) -> None:
    model.create_reservation("white", "Test Guest", "2026-07-20", "2026-07-21")
    white = next(room for room in model.state.rooms if room.room_id == "white")
    assert any(res.guest_name == "Test Guest" for res in white.reservations)


@pytest.mark.unit
def test_create_reservation_conflict(model: HotelBookingModel) -> None:
    model.create_reservation("blue", "Guest A", "2026-07-20", "2026-07-22")
    before_count = sum(len(room.reservations) for room in model.state.rooms)
    result = model.create_reservation("blue", "Guest B", "2026-07-21", "2026-07-23")
    after_count = sum(len(room.reservations) for room in model.state.rooms)
    assert "not available" in result.lower() or "conflict" in result.lower() or after_count == before_count


@pytest.mark.unit
def test_cancel_reservation_success(model: HotelBookingModel) -> None:
    created = model.create_reservation(
        "white", "Cancel Me", "2026-08-01", "2026-08-02"
    )
    res_id = created.split("ID:")[-1].strip().rstrip(".")
    result = model.cancel_reservation(res_id)
    assert "cancelled" in result.lower()
    white = next(room for room in model.state.rooms if room.room_id == "white")
    assert not any(res.reservation_id == res_id for res in white.reservations)


@pytest.mark.unit
def test_cancel_reservation_unknown(model: HotelBookingModel) -> None:
    result = model.cancel_reservation("00000000-0000-0000-0000-000000000000")
    assert "not found" in result.lower()


@pytest.mark.unit
def test_find_reservation_by_name(model: HotelBookingModel) -> None:
    result = model.find_reservation(guest_name="Novak")
    assert "Novak" in result


@pytest.mark.unit
def test_find_reservation_empty_args(model: HotelBookingModel) -> None:
    result = model.find_reservation()
    assert "Provide" in result


@pytest.mark.unit
def test_tools_returns_5_tools(model: HotelBookingModel) -> None:
    assert len(model.tools()) == 5


@pytest.mark.unit
def test_tool_registry_names(model: HotelBookingModel) -> None:
    names = set(model.tool_registry().names())
    assert names == {
        "check_availability",
        "get_room_details",
        "create_reservation",
        "cancel_reservation",
        "find_reservation",
    }
