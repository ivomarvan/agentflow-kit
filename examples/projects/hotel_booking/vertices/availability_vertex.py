"""Vertex: AvailabilityVertex — check room availability without an LLM call.

A pure StateVertex that uses BookingStore directly to verify whether the
selected room is free for the requested dates.  If available it also
computes the total price and stores it in order.total_price.

Emits:
  available   → OrderConfirmationVertex
  unavailable → StdEnd  (guest is informed via final_response; alternatives TBD)
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
)

logger = logging.getLogger(__name__)


class AvailabilityVertex(StateVertex):
    """Check room availability and compute total price (no LLM).

    Inject the BookingStore via the constructor so the vertex can call
    store methods directly without going through the tool registry.
    """

    _store: BookingStore = PrivateAttr()

    def __init__(self, store: BookingStore, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._store = store

    async def run(
        self, state: HotelBookingState, ctx: object
    ) -> tuple[Signal, HotelBookingPatch]:
        """Verify availability and return available/unavailable signal.

        Args:
            state: Current graph state; order must have all booking fields set.
            ctx:   Shared context (unused — no LLM call).

        Returns:
            (available, patch) with total_price set, or (unavailable, patch)
            with a Czech TTS-ready final_response.
        """
        order = state.order
        try:
            check_in = date.fromisoformat(order.check_in)
            check_out = date.fromisoformat(order.check_out)
        except ValueError as exc:
            logger.error("AvailabilityVertex: invalid dates: %s", exc)
            msg = "Promiňte, nepodařilo se ověřit dostupnost. Zkontrolujte prosím zadaná data."
            # cs: Chyba při parsování dat — požádejte hosta o opakování.
            return HotelBookingSignal.unavailable, HotelBookingPatch(final_response=msg)

        available_rooms = self._store.check_availability(check_in, check_out, order.capacity)
        available_ids = {r.room_id for r in available_rooms}

        if order.selected_room_id not in available_ids:
            # Inform guest in Czech; alternatives flow to be added later.
            try:
                room = self._store.get_room(order.selected_room_id)
                room_name = room.name
            except ValueError:
                room_name = order.selected_room_id
            msg = (
                f"Bohužel, pokoj {room_name} není v termínu "
                f"{order.check_in} – {order.check_out} k dispozici."
                # cs: Požadovaný pokoj není v daném termínu volný.
            )
            logger.info(
                "AvailabilityVertex: room=%s unavailable  in=%s  out=%s  cap=%d",
                order.selected_room_id, order.check_in, order.check_out, order.capacity,
            )
            return HotelBookingSignal.unavailable, HotelBookingPatch(
                messages=({"role": "assistant", "content": msg},),
                final_response=msg,
            )

        # Room is available — compute price.
        try:
            total = self._store.calculate_price(order.selected_room_id, check_in, check_out)
        except ValueError as exc:
            logger.error("AvailabilityVertex: price calculation failed: %s", exc)
            total = 0.0

        new_order = order.with_update(total_price=total)
        logger.info(
            "AvailabilityVertex: room=%s available  price=%.0f EUR",
            order.selected_room_id, total,
        )
        return HotelBookingSignal.available, HotelBookingPatch(order=new_order)
