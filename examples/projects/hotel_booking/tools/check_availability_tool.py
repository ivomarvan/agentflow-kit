"""Tool: check_availability — list rooms free for given dates and guest count."""

from __future__ import annotations

from agentflow.tools.Tool import ToolBase, param_desc
from ..booking_store import BookingStore
from ._helpers import parse_date


class CheckAvailabilityTool(ToolBase):
    """Return available rooms for given check-in date, check-out date, and guest count."""

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
        check_in_d = parse_date(check_in)
        if isinstance(check_in_d, str):
            return check_in_d
        check_out_d = parse_date(check_out)
        if isinstance(check_out_d, str):
            return check_out_d
        try:
            cap = int(capacity)
        except ValueError:
            return f"Invalid capacity '{capacity}'. Provide a whole number."

        rooms = self._store.check_availability(check_in_d, check_out_d, cap)
        if not rooms:
            return "No rooms available."
        lines = [
            f"{room.name}: {room.capacity} beds, €{room.price_per_night:.0f} per night."
            for room in rooms
        ]
        return "Available rooms: " + "; ".join(lines)
