"""Hotel booking tool — books rooms and emits ReservationEvent to EventBus."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from agentflow.events import AgentEvent
from agentflow.tools.Tool import ToolBase, param_desc
from examples.hotel_booking.reservation_store import Reservation, ReservationStore

if TYPE_CHECKING:
    from agentflow.events import EventBus


class ReservationEvent(AgentEvent):
    """Domain event emitted when a hotel room reservation is created.

    The GUI renders this as a table row when hotel_reservation.vue renderer
    is registered under the key ``hotel.reservation``.

    Attributes:
        event_type: Fixed discriminator used by the GUI renderer registry.
        guest_name: Full name of the guest.
        room: Room number or type.
        check_in: Check-in date string.
        check_out: Check-out date string.
    """

    event_type: Literal["hotel.reservation"] = "hotel.reservation"
    guest_name: str
    room: str
    check_in: str
    check_out: str


class HotelBookingTool(ToolBase):
    """Books hotel rooms, persists to ReservationStore, and emits ReservationEvent.

    Uses an injected EventBus so the same tool instance works both in tests
    (no GUI) and in the live GUI workflow (events streamed to the frontend).
    """

    def __init__(self, store: ReservationStore, event_bus: "EventBus") -> None:
        """Initialise with a shared store and event bus.

        Args:
            store: In-memory reservation store shared with the application.
            event_bus: EventBus used to stream domain events to the GUI.
        """
        super().__init__(name="book_hotel_room")
        self._store = store
        self._event_bus = event_bus

    @param_desc(
        guest_name="Full name of the guest",
        room="Room number or type (e.g. '101' or 'deluxe double')",
        check_in="Check-in date (YYYY-MM-DD or natural language)",
        check_out="Check-out date (YYYY-MM-DD or natural language)",
    )
    def execute(  # type: ignore[override]
        self,
        guest_name: str,
        room: str,
        check_in: str,
        check_out: str,
    ) -> str:
        """Book a room synchronously — stores reservation without event emission.

        Used when the tool is dispatched by the LLM via ToolRegistry.execute().
        For GUI-aware async usage, call run() directly from a StateVertex.

        Args:
            guest_name: Full name of the guest.
            room: Room number or type.
            check_in: Check-in date string.
            check_out: Check-out date string.

        Returns:
            Confirmation string describing the booking.
        """
        r = self._do_book(guest_name, room, check_in, check_out)
        return f"Room '{r.room}' booked for {r.guest_name} ({r.check_in} → {r.check_out})."

    async def run(  # type: ignore[override]
        self,
        guest_name: str,
        room: str,
        check_in: str,
        check_out: str,
    ) -> str:
        """Book a room asynchronously — persists to store and emits ReservationEvent.

        Called directly from StateVertex.run() when EventBus integration is needed.

        Args:
            guest_name: Full name of the guest.
            room: Room number or type.
            check_in: Check-in date string.
            check_out: Check-out date string.

        Returns:
            Confirmation string describing the booking.
        """
        r = self._do_book(guest_name, room, check_in, check_out)
        await self._event_bus.emit(
            ReservationEvent(
                guest_name=r.guest_name,
                room=r.room,
                check_in=r.check_in,
                check_out=r.check_out,
            )
        )
        return f"Room '{r.room}' booked for {r.guest_name} ({r.check_in} → {r.check_out})."

    def _do_book(
        self, guest_name: str, room: str, check_in: str, check_out: str
    ) -> Reservation:
        """Create and store a Reservation.

        Args:
            guest_name: Full name of the guest.
            room: Room number or type.
            check_in: Check-in date string.
            check_out: Check-out date string.

        Returns:
            The newly created and stored Reservation instance.
        """
        r = Reservation(
            guest_name=guest_name,
            room=room,
            check_in=check_in,
            check_out=check_out,
        )
        self._store.add(r)
        return r

    def _get_own_attributes(self) -> dict[str, Any]:
        d = super()._get_own_attributes()
        d["store_size"] = len(self._store)
        return d
