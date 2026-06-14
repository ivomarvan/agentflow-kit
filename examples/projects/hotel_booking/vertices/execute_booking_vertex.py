"""Vertex: ExecuteBookingVertex — create the reservation (no LLM).

Called after the guest has explicitly confirmed the booking.
Calls BookingStore.create_reservation() directly (no tool wrapper needed)
and updates order.reservation_id with the assigned UUID.

Emits done → StdEnd on success, fail → StdEnd on error.
"""

from __future__ import annotations

import logging
from datetime import date

from pydantic import PrivateAttr

from agentflow.statemachine import Signal, StateVertex
from ..booking_store import BookingStore
from ..state import (
    HotelBookingPatch,
    HotelBookingSignal,
    HotelBookingState,
    Order,
)

logger = logging.getLogger(__name__)


class ExecuteBookingVertex(StateVertex):
    """Create the confirmed reservation and update the live Guest Book.

    Inject BookingStore via constructor so the vertex operates on the same
    mutable HotelBookState that the GUI LiveModel observes.
    """

    _store: BookingStore = PrivateAttr()

    def __init__(self, store: BookingStore, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._store = store

    async def run(
        self, state: HotelBookingState, ctx: object
    ) -> tuple[Signal, HotelBookingPatch]:
        """Create the reservation and return confirmation message.

        Args:
            state: Current graph state; order must have all booking fields.
            ctx:   Shared context (unused — no LLM call).

        Returns:
            (done, patch) on success, (fail, patch) on booking error.
        """
        order = state.order
        try:
            check_in = date.fromisoformat(order.check_in)
            check_out = date.fromisoformat(order.check_out)
        except ValueError as exc:
            logger.error("ExecuteBookingVertex: invalid dates: %s", exc)
            msg = "Omlouváme se, nepodařilo se dokončit rezervaci. Zkuste to prosím znovu."
            # cs: Chyba při parsování dat — informujte hosta a požádejte o opakování.
            return HotelBookingSignal.fail, HotelBookingPatch(
                messages=({"role": "assistant", "content": msg},),
                order=Order(),
                flow="initial",
                final_response=msg,
            )

        try:
            reservation = self._store.create_reservation(
                order.selected_room_id,
                order.guest_name,
                check_in,
                check_out,
            )
        except ValueError as exc:
            logger.error("ExecuteBookingVertex: store error: %s", exc)
            msg = f"Omlouváme se, rezervaci se nepodařilo vytvořit: {exc}"
            # cs: Chyba store — pokoj již není volný nebo data jsou neplatná.
            return HotelBookingSignal.fail, HotelBookingPatch(
                messages=({"role": "assistant", "content": msg},),
                order=Order(),
                flow="initial",
                final_response=msg,
            )

        reservation_id = reservation.reservation_id

        try:
            from ..live_state import _ROOM_CATALOGUE
            room_name = next(
                (r[1] for r in _ROOM_CATALOGUE if r[0] == order.selected_room_id),
                order.selected_room_id,
            )
        except Exception:
            room_name = order.selected_room_id

        msg = (
            f"Vaše rezervace pokoje {room_name} pro {order.guest_name} "
            f"od {order.check_in} do {order.check_out} byla úspěšně vytvořena."
            # cs: Potvrzení úspěšné rezervace — pokoj, jméno, termín.
        )
        logger.info(
            "ExecuteBookingVertex: reservation created  id=%s  room=%s  guest=%s",
            reservation_id, order.selected_room_id, order.guest_name,
        )

        patch = HotelBookingPatch(
            messages=({"role": "assistant", "content": msg},),
            order=Order(),        # reset for the next request in this session
            flow="initial",
            final_response=msg,
        )
        return HotelBookingSignal.done, patch
