"""Tool: get_room_details — name, capacity, and nightly rate for one room."""

from __future__ import annotations

from agentflow.tools.Tool import ToolBase, param_desc
from ..booking_store import BookingStore


class GetRoomDetailsTool(ToolBase):
    """Return name, capacity, and price per night for a specific room."""

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
