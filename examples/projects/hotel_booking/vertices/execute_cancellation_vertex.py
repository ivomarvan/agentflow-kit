"""Vertex: ExecuteCancellationVertex — cancel the reservation (no LLM).

Called after all required cancellation data is collected.
Uses BookingStore.find_reservation() to locate the booking (by reservation_id,
guest_name, or check_in) and then cancel_reservation() to remove it.

Emits done → StdEnd on success, fail → StdEnd when no matching reservation is found.
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


class ExecuteCancellationVertex(StateVertex):
    """Find and cancel the reservation, then update the live Guest Book."""

    _store: BookingStore = PrivateAttr()

    def __init__(self, store: BookingStore, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._store = store

    async def run(
        self, state: HotelBookingState, ctx: object
    ) -> tuple[Signal, HotelBookingPatch]:
        """Locate and remove the reservation.

        Args:
            state: Current graph state; order must have guest_name and at
                   least one of: reservation_id, check_in.
            ctx:   Shared context (unused — no LLM call).

        Returns:
            (done, patch) on success, (fail, patch) on lookup failure.
        """
        order = state.order

        # Parse check_in date if provided (FindReservation store method needs a date).
        check_in_date: date | None = None
        if order.check_in:
            try:
                check_in_date = date.fromisoformat(order.check_in)
            except ValueError:
                pass

        # Step 1: find the reservation.
        matches = self._store.find_reservation(
            guest_name=order.guest_name,
            check_in=check_in_date,
            reservation_id=order.reservation_id,
        )

        if not matches:
            msg = (
                f"Omlouváme se, nepodařilo se najít rezervaci pro {order.guest_name}. "
                "Zkontrolujte prosím datum nebo ID rezervace."
                # cs: Rezervace nenalezena — požádejte o ověření údajů.
            )
            logger.warning(
                "ExecuteCancellationVertex: no reservation found  guest=%s  check_in=%s  id=%s",
                order.guest_name, order.check_in, order.reservation_id,
            )
            return HotelBookingSignal.fail, HotelBookingPatch(
                messages=({"role": "assistant", "content": msg},),
                order=Order(),
                flow="initial",
                final_response=msg,
            )

        if len(matches) > 1:
            # Multiple matches: cancel the first one but log a warning.
            logger.warning(
                "ExecuteCancellationVertex: multiple reservations found for guest=%s, cancelling first",
                order.guest_name,
            )

        reservation = matches[0]

        # Step 2: cancel.
        try:
            self._store.cancel_reservation(reservation.reservation_id)
        except ValueError as exc:
            logger.error("ExecuteCancellationVertex: cancel failed: %s", exc)
            msg = f"Omlouváme se, rezervaci se nepodařilo zrušit: {exc}"
            # cs: Chyba store při rušení — informujte hosta.
            return HotelBookingSignal.fail, HotelBookingPatch(
                messages=({"role": "assistant", "content": msg},),
                order=Order(),
                flow="initial",
                final_response=msg,
            )

        msg = (
            f"Rezervace pro {reservation.guest_name} "
            f"({reservation.check_in.isoformat()} – {reservation.check_out.isoformat()}) "
            "byla úspěšně zrušena."
            # cs: Potvrzení zrušení rezervace s jménem hosta a termínem.
        )
        logger.info(
            "ExecuteCancellationVertex: cancelled  id=%s  guest=%s",
            reservation.reservation_id, reservation.guest_name,
        )

        patch = HotelBookingPatch(
            messages=({"role": "assistant", "content": msg},),
            order=Order(),     # reset order after cancellation
            flow="initial",
            final_response=msg,
        )
        return HotelBookingSignal.done, patch
