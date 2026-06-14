"""Vertex: OtherHandlerVertex — handle off-topic messages.

When the guest says something unrelated to hotel booking, room information,
or cancellation this vertex responds politely and redirects them back to
the hotel service topics.

After the redirect it emits done → StdEnd.  The next turn will restart
at OrderDirectionVertex which will re-route based on state.flow:
  - flow == 'booking'      → OrderDetailsVertex (continue incomplete booking)
  - flow == 'cancellation' → CancellationDetailsVertex
  - flow == 'initial'      → intent detection again
"""

from __future__ import annotations

import logging
from typing import Annotated

from pydantic import BaseModel, Field

from agentflow.statemachine import Signal
from ..state import HotelBookingPatch, HotelBookingSignal, HotelBookingState
from ._base import HotelBookingVertexBase

logger = logging.getLogger(__name__)


class RedirectResult(BaseModel):
    """LLM output for the off-topic redirect."""

    user_question: str = Field(
        description=(
            "Polite Czech TTS-ready response that acknowledges the guest's message "
            "and redirects them to hotel services (room booking, cancellation, room info). "
            "Two sentences maximum."
            # cs: Zdvořilá česky TTS-ready odpověď, která přesměruje hosta zpět na hotelové služby.
        )
    )


_EXTRACTION_PROMPT = (
    "The guest has said something unrelated to hotel room booking, "
    "cancellation, or room information.\n"
    "Acknowledge their message politely, then gently remind them that "
    "Emma can help with: room reservations, reservation cancellations, "
    "and room availability or pricing questions.\n"
    "If the guest was in the middle of a booking or cancellation, "
    "invite them to continue.\n"
    "<output_schema>RedirectResult</output_schema>"
    # cs: Host odbočil od tématu. Zdvořile potvrďte a připomeňte, s čím Emma pomůže.
    # cs: Pokud byl host uprostřed rezervace/zrušení, vyzvi ho k pokračování.
)


class OtherHandlerVertex(HotelBookingVertexBase):
    """Politely redirect off-topic messages back to hotel services."""

    async def run(
        self, state: HotelBookingState, ctx: object
    ) -> tuple[Signal, HotelBookingPatch]:
        """Generate a polite redirect response.

        Args:
            state: Current graph state.
            ctx:   Shared context with LLM pool.

        Returns:
            (done, patch) — always terminates to StdEnd.
        """
        messages = self.build_messages(state, _EXTRACTION_PROMPT)
        response = await ctx.llm_for_model(self.model).achat(
            messages, response_schema=RedirectResult, temperature=self.temperature
        )
        parsed = self.parse_llm_json(response.content, RedirectResult)

        if parsed is None:
            return HotelBookingSignal.done, self.error_patch()

        answer = parsed.user_question
        msgs_out = ({"role": "assistant", "content": answer},)
        patch = HotelBookingPatch(messages=msgs_out, final_response=answer)
        return HotelBookingSignal.done, patch
