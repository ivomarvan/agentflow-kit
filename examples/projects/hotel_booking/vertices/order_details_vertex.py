"""Vertex: OrderDetailsVertex — iterative data collection for new bookings.

Runs after OrderDirectionVertex when flow == 'booking'.

Uses make_partial_order_schema() to build a dynamic Pydantic model that
contains ONLY the Order fields still missing — the schema shrinks turn by
turn as the guest provides information.  When all required fields are filled
the vertex emits data_complete; otherwise it emits need_more_data so the
runner reaches StdEnd and waits for the guest's next message.

The LLM also receives an is_off_topic flag so it can signal when the guest
has switched to an unrelated topic (→ OtherHandlerVertex) and an
is_inquiry flag for mid-booking room questions (→ InquiryVertex).
"""

from __future__ import annotations

import logging
from typing import Annotated

from pydantic import Field

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
    make_partial_order_schema,
)

logger = logging.getLogger(__name__)


def _is_booking_complete(order: Order) -> bool:
    """Return True when all required booking fields are filled.

    Args:
        order: Current Order state.

    Returns:
        True if guest_name, check_in, check_out, capacity > 0, and
        selected_room_id are all non-empty.
    """
    return bool(
        order.guest_name
        and order.check_in
        and order.check_out
        and order.capacity > 0
        and order.selected_room_id
    )


_EXTRACTION_PROMPT_TEMPLATE = (
    "The guest is in the process of booking a room.\n"
    "Current booking order:\n"
    "{order_summary}\n\n"
    "Task:\n"
    "1. Extract any booking information from the guest's latest message and fill it "
    "into the JSON schema (only the unfilled fields are present in the schema).\n"
    "2. Generate user_question: a natural Czech TTS-ready question asking for the "
    "NEXT missing piece of information.  If only one field is missing, ask for it directly.  "
    "If the guest just provided data, confirm it warmly before asking for the next field.\n"
    "3. Set is_off_topic=True if the guest is talking about something completely unrelated.\n"
    "4. Set is_inquiry=True if the guest is asking about room details or availability "
    "(you can answer room questions from the catalogue and then ask for the missing data).\n"
    "<output_schema>OrderUpdate (dynamic — unfilled fields only)</output_schema>"
    # cs: Host provádí rezervaci. Úkol: extrahuj rezervační data z poslední zprávy,
    # cs: ptej se na chybějící pole, nastav is_off_topic/is_inquiry dle situace.
)


def _order_summary(order: Order) -> str:
    """Format the current Order as a concise English summary for the prompt.

    Args:
        order: Current Order state.

    Returns:
        Multi-line string showing filled and missing fields.
    """
    def _val(v: object) -> str:
        return str(v) if v not in ("", 0, None) else "<missing>"

    return (
        f"  guest_name:       {_val(order.guest_name)}\n"
        f"  check_in:         {_val(order.check_in)}\n"
        f"  check_out:        {_val(order.check_out)}\n"
        f"  capacity:         {_val(order.capacity)}\n"
        f"  selected_room_id: {_val(order.selected_room_id)}"
    )


class OrderDetailsVertex(HotelBookingVertexBase):
    """Collect booking data turn-by-turn using a dynamic schema.

    Loops (across turns via StdEnd) until all five booking fields are filled,
    then emits data_complete to trigger availability checking.
    """

    system_prompt: Annotated[str, Field(
        description="Vertex-specific system instructions for booking data collection.",
        json_schema_extra={"x-textarea": True},
    )] = (
        "You are collecting booking details for a new room reservation.\n"
        "Ask for one or two missing fields per turn — do not bombard the guest.\n"
        "If the guest provides the room name instead of ID, map it: "
        "Red Room→red, Blue Room→blue, Green Room→green, White Room→white.\n"
        "Always address the guest by name if you know it."
        # cs: Sbíráte rezervační údaje. Ptejte se na jedno nebo dvě pole najednou.
        # cs: Mapujte jméno pokoje na ID: Červený→red, Modrý→blue, atd.
        # cs: Pokud znáte jméno hosta, vždy ho oslovujte.
    )

    async def run(
        self, state: HotelBookingState, ctx: object
    ) -> tuple[Signal, HotelBookingPatch]:
        """Extract booking data and determine if collection is complete.

        Args:
            state: Current graph state with accumulated order.
            ctx:   Shared context with LLM pool.

        Returns:
            (signal, patch) pair for the runner.
        """
        order = state.order

        # Build dynamic schema with only unfilled booking fields.
        DynamicSchema = make_partial_order_schema(order, _BOOKING_FIELD_SPECS)

        extraction_prompt = _EXTRACTION_PROMPT_TEMPLATE.format(
            order_summary=_order_summary(order)
        )
        messages = self.build_messages(
            state, extraction_prompt, extra_system=self.system_prompt
        )
        response = await ctx.llm_for_model(self.model).achat(
            messages, response_schema=DynamicSchema, temperature=self.temperature
        )
        parsed = self.parse_llm_json(response.content, DynamicSchema)

        if parsed is None:
            return HotelBookingSignal.need_more_data, self.error_patch()

        # Redirect when guest goes off-topic or asks a room inquiry.
        if getattr(parsed, "is_off_topic", False):
            question = getattr(parsed, "user_question", "")
            msgs_out = ({"role": "assistant", "content": question},) if question else ()
            return HotelBookingSignal.order_other, HotelBookingPatch(
                messages=msgs_out, final_response=question
            )

        if getattr(parsed, "is_inquiry", False):
            return HotelBookingSignal.order_inquiry, HotelBookingPatch()

        # Merge newly extracted fields into order (skip system-computed fields).
        update_kwargs: dict = {}
        for field_name in _BOOKING_FIELD_SPECS:
            val = getattr(parsed, field_name, None)
            if val not in ("", 0, None):
                update_kwargs[field_name] = val
        new_order = order.with_update(**update_kwargs)

        question = parsed.user_question
        msgs_out: tuple[dict, ...] = ({"role": "assistant", "content": question},)

        if _is_booking_complete(new_order):
            patch = HotelBookingPatch(
                messages=msgs_out,
                order=new_order,
                final_response=question,
            )
            return HotelBookingSignal.data_complete, patch

        patch = HotelBookingPatch(
            messages=msgs_out,
            order=new_order,
            final_response=question,
        )
        return HotelBookingSignal.need_more_data, patch
