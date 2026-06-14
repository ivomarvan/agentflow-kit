"""Tool: find_reservation — look up bookings by guest name, date, or UUID."""

from __future__ import annotations

from datetime import date

from agentflow.tools.Tool import ToolBase, param_desc
from ..booking_store import BookingStore
from ._helpers import parse_date


class FindReservationTool(ToolBase):
    """Look up reservations by guest name, check-in date, or reservation ID."""

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
            parsed = parse_date(check_in)
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
