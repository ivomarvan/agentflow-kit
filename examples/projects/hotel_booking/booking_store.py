"""In-memory booking store with conflict detection for the hotel example."""

from __future__ import annotations

from datetime import date, timedelta

from .live_state import (
    _HOTEL,
    HotelBookState,
    Reservation,
    RoomState,
)


def _parse_iso(value: str | date) -> date:
    """Accept date or ISO string for store helpers used by vertices."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _nights(check_in: date, check_out: date) -> int:
    return (check_out - check_in).days


def _overlaps(
    new_in: date,
    new_out: date,
    existing_in: date,
    existing_out: date,
) -> bool:
    """True when the new stay overlaps an existing reservation."""
    return new_in < existing_out and new_out > existing_in


class BookingStore:
    """CRUD service operating on a shared HotelBookState instance."""

    def __init__(self, hotel_state: HotelBookState) -> None:
        self._hotel_state = hotel_state

    @property
    def hotel_state(self) -> HotelBookState:
        """Underlying live-state object observed by the GUI."""
        return self._hotel_state

    def get_room(self, room_id: str) -> RoomState:
        """Return a room by ID.

        Raises:
            ValueError: When room_id is unknown.
        """
        for room in self._hotel_state.rooms:
            if room.room_id == room_id:
                return room
        raise ValueError(f"Unknown room '{room_id}'.")

    def calculate_price(self, room_id: str, check_in: date, check_out: date) -> float:
        """Compute total stay cost as nights × price_per_night.

        Raises:
            ValueError: When room_id is unknown or dates are invalid.
        """
        room = self.get_room(room_id)
        nights = _nights(check_in, check_out)
        if nights <= 0:
            raise ValueError("check_out must be after check_in.")
        return nights * room.price_per_night

    def check_availability(
        self,
        check_in: date,
        check_out: date,
        capacity: int,
    ) -> list[RoomState]:
        """Return rooms with sufficient capacity and no overlapping reservations."""
        available: list[RoomState] = []
        for room in self._hotel_state.rooms:
            if room.capacity < capacity:
                continue
            if any(
                _overlaps(check_in, check_out, res.check_in, res.check_out)
                for res in room.reservations
            ):
                continue
            available.append(room)
        return available

    def _room_is_free(
        self,
        room: RoomState,
        check_in: date,
        check_out: date,
    ) -> bool:
        return not any(
            _overlaps(check_in, check_out, res.check_in, res.check_out)
            for res in room.reservations
        )

    def create_reservation(
        self,
        room_id: str,
        guest_name: str,
        check_in: date | str,
        check_out: date | str,
    ) -> Reservation:
        """Add a reservation after validating dates and availability.

        Raises:
            ValueError: On invalid dates, unknown room, or scheduling conflict.
        """
        check_in_d = _parse_iso(check_in)
        check_out_d = _parse_iso(check_out)
        if check_out_d <= check_in_d:
            raise ValueError("check_out must be after check_in.")
        nights = _nights(check_in_d, check_out_d)
        if nights < 1 or nights > 30:
            raise ValueError("Stay length must be between 1 and 30 nights.")

        room = self.get_room(room_id)
        if not self._room_is_free(room, check_in_d, check_out_d):
            raise ValueError(f"Room '{room_id}' is not available for the requested dates.")

        total_price = self.calculate_price(room_id, check_in_d, check_out_d)
        reservation = Reservation(
            guest_name=guest_name,
            check_in=check_in_d,
            check_out=check_out_d,
            total_price=total_price,
        )
        room.reservations.append(reservation)
        self._hotel_state.last_action = (
            f"Booked {room.name} for {guest_name} "
            f"({check_in_d.isoformat()} – {check_out_d.isoformat()}), €{total_price:.0f}"
        )
        return reservation

    def cancel_reservation(self, reservation_id: str) -> Reservation:
        """Remove a reservation by ID.

        Raises:
            ValueError: When no reservation matches the ID.
        """
        for room in self._hotel_state.rooms:
            for index, reservation in enumerate(room.reservations):
                if reservation.reservation_id == reservation_id:
                    removed = room.reservations.pop(index)
                    self._hotel_state.last_action = (
                        f"Cancelled {removed.guest_name} in {room.name} "
                        f"({removed.check_in.isoformat()} – {removed.check_out.isoformat()})"
                    )
                    return removed
        raise ValueError(f"Reservation '{reservation_id}' not found.")

    def find_reservation(
        self,
        *,
        guest_name: str = "",
        check_in: date | None = None,
        reservation_id: str = "",
    ) -> list[Reservation]:
        """Return reservations matching any supplied criterion."""
        matches: list[Reservation] = []
        for room in self._hotel_state.rooms:
            for reservation in room.reservations:
                if reservation_id and reservation.reservation_id != reservation_id:
                    continue
                if guest_name and guest_name.lower() not in reservation.guest_name.lower():
                    continue
                if check_in is not None and reservation.check_in != check_in:
                    continue
                matches.append(reservation)
        return matches

    def find_alternatives(
        self,
        room_id: str,
        check_in: date,
        check_out: date,
        date_flex_days: int = 3,
    ) -> list[dict[str, str | date]]:
        """Suggest alternate dates for the requested room or other rooms same dates."""
        alternatives: list[dict[str, str | date]] = []
        nights = _nights(check_in, check_out)
        if nights <= 0:
            return alternatives

        requested = self.get_room(room_id)
        seen: set[tuple[str, date, date]] = set()

        def _add(room: RoomState, alt_in: date, alt_out: date, reason: str) -> None:
            key = (room.room_id, alt_in, alt_out)
            if key in seen:
                return
            if not self._room_is_free(room, alt_in, alt_out):
                return
            seen.add(key)
            alternatives.append(
                {
                    "room_id": room.room_id,
                    "check_in": alt_in,
                    "check_out": alt_out,
                    "reason": reason,
                }
            )

        for offset in range(-date_flex_days, date_flex_days + 1):
            if offset == 0:
                continue
            alt_in = check_in + timedelta(days=offset)
            alt_out = alt_in + timedelta(days=nights)
            _add(
                requested,
                alt_in,
                alt_out,
                f"Same room shifted by {offset:+d} days",
            )

        for room in self._hotel_state.rooms:
            if room.room_id == room_id:
                continue
            if room.capacity < requested.capacity:
                continue
            _add(room, check_in, check_out, f"{room.name} available on original dates")

        return alternatives


_STORE = BookingStore(_HOTEL)


def set_booking_store(store: BookingStore) -> None:
    """Replace the module-level store singleton (used by vertices and LLM tools)."""
    global _STORE
    _STORE = store
