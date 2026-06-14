"""Vertex: OrderConfirmationVertex — present booking summary and collect confirmation.

Two-phase operation driven by state.flow:

Phase 1 (flow == 'booking', emits need_more_data):
  The LLM presents the full booking summary and asks the guest to confirm.
  Sets flow = 'awaiting_confirmation' so the next turn skips intent detection.

Phase 2 (flow == 'awaiting_confirmation', emits confirmed or declined):
  The LLM reads the guest's confirmation answer from history and decides.
  On confirmed → ExecuteBookingVertex.
  On declined  → StdEnd + order + flow reset.
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from agentflow.statemachine import Signal
from ..state import (
    HotelBookingPatch,
    HotelBookingSignal,
    HotelBookingState,
    Order,
)
from ._base import HotelBookingVertexBase

logger = logging.getLogger(__name__)


class ConfirmationResult(BaseModel):
    """LLM output for the confirmation dialog."""

    user_question: str = Field(
        description=(
            "TTS-ready Czech response for the guest. "
            "Phase 1: full booking summary + confirmation question. "
            "Phase 2: confirm booking success or acknowledge cancellation. "
            "Two sentences maximum."
            # cs: TTS-ready česká odpověď. Fáze 1: přehled rezervace + otázka na potvrzení.
            # cs: Fáze 2: potvrzení úspěšné rezervace nebo odmítnutí.
        )
    )
    confirmed: bool | None = Field(
        default=None,
        description=(
            "True if the guest explicitly confirmed the booking. "
            "False if the guest explicitly declined. "
            "None if the guest has not yet answered (first visit)."
            # cs: True=host potvrdil, False=host odmítl, None=host ještě neodpověděl.
        ),
    )


_PROMPT_PHASE1 = (
    "The booking data collection is complete.  Present the following booking summary "
    "to the guest in a warm, friendly Czech tone and ask for explicit confirmation.\n"
    "Booking summary:\n"
    "{order_summary}\n"
    "In user_question: summarise the booking details (room, dates, total price in words) "
    "and ask 'Do you confirm?' — max two sentences.\n"
    "Set confirmed=None (guest has not yet answered).\n"
    "<output_schema>ConfirmationResult</output_schema>"
    # cs: Sběr dat dokončen. Přečtěte přehled rezervace a zeptejte se na potvrzení.
)

_PROMPT_PHASE2 = (
    "The guest was presented with the booking summary and has now responded.\n"
    "Determine from the conversation whether the guest confirmed or declined.\n"
    "Set confirmed=True for 'yes / confirm / ok / ano / jo / souhlasím / potvrdit'.\n"
    "Set confirmed=False for 'no / cancel / ne / zrušit / nechci'.\n"
    "Set confirmed=None if the response is ambiguous.\n"
    "In user_question: if confirmed, acknowledge the booking warmly; "
    "if declined, acknowledge politely; if ambiguous, ask again.\n"
    "<output_schema>ConfirmationResult</output_schema>"
    # cs: Host dostal přehled rezervace a odpověděl. Určete zda potvrdil nebo odmítl.
)


def _order_summary(order: Order) -> str:
    """Format order fields for the confirmation prompt.

    Args:
        order: Current Order state (must have all booking fields set).

    Returns:
        Human-readable multi-line summary in English.
    """
    try:
        from ..live_state import _ROOM_CATALOGUE
        room_name = next(
            (r[1] for r in _ROOM_CATALOGUE if r[0] == order.selected_room_id),
            order.selected_room_id,
        )
    except Exception:
        room_name = order.selected_room_id
    return (
        f"  Room:       {room_name} ({order.selected_room_id})\n"
        f"  Guest:      {order.guest_name}\n"
        f"  Check-in:   {order.check_in}\n"
        f"  Check-out:  {order.check_out}\n"
        f"  Guests:     {order.capacity}\n"
        f"  Total:      €{order.total_price:.0f}"
    )


class OrderConfirmationVertex(HotelBookingVertexBase):
    """Present booking summary and collect explicit confirmation from the guest."""

    system_prompt: Annotated[str, Field(
        description="Vertex-specific system instructions for confirmation dialog.",
        json_schema_extra={"x-textarea": True},
    )] = (
        "You are confirming a room booking with the guest.\n"
        "Always state prices in words (e.g. 'three hundred and forty euros').\n"
        "Wait for an unambiguous yes or no before proceeding."
        # cs: Potvrzujete rezervaci s hostem. Ceny uvádějte slovy.
        # cs: Počkejte na jednoznačné ano nebo ne.
    )

    async def run(
        self, state: HotelBookingState, ctx: object
    ) -> tuple[Signal, HotelBookingPatch]:
        """Present summary (phase 1) or process confirmation (phase 2).

        Args:
            state: Current graph state.
            ctx:   Shared context with LLM pool.

        Returns:
            (signal, patch) pair for the runner.
        """
        order = state.order
        is_phase2 = state.flow == "awaiting_confirmation"
        prompt = (
            _PROMPT_PHASE2
            if is_phase2
            else _PROMPT_PHASE1.format(order_summary=_order_summary(order))
        )

        messages = self.build_messages(
            state, prompt, extra_system=self.system_prompt
        )
        response = await ctx.llm_for_model(self.model).achat(
            messages, response_schema=ConfirmationResult, temperature=self.temperature
        )
        parsed = self.parse_llm_json(response.content, ConfirmationResult)

        if parsed is None:
            return HotelBookingSignal.need_more_data, self.error_patch()

        question = parsed.user_question
        msgs_out = ({"role": "assistant", "content": question},)

        if parsed.confirmed is True:
            patch = HotelBookingPatch(
                messages=msgs_out,
                final_response=question,
                flow="initial",  # reset after successful booking
            )
            return HotelBookingSignal.confirmed, patch

        if parsed.confirmed is False:
            patch = HotelBookingPatch(
                messages=msgs_out,
                order=Order(),    # reset order after declined booking
                final_response=question,
                flow="initial",
            )
            return HotelBookingSignal.declined, patch

        # confirmed == None: first visit or ambiguous — ask / wait for next turn.
        patch = HotelBookingPatch(
            messages=msgs_out,
            final_response=question,
            flow="awaiting_confirmation",
        )
        return HotelBookingSignal.need_more_data, patch
