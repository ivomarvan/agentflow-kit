"""Vertex: InquiryVertex — answer room availability and information questions.

Uses achat_with_tools() so the LLM can call GetRoomDetailsTool,
CheckAvailabilityTool, and CalculatePriceTool to retrieve accurate data
before composing a TTS-ready response.

After answering the inquiry the vertex always emits done → StdEnd.
If the guest was previously in a booking or cancellation flow, the next turn
will return to OrderDirectionVertex which re-routes to the correct phase.
"""

from __future__ import annotations

import logging
from typing import Annotated

from pydantic import Field

from agentflow.statemachine import Signal
from ..state import HotelBookingPatch, HotelBookingSignal, HotelBookingState
from ._base import HotelBookingVertexBase

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = (
    "The guest is asking about room information, availability, or pricing.\n"
    "Use the available tools to retrieve accurate data, then compose a natural "
    "Czech TTS-ready answer.  Two sentences maximum.\n"
    "If the guest was in the middle of a booking, after answering acknowledge "
    "this and invite them to continue.\n"
    # cs: Host se ptá na informace o pokojích, dostupnost nebo ceny.
    # cs: Použij nástroje pro přesná data, pak odpověz česky (max. dvě věty).
    # cs: Pokud byl host uprostřed rezervace, po odpovědi ho vyzvi k pokračování.
)


class InquiryVertex(HotelBookingVertexBase):
    """Answer room-related questions using tools and return to conversation flow."""

    system_prompt: Annotated[str, Field(
        description="Vertex-specific instructions for room inquiry handling.",
        json_schema_extra={"x-textarea": True},
    )] = (
        "Answer questions about room availability, capacity, prices, and features "
        "using the room catalogue and tools.  Be concise and helpful."
        # cs: Odpovídejte na otázky o dostupnosti, kapacitě, cenách a vlastnostech pokojů.
        # cs: Používejte katalog pokojů a nástroje. Buďte stručné a nápomocné.
    )

    async def run(
        self, state: HotelBookingState, ctx: object
    ) -> tuple[Signal, HotelBookingPatch]:
        """Call LLM with tool access to answer the room inquiry.

        Args:
            state: Current graph state.
            ctx:   Shared context with LLM pool and tool registries.

        Returns:
            (done, patch) — always terminates to StdEnd.
        """
        messages = self.build_messages(
            state, _EXTRACTION_PROMPT, extra_system=self.system_prompt
        )
        registry = ctx.get_tools("default")
        response = await ctx.llm_for_model(self.model).achat_with_tools(
            messages, registry, temperature=self.temperature
        )
        answer = response.content or "Promiňte, nepodařilo se mi získat požadované informace."
        # cs: Záložní zpráva pokud LLM nevrátí obsah.

        msgs_out = ({"role": "assistant", "content": answer},)
        patch = HotelBookingPatch(messages=msgs_out, final_response=answer)
        return HotelBookingSignal.done, patch
