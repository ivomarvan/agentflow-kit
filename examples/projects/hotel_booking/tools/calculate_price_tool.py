"""Tool: calculate_price — total stay cost for a room and date range."""

from __future__ import annotations

from agentflow.tools.Tool import ToolBase, param_desc
from ..booking_store import BookingStore
from ._helpers import format_date, parse_date


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
        check_in_d = parse_date(check_in)
        if isinstance(check_in_d, str):
            return check_in_d
        check_out_d = parse_date(check_out)
        if isinstance(check_out_d, str):
            return check_out_d
        try:
            room = self._store.get_room(room_id)
            total = self._store.calculate_price(room_id, check_in_d, check_out_d)
        except ValueError as exc:
            return str(exc)
        nights = (check_out_d - check_in_d).days
        return (
            f"{room.name} from {format_date(check_in_d)} to {format_date(check_out_d)}: "
            f"{nights} nights × €{room.price_per_night:.0f} = €{total:.0f}."
        )
