"""Tool: create_reservation — persist a booking after explicit guest confirmation."""

from __future__ import annotations

from agentflow.tools.Tool import ToolBase, param_desc
from ..booking_store import BookingStore
from ._helpers import format_date, parse_date


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
        check_in_d = parse_date(check_in)
        if isinstance(check_in_d, str):
            return check_in_d
        check_out_d = parse_date(check_out)
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
            f"{format_date(check_in_d)}–{format_date(check_out_d)}. "
            f"Total: €{reservation.total_price:.0f}. ID: {reservation.reservation_id}."
        )
