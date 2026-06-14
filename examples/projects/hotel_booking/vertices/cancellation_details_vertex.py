"""Vertex: CancellationDetailsVertex — iterative data collection for cancellations.

Mirrors OrderDetailsVertex but uses _CANCELLATION_FIELD_SPECS.
Required fields: guest_name + (reservation_id OR check_in).
When at least one identifying field is present alongside guest_name
the vertex emits data_complete → ExecuteCancellationVertex.
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
    _CANCELLATION_FIELD_SPECS,
    make_partial_order_schema,
)

logger = logging.getLogger(__name__)


def _is_cancellation_complete(order: Order) -> bool:
    """Return True when enough data is present to attempt a cancellation.

    Args:
        order: Current Order state.

    Returns:
        True if guest_name is known AND either reservation_id or check_in is set.
    """
    return bool(order.guest_name and (order.reservation_id or order.check_in))


_EXTRACTION_PROMPT_TEMPLATE = (
    "The guest wants to cancel a reservation.\n"
    "Current information collected:\n"
    "{order_summary}\n\n"
    "Task:\n"
    "1. Extract any cancellation details from the guest's latest message.\n"
    "2. Generate user_question: a natural Czech TTS-ready question asking for "
    "missing details.  We need the guest's name and at least one of: "
    "reservation ID or check-in date to find the booking.\n"
    "3. Set is_off_topic=True if the guest is clearly talking about something else.\n"
    "<output_schema>OrderUpdate (dynamic — unfilled cancellation fields only)</output_schema>"
    # cs: Host chce zrušit rezervaci. Extrahuj jméno, ID rezervace nebo datum příjezdu.
    # cs: Ptej se na chybějící pole. Nastav is_off_topic při odbočení od tématu.
)


def _order_summary(order: Order) -> str:
    """Format relevant cancellation fields as a concise summary.

    Args:
        order: Current Order state.

    Returns:
        Multi-line string showing filled and missing cancellation fields.
    """
    def _val(v: object) -> str:
        return str(v) if v not in ("", 0, None) else "<missing>"

    return (
        f"  guest_name:     {_val(order.guest_name)}\n"
        f"  reservation_id: {_val(order.reservation_id)}\n"
        f"  check_in:       {_val(order.check_in)}"
    )


class CancellationDetailsVertex(HotelBookingVertexBase):
    """Collect cancellation details turn-by-turn using a dynamic schema.

    Loops across turns until guest_name + an identifying field are available,
    then emits data_complete to trigger ExecuteCancellationVertex.
    """

    system_prompt: Annotated[str, Field(
        description="Vertex-specific system instructions for cancellation data collection.",
        json_schema_extra={"x-textarea": True},
    )] = (
        "You are collecting details to cancel an existing reservation.\n"
        "Ask for the guest's name first, then the reservation ID or check-in date.\n"
        "Be empathetic — the guest may be cancelling due to an emergency."
        # cs: Sbíráte údaje pro zrušení rezervace.
        # cs: Zeptejte se nejprve na jméno, pak na ID rezervace nebo datum příjezdu.
        # cs: Buďte empatičtí — host možná ruší z naléhavých důvodů.
    )

    async def run(
        self, state: HotelBookingState, ctx: object
    ) -> tuple[Signal, HotelBookingPatch]:
        """Extract cancellation data and decide if collection is complete.

        Args:
            state: Current graph state with accumulated order.
            ctx:   Shared context with LLM pool.

        Returns:
            (signal, patch) pair for the runner.
        """
        order = state.order

        DynamicSchema = make_partial_order_schema(order, _CANCELLATION_FIELD_SPECS)

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

        if getattr(parsed, "is_off_topic", False):
            question = getattr(parsed, "user_question", "")
            msgs_out = ({"role": "assistant", "content": question},) if question else ()
            return HotelBookingSignal.order_other, HotelBookingPatch(
                messages=msgs_out, final_response=question
            )

        update_kwargs: dict = {}
        for field_name in _CANCELLATION_FIELD_SPECS:
            val = getattr(parsed, field_name, None)
            if val not in ("", 0, None):
                update_kwargs[field_name] = val
        new_order = order.with_update(**update_kwargs)

        question = parsed.user_question
        msgs_out = ({"role": "assistant", "content": question},)

        if _is_cancellation_complete(new_order):
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
