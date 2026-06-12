"""Agentflow tools for the hotel booking voice assistant."""

from __future__ import annotations

from datetime import date

from agentflow.tools.Tool import ToolBase, param_desc
from examples.projects.hotel_booking.booking_store import BookingStore


def _parse_date(value: str) -> date | str:
    """Parse ISO date or return a user-friendly error string."""
    try:
        return date.fromisoformat(value)
    except ValueError:
        return f"Invalid date '{value}'. Use YYYY-MM-DD format."


def _format_date(d: date) -> str:
    return d.strftime("%b %d")


class CheckAvailabilityTool(ToolBase):
    """Return available rooms for given dates and guest count."""

    name = "check_availability"
    description = (
        "Return available rooms for given check-in date, check-out date, and number of guests."
    )

    def __init__(self, store: BookingStore) -> None:
        self._store = store

    @param_desc(
        check_in="Check-in date in YYYY-MM-DD format.",
        check_out="Check-out date in YYYY-MM-DD format.",
        capacity="Number of guests as a string, e.g. '2'.",
    )
    def execute(self, check_in: str, check_out: str, capacity: str) -> str:
        """List rooms that fit capacity and have no date conflicts."""
        check_in_d = _parse_date(check_in)
        if isinstance(check_in_d, str):
            return check_in_d
        check_out_d = _parse_date(check_out)
        if isinstance(check_out_d, str):
            return check_out_d
        try:
            cap = int(capacity)
        except ValueError:
            return f"Invalid capacity '{capacity}'. Provide a whole number."

        rooms = self._store.check_availability(check_in_d, check_out_d, cap)
        if not rooms:
            return "No rooms available"
        lines = [
            f"{room.name}: {room.capacity} beds, €{room.price_per_night:.0f} per night."
            for room in rooms
        ]
        return "Available rooms: " + "; ".join(lines)


class GetRoomDetailsTool(ToolBase):
    """Return name, capacity, and nightly rate for one room."""

    name = "get_room_details"
    description = "Return name, capacity, and price per night for a specific room."

    def __init__(self, store: BookingStore) -> None:
        self._store = store

    @param_desc(room_id="Room ID: red, blue, green, or white.")
    def execute(self, room_id: str) -> str:
        """Format room metadata for voice output."""
        try:
            room = self._store.get_room(room_id)
        except ValueError as exc:
            return str(exc)
        return f"{room.name}: {room.capacity} beds, €{room.price_per_night:.0f}/night."


class CalculatePriceTool(ToolBase):
    """Compute total stay cost for a room and date range."""

    name = "calculate_price"
    description = "Calculate total price for a room and stay duration."

    def __init__(self, store: BookingStore) -> None:
        self._store = store

    @param_desc(
        room_id="Room ID: red, blue, green, or white.",
        check_in="Check-in date in YYYY-MM-DD format.",
        check_out="Check-out date in YYYY-MM-DD format.",
    )
    def execute(self, room_id: str, check_in: str, check_out: str) -> str:
        """Return a voice-friendly price breakdown."""
        check_in_d = _parse_date(check_in)
        if isinstance(check_in_d, str):
            return check_in_d
        check_out_d = _parse_date(check_out)
        if isinstance(check_out_d, str):
            return check_out_d
        try:
            room = self._store.get_room(room_id)
            total = self._store.calculate_price(room_id, check_in_d, check_out_d)
        except ValueError as exc:
            return str(exc)
        nights = (check_out_d - check_in_d).days
        return (
            f"{room.name} from {_format_date(check_in_d)} to {_format_date(check_out_d)}: "
            f"{nights} nights × €{room.price_per_night:.0f} = €{total:.0f}."
        )


class CreateReservationTool(ToolBase):
    """Create a reservation after explicit guest confirmation.

    This tool must only be called after the guest has explicitly confirmed
    the booking summary.
    """

    name = "create_reservation"
    description = (
        "Create a room reservation. ONLY call after the guest has explicitly confirmed."
    )

    def __init__(self, store: BookingStore) -> None:
        self._store = store

    @param_desc(
        room_id="Room ID: red, blue, green, or white.",
        guest_name="Full name of the guest.",
        check_in="Check-in date in YYYY-MM-DD format.",
        check_out="Check-out date in YYYY-MM-DD format.",
    )
    def execute(
        self,
        room_id: str,
        guest_name: str,
        check_in: str,
        check_out: str,
    ) -> str:
        """Persist a reservation or return an error string."""
        check_in_d = _parse_date(check_in)
        if isinstance(check_in_d, str):
            return check_in_d
        check_out_d = _parse_date(check_out)
        if isinstance(check_out_d, str):
            return check_out_d
        try:
            reservation = self._store.create_reservation(
                room_id, guest_name, check_in_d, check_out_d
            )
            room = self._store.get_room(room_id)
        except ValueError as exc:
            return str(exc)
        return (
            f"Reservation confirmed: {room.name} for {guest_name}, "
            f"{_format_date(check_in_d)}–{_format_date(check_out_d)}. "
            f"Total: €{reservation.total_price:.0f}. ID: {reservation.reservation_id}."
        )


class CancelReservationTool(ToolBase):
    """Cancel an existing reservation by ID."""

    name = "cancel_reservation"
    description = "Cancel an existing reservation by reservation ID."

    def __init__(self, store: BookingStore) -> None:
        self._store = store

    @param_desc(reservation_id="UUID of the reservation to cancel.")
    def execute(self, reservation_id: str) -> str:
        """Remove reservation or return error string."""
        try:
            cancelled = self._store.cancel_reservation(reservation_id)
        except ValueError as exc:
            return str(exc)
        return f"Reservation {reservation_id} for {cancelled.guest_name} cancelled."


class FindReservationTool(ToolBase):
    """Look up reservations by guest name, check-in date, or ID."""

    name = "find_reservation"
    description = (
        "Find reservations by guest name, check-in date, or reservation ID. "
        "At least one parameter required."
    )

    def __init__(self, store: BookingStore) -> None:
        self._store = store

    @param_desc(
        guest_name="Partial or full guest name (optional).",
        check_in="Check-in date YYYY-MM-DD (optional).",
        reservation_id="Reservation UUID (optional).",
    )
    def execute(
        self,
        guest_name: str = "",
        check_in: str = "",
        reservation_id: str = "",
    ) -> str:
        """Return formatted matches or a not-found message."""
        if not guest_name and not check_in and not reservation_id:
            return "Provide at least one of guest_name, check_in, or reservation_id."

        check_in_d: date | None = None
        if check_in:
            parsed = _parse_date(check_in)
            if isinstance(parsed, str):
                return parsed
            check_in_d = parsed

        matches = self._store.find_reservation(
            guest_name=guest_name,
            check_in=check_in_d,
            reservation_id=reservation_id,
        )
        if not matches:
            return "No reservations found."
        lines = [
            f"{res.guest_name}: {res.check_in} to {res.check_out}, ID {res.reservation_id}"
            for res in matches
        ]
        return "Found: " + "; ".join(lines)


class FindAlternativesTool(ToolBase):
    """Suggest alternate rooms or dates when the requested stay is unavailable."""

    name = "find_alternatives"
    description = "Find alternative rooms or dates when a requested room is unavailable."

    def __init__(self, store: BookingStore) -> None:
        self._store = store

    @param_desc(
        room_id="Requested room ID.",
        check_in="Check-in date in YYYY-MM-DD format.",
        check_out="Check-out date in YYYY-MM-DD format.",
    )
    def execute(self, room_id: str, check_in: str, check_out: str) -> str:
        """Format up to four voice-friendly alternatives."""
        check_in_d = _parse_date(check_in)
        if isinstance(check_in_d, str):
            return check_in_d
        check_out_d = _parse_date(check_out)
        if isinstance(check_out_d, str):
            return check_out_d
        try:
            alternatives = self._store.find_alternatives(room_id, check_in_d, check_out_d)
        except ValueError as exc:
            return str(exc)
        if not alternatives:
            return "No alternatives found for those dates."
        lines: list[str] = []
        for alt in alternatives[:4]:
            alt_room = self._store.get_room(str(alt["room_id"]))
            alt_in = alt["check_in"]
            alt_out = alt["check_out"]
            assert isinstance(alt_in, date)
            assert isinstance(alt_out, date)
            lines.append(
                f"{alt_room.name} {_format_date(alt_in)} to {_format_date(alt_out)} "
                f"({alt['reason']})"
            )
        return "Alternatives: " + "; ".join(lines)
