"""Unit tests for hotel booking data layer."""

from __future__ import annotations

from datetime import date

import pytest

from examples.projects.hotel_booking.booking_store import BookingStore
from examples.projects.hotel_booking.live_state import build_initial_hotel_state


@pytest.fixture
def store() -> BookingStore:
    """Fresh seeded store for each test."""
    return BookingStore(build_initial_hotel_state())


@pytest.mark.unit
def test_check_availability_returns_free_rooms(store: BookingStore) -> None:
    """Jul 8–11 with capacity 2 — only Green Room is free."""
    available = store.check_availability(date(2026, 7, 8), date(2026, 7, 11), capacity=2)
    assert [room.room_id for room in available] == ["green"]


@pytest.mark.unit
def test_check_availability_all_free(store: BookingStore) -> None:
    """Jul 20–25 — all four rooms are available."""
    available = store.check_availability(date(2026, 7, 20), date(2026, 7, 25), capacity=1)
    assert len(available) == 4


@pytest.mark.unit
def test_create_reservation_success(store: BookingStore) -> None:
    """Booking White Room Jul 20–22 adds reservation and updates last_action."""
    reservation = store.create_reservation(
        "white", "Smith", date(2026, 7, 20), date(2026, 7, 22)
    )
    white = store.get_room("white")
    assert reservation in white.reservations
    assert store.hotel_state.last_action != ""
    assert "Smith" in store.hotel_state.last_action


@pytest.mark.unit
def test_create_reservation_conflict_raises(store: BookingStore) -> None:
    """Blue Room Jul 8–10 overlaps Dvorakova — ValueError."""
    with pytest.raises(ValueError, match="not available"):
        store.create_reservation("blue", "Brown", date(2026, 7, 8), date(2026, 7, 10))


@pytest.mark.unit
def test_create_reservation_invalid_dates_raises(store: BookingStore) -> None:
    """check_out <= check_in raises ValueError."""
    with pytest.raises(ValueError, match="check_out"):
        store.create_reservation("white", "Brown", date(2026, 7, 20), date(2026, 7, 20))


@pytest.mark.unit
def test_cancel_reservation_success(store: BookingStore) -> None:
    """Cancel by ID removes reservation from room."""
    reservation = store.create_reservation(
        "white", "Smith", date(2026, 7, 20), date(2026, 7, 22)
    )
    cancelled = store.cancel_reservation(reservation.reservation_id)
    assert cancelled.reservation_id == reservation.reservation_id
    assert reservation not in store.get_room("white").reservations


@pytest.mark.unit
def test_cancel_reservation_not_found_raises(store: BookingStore) -> None:
    """Unknown ID raises ValueError."""
    with pytest.raises(ValueError, match="not found"):
        store.cancel_reservation("00000000-0000-0000-0000-000000000000")


@pytest.mark.unit
def test_find_reservation_by_name(store: BookingStore) -> None:
    """Partial guest name match returns Novak family."""
    matches = store.find_reservation(guest_name="Novak")
    assert len(matches) == 1
    assert matches[0].guest_name == "Novak family"


@pytest.mark.unit
def test_find_alternatives_date_flex(store: BookingStore) -> None:
    """Blue Jul 8–11 conflict yields shifted Blue dates or Green same dates."""
    alternatives = store.find_alternatives("blue", date(2026, 7, 8), date(2026, 7, 11))
    room_ids = {alt["room_id"] for alt in alternatives}
    assert "green" in room_ids or "blue" in room_ids
    assert len(alternatives) >= 1


@pytest.mark.unit
def test_seed_data_count() -> None:
    """Initial state contains exactly five reservations."""
    hotel = build_initial_hotel_state()
    total = sum(len(room.reservations) for room in hotel.rooms)
    assert total == 5


@pytest.mark.unit
def test_calculate_price(store: BookingStore) -> None:
    """Red Room three nights at €120/night totals €360."""
    price = store.calculate_price("red", date(2026, 7, 20), date(2026, 7, 23))
    assert price == 360.0
