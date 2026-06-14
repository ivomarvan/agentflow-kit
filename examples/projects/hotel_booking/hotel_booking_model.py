"""HotelBookingModel — LiveModel for the hotel booking example.

Run standalone (no LLM) to test the visual state panel:
    uv run python examples/projects/hotel_booking/hotel_booking_model.py

Use in AgentApp (hotel_booking_app.py):
    from .hotel_booking_model import HotelBookingModel, install_hotel_model
    model = install_hotel_model()
    app = AgentApp(live_model=model, ...)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date
from typing import Annotated

from pydantic import Field

from agentflow.live_model import LiveModel, action
from .booking_store import BookingStore, set_booking_store
from .live_state import HotelBookState, build_initial_hotel_state


def _parse_date(value: str) -> date | str:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return f"Invalid date '{value}'. Use YYYY-MM-DD format."


def _format_date(d: date) -> str:
    return d.strftime("%b %d")


class HotelBookingModel(LiveModel):
    """Self-describing hotel booking model with @action API.

    Run standalone demo:
        python examples/projects/hotel_booking/hotel_booking_model.py
    """

    def __init__(self) -> None:
        self._store = BookingStore(build_initial_hotel_state())

    @property
    def state(self) -> HotelBookState:
        """Current live state snapshot — rendered by the GUI state panel."""
        return self._store.hotel_state

    @action
    def check_availability(
        self,
        check_in: Annotated[
            str,
            Field(
                description="Check-in date (YYYY-MM-DD).",
                json_schema_extra={"x-widget": "date"},
            ),
        ],
        check_out: Annotated[
            str,
            Field(
                description="Check-out date (YYYY-MM-DD).",
                json_schema_extra={"x-widget": "date"},
            ),
        ],
        capacity: Annotated[
            int,
            Field(
                description="Number of guests (1–3).",
                ge=1,
                le=3,
                json_schema_extra={"x-widget": "number"},
            ),
        ],
    ) -> str:
        """Return available rooms for the given dates and guest count."""
        check_in_d = _parse_date(check_in)
        if isinstance(check_in_d, str):
            return check_in_d
        check_out_d = _parse_date(check_out)
        if isinstance(check_out_d, str):
            return check_out_d
        rooms = self._store.check_availability(check_in_d, check_out_d, capacity)
        if not rooms:
            return "No rooms available"
        lines = [
            f"{room.name}: {room.capacity} beds, €{room.price_per_night:.0f} per night."
            for room in rooms
        ]
        return "Available rooms: " + "; ".join(lines)

    @action
    def get_room_details(
        self,
        room_id: Annotated[
            str,
            Field(
                description="Room identifier: 'red', 'blue', 'green', or 'white'.",
                json_schema_extra={
                    "x-widget": "select",
                    "enum": ["red", "blue", "green", "white"],
                },
            ),
        ],
    ) -> str:
        """Return name, capacity, and price for the given room."""
        try:
            room = self._store.get_room(room_id)
        except ValueError as exc:
            return str(exc)
        return f"{room.name}: {room.capacity} beds, €{room.price_per_night:.0f}/night."

    @action
    def create_reservation(
        self,
        room_id: Annotated[
            str,
            Field(
                description="Room: 'red', 'blue', 'green', or 'white'.",
                json_schema_extra={
                    "x-widget": "select",
                    "enum": ["red", "blue", "green", "white"],
                },
            ),
        ],
        guest_name: Annotated[str, Field(description="Full name of the guest.")],
        check_in: Annotated[
            str,
            Field(
                description="Check-in date (YYYY-MM-DD).",
                json_schema_extra={"x-widget": "date"},
            ),
        ],
        check_out: Annotated[
            str,
            Field(
                description="Check-out date (YYYY-MM-DD).",
                json_schema_extra={"x-widget": "date"},
            ),
        ],
    ) -> str:
        """Book a room for a guest. Validates availability before booking."""
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

    @action
    def cancel_reservation(
        self,
        reservation_id: Annotated[str, Field(description="UUID of the reservation to cancel.")],
    ) -> str:
        """Cancel an existing reservation by its ID."""
        try:
            cancelled = self._store.cancel_reservation(reservation_id)
        except ValueError as exc:
            return str(exc)
        return f"Reservation {reservation_id} for {cancelled.guest_name} cancelled."

    @action
    def find_reservation(
        self,
        guest_name: Annotated[
            str,
            Field(description="Guest name (partial match). Leave empty to skip."),
        ] = "",
        reservation_id: Annotated[
            str,
            Field(description="Exact reservation UUID. Leave empty to skip."),
        ] = "",
    ) -> str:
        """Find reservations by guest name or ID. At least one field required."""
        if not guest_name and not reservation_id:
            return "Provide guest_name and/or reservation_id."
        matches = self._store.find_reservation(
            guest_name=guest_name,
            reservation_id=reservation_id,
        )
        if not matches:
            return "No matching reservations found."
        lines = [
            f"{res.guest_name}: {res.check_in.isoformat()} – {res.check_out.isoformat()} "
            f"(ID {res.reservation_id})"
            for res in matches
        ]
        return "Reservations: " + "; ".join(lines)


def install_hotel_model(model: HotelBookingModel | None = None) -> HotelBookingModel:
    """Create a HotelBookingModel and wire the module-level booking store singleton.

    Args:
        model: Optional existing instance; creates a new one when None.

    Returns:
        The wired HotelBookingModel instance.
    """
    instance = model or HotelBookingModel()
    set_booking_store(instance._store)  # noqa: SLF001
    return instance


if __name__ == "__main__":
    # Standalone demo — opens the LiveModel GUI without any LLM vertices.
    HotelBookingModel.demo()
