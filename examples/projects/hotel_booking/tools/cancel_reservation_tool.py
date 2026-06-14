"""Tool: cancel_reservation — remove an existing booking by UUID."""

from __future__ import annotations

from agentflow.tools.Tool import ToolBase, param_desc
from ..booking_store import BookingStore


class CancelReservationTool(ToolBase):
    """Cancel an existing reservation by ID."""

    name = "cancel_reservation"
    description = "Cancel an existing reservation by reservation ID."

    def __init__(self, store: BookingStore) -> None:
        self._store = store

    @param_desc(reservation_id="UUID of the reservation to cancel.")
    def execute(self, reservation_id: str) -> str:
        """Remove reservation or return an error string."""
        try:
            cancelled = self._store.cancel_reservation(reservation_id)
        except ValueError as exc:
            return str(exc)
        return f"Reservation {reservation_id} for {cancelled.guest_name} cancelled."
