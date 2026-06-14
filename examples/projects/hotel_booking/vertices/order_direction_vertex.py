"""Vertex: OrderDirectionVertex — intent detection and flow routing.

Runs at the START of every conversation turn.

When flow == "initial" the vertex calls the LLM to determine the guest's
intent (NEW_BOOKING, CANCELLATION, INQUIRY, OTHER, or unknown) and extracts
any booking data the guest volunteered in the same message.

When flow is already set (booking / cancellation / awaiting_confirmation)
the vertex short-circuits without an LLM call and routes directly to the
appropriate downstream vertex.  This avoids an extra LLM round-trip on every
turn once the conversation is in a well-defined phase.
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
from ._base import (
    HotelBookingVertexBase,
    _BOOKING_FIELD_SPECS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM response schema (used only when flow == "initial")
# ---------------------------------------------------------------------------

class DirectionResult(BaseModel):
    """Structured output from the intent-detection LLM call."""

    action: Literal["NEW_BOOKING", "CANCELLATION", "INQUIRY", "OTHER", ""] = Field(
        default="",
        description=(
            "Detected guest intent. "
            "NEW_BOOKING: guest wants to book a room. "
            "CANCELLATION: guest wants to cancel a booking. "
            "INQUIRY: guest is asking about room availability, prices, or details. "
            "OTHER: completely off-topic. "
            "Empty string: intent is still unclear."
            # cs: Záměr hosta. NEW_BOOKING=rezervace, CANCELLATION=zrušení,
            # cs: INQUIRY=dotaz na pokoje, OTHER=mimo téma, ""=nejasné.
        ),
    )
    # Voluntarily provided booking data — extract even on first turn if present.
    guest_name:       str = Field(default="", description="Guest name if provided in the message.")
    check_in:         str = Field(default="", description="Check-in date (YYYY-MM-DD) if provided.")
    check_out:        str = Field(default="", description="Check-out date (YYYY-MM-DD) if provided.")
    capacity:         int = Field(default=0, ge=0, le=3, description="Number of guests if provided.")
    selected_room_id: str = Field(
        default="",
        description="Room ID if provided. Must be one of: red, blue, green, white.",
        json_schema_extra={"enum": ["red", "blue", "green", "white", ""]},
    )
    user_question: str = Field(
        description=(
            "TTS-ready greeting or question for the guest, in Czech. "
            "On the first interaction introduce Emma and explain what the hotel can help with. "
            "When intent is already clear, respond naturally and guide the guest. "
            "Two sentences maximum."
            # cs: TTS-ready pozdrav nebo otázka pro hosta, česky, max. dvě věty.
            # cs: Při první interakci se představte jako Emma a vysvětlete, s čím hotel pomůže.
        )
    )


# ---------------------------------------------------------------------------
# Vertex
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = (
    "Based on the conversation so far, determine the guest's intent and fill the JSON schema.\n"
    "Extract any booking information (name, dates, room, number of guests) the guest mentioned "
    "— even if the primary intent is not yet clear.\n"
    "In user_question write a natural Czech response that either:\n"
    "  - introduces Emma and invites the guest to explain their need (first interaction), or\n"
    "  - confirms what you understood and asks for the missing intent if still unclear.\n"
    "<output_schema>DirectionResult</output_schema>"
    # cs: Na základě dosavadní konverzace urči záměr hosta a vyplň JSON schéma.
    # cs: Extrahuj jakékoliv rezervační údaje (jméno, termíny, pokoj, počet osob).
    # cs: V user_question napiš přirozenu českou odpověď.
)


class OrderDirectionVertex(HotelBookingVertexBase):
    """Detect guest intent and route to the appropriate downstream vertex.

    Calls the LLM only when flow == 'initial' to keep subsequent turns fast.
    Once the flow is established (booking / cancellation / awaiting_confirmation)
    this vertex routes without any LLM call.
    """

    system_prompt: Annotated[str, Field(
        description="Additional system instructions for intent detection.",
        json_schema_extra={"x-textarea": True},
    )] = (
        # Extra instructions specific to intent detection.
        # The base system prompt (persona, TTS, ASR, catalogue) is always injected.
        "On the very first interaction (no assistant messages yet in history), "
        "greet the guest warmly and introduce yourself as Emma.\n"
        "Extract the guest's intent even when the message is short or ambiguous.\n"
        "If multiple intents are detectable, prioritise NEW_BOOKING over CANCELLATION."
        # cs: Při první interakci pozdravte hosta a představte se jako Emma.
        # cs: Extrahujte záměr i z krátkých nebo nejednoznačných zpráv.
        # cs: Je-li více záměrů, preferujte NEW_BOOKING před CANCELLATION.
    )

    async def run(
        self, state: HotelBookingState, ctx: object
    ) -> tuple[Signal, HotelBookingPatch]:
        """Route based on current flow or detect intent via LLM.

        Args:
            state: Current graph state.
            ctx:   Shared context with LLM pool.

        Returns:
            (signal, patch) pair for the runner.
        """
        # Short-circuit: flow already determined from a previous turn.
        if state.flow == "awaiting_confirmation":
            return HotelBookingSignal.awaiting_confirmation, HotelBookingPatch()

        if state.flow == "booking":
            return HotelBookingSignal.order_request, HotelBookingPatch()

        if state.flow == "cancellation":
            return HotelBookingSignal.order_cancellation, HotelBookingPatch()

        # flow == "initial": call LLM to detect intent.
        messages = self.build_messages(
            state, _EXTRACTION_PROMPT, extra_system=self.system_prompt
        )
        response = await ctx.llm_for_model(self.model).achat(
            messages, response_schema=DirectionResult, temperature=self.temperature
        )
        parsed = self.parse_llm_json(response.content, DirectionResult)

        if parsed is None:
            return HotelBookingSignal.need_more_data, self.error_patch()

        # Build updated order with any voluntarily provided data.
        update_kwargs: dict = {}
        for field_name in _BOOKING_FIELD_SPECS:
            val = getattr(parsed, field_name, None)
            if val not in ("", 0, None):
                update_kwargs[field_name] = val
        if parsed.action:
            update_kwargs["action"] = parsed.action
        new_order = state.order.with_update(**update_kwargs)

        question = parsed.user_question

        match parsed.action:
            case "NEW_BOOKING":
                patch = HotelBookingPatch(order=new_order, flow="booking")
                return HotelBookingSignal.order_request, patch

            case "CANCELLATION":
                patch = HotelBookingPatch(order=new_order, flow="cancellation")
                return HotelBookingSignal.order_cancellation, patch

            case "INQUIRY":
                # Route to inquiry vertex without changing flow (guest may return to booking).
                patch = HotelBookingPatch(order=new_order)
                return HotelBookingSignal.order_inquiry, patch

            case "OTHER":
                msgs_out = ({"role": "assistant", "content": question},)
                patch = HotelBookingPatch(order=new_order, messages=msgs_out, final_response=question)
                return HotelBookingSignal.order_other, patch

            case _:
                # Unknown intent — ask again next turn.
                msgs_out = ({"role": "assistant", "content": question},)
                patch = HotelBookingPatch(order=new_order, messages=msgs_out, final_response=question)
                return HotelBookingSignal.need_more_data, patch
