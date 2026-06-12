"""State machine vertices and system prompts for the hotel booking assistant."""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Annotated, Any

from pydantic import Field

from agentflow.statemachine import Context, LlmStateVertex, StateVertex
from examples.projects.hotel_booking.booking_store import _STORE
from examples.projects.hotel_booking.state import HotelPatch, HotelSignal, HotelState

_logger = logging.getLogger(__name__)

PERSONA_HEADER = """
You are Emma, a virtual receptionist at the Four Colours Hotel.
Your role: help guests book rooms, cancel reservations, and answer room questions.
You are an AI assistant — never claim to be human.
""".strip()

TTS_CONSTRAINTS = """
<tts_constraints>
Reply as if speaking on the phone. Maximum two sentences per turn.
No markdown, bullet points, URLs, or special characters.
Write all numbers and monetary amounts in words.
Use a warm, professional tone.
</tts_constraints>
""".strip()

ASR_CONSTRAINTS = """
<asr_constraints>
The user's text may come from a speech recogniser.
Parse dates and names flexibly (e.g. "fourteenth of july", "14.7.", "Jul 14", "14/7/2026").
If the input is unclear, ask the user to repeat — up to 3 times, then escalate politely.
</asr_constraints>
""".strip()

_INTENT_SYSTEM = f"""{PERSONA_HEADER}

{TTS_CONSTRAINTS}

{ASR_CONSTRAINTS}

Classify the guest message into exactly one intent:
NEW_BOOKING, CANCELLATION, INQUIRY, or OTHER.

Respond with JSON only:
{{"intent": "...", "guest_name": "", "check_in": "", "check_out": "", "capacity": 0}}

Fill any fields you can extract from the message; leave others empty or zero.

Examples:
User: I would like a room for two from July twentieth to twenty-second, name Smith.
{{"intent": "NEW_BOOKING", "guest_name": "Smith", "check_in": "2026-07-20",
  "check_out": "2026-07-22", "capacity": 2}}

User: Please cancel the Novak family reservation arriving July tenth.
{{"intent": "CANCELLATION", "guest_name": "Novak family", "check_in": "2026-07-10",
  "check_out": "", "capacity": 0}}

User: How much is the red room per night?
{{"intent": "INQUIRY", "guest_name": "", "check_in": "", "check_out": "", "capacity": 0}}

User: What is the weather like today?
{{"intent": "OTHER", "guest_name": "", "check_in": "", "check_out": "", "capacity": 0}}
"""

_ASK_DATES_SYSTEM = f"""{PERSONA_HEADER}

{TTS_CONSTRAINTS}

{ASR_CONSTRAINTS}

Extract check-in and check-out dates from the guest message.
Respond with JSON only:
{{"check_in": "YYYY-MM-DD", "check_out": "YYYY-MM-DD", "voice_reply": "..."}}

Date parsing examples:
User: from the fourteenth to the seventeenth of July
{{"check_in": "2026-07-14", "check_out": "2026-07-17",
  "voice_reply": "Thank you, I have the fourteenth to the seventeenth of July."}}

User: 20.7. to 22.7.
{{"check_in": "2026-07-20", "check_out": "2026-07-22",
  "voice_reply": "Got it, July twentieth to twenty-second."}}

User: Jul 8 until Jul 11
{{"check_in": "2026-07-08", "check_out": "2026-07-11",
  "voice_reply": "Perfect, eighth to eleventh of July."}}
"""

_INTENT_TO_SIGNAL: dict[str, HotelSignal] = {
    "NEW_BOOKING": HotelSignal.intent_new,
    "CANCELLATION": HotelSignal.intent_cancel,
    "INQUIRY": HotelSignal.intent_inquiry,
    "OTHER": HotelSignal.intent_other,
}


def _last_user_content(state: HotelState) -> str:
    """Return the most recent user message text."""
    for message in reversed(state.messages):
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


def _extract_json(text: str) -> dict[str, Any]:
    """Parse JSON from an LLM response, tolerating surrounding prose."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {}


def _merge_patch(base: HotelPatch, **fields: Any) -> HotelPatch:
    """Build a HotelPatch, skipping None values."""
    data = {key: value for key, value in fields.items() if value is not None}
    return HotelPatch(**data) if data else HotelPatch()


class IntentParserVertex(LlmStateVertex):
    """Classify guest intent and pre-fill booking fields when possible."""

    model: Annotated[str, Field(
        description="LLM model name (economy tier).",
        json_schema_extra={"x-model-select": True},
    )] = "gpt-4o-mini"

    system_prompt: Annotated[str, Field(
        description="Intent classification instructions with few-shot examples.",
        json_schema_extra={"x-textarea": True},
    )] = _INTENT_SYSTEM

    async def run(
        self, state: HotelState, ctx: Context
    ) -> tuple[HotelSignal, HotelPatch]:
        """Parse intent JSON and route to the appropriate workflow branch."""
        response = await ctx.llm_for_model(self.model).achat(
            [
                {"role": "system", "content": self.system_prompt},
                *state.messages,
            ],
            temperature=self.temperature,
        )
        data = _extract_json(response.text)
        intent = str(data.get("intent", "OTHER")).upper()
        signal = _INTENT_TO_SIGNAL.get(intent, HotelSignal.intent_other)
        capacity = int(data.get("capacity") or 0)
        return signal, HotelPatch(
            intent=intent,
            guest_name=str(data.get("guest_name") or ""),
            check_in=str(data.get("check_in") or ""),
            check_out=str(data.get("check_out") or ""),
            capacity=capacity,
        )


class DataDispatcherVertex(StateVertex):
    """Route to the next missing booking field without calling an LLM."""

    async def run(
        self, state: HotelState, ctx: Context
    ) -> tuple[HotelSignal, HotelPatch]:
        """Inspect state and emit the next data-collection signal."""
        if state.guest_name == "":
            return HotelSignal.need_name, HotelPatch()
        if state.check_in == "" or state.check_out == "":
            return HotelSignal.need_dates, HotelPatch()
        if state.capacity == 0:
            return HotelSignal.need_capacity, HotelPatch()
        return HotelSignal.data_complete, HotelPatch()


class AskGuestNameVertex(LlmStateVertex):
    """Ask for the guest name and extract it from the reply."""

    model: Annotated[str, Field(
        json_schema_extra={"x-model-select": True},
    )] = "gpt-4o-mini"

    system_prompt: Annotated[str, Field(
        json_schema_extra={"x-textarea": True},
    )] = (
        f"{PERSONA_HEADER}\n\n{TTS_CONSTRAINTS}\n\n{ASR_CONSTRAINTS}\n\n"
        "Extract the guest name from the message. "
        'Respond JSON: {{"guest_name": "...", "voice_reply": "..."}}'
    )

    async def run(
        self, state: HotelState, ctx: Context
    ) -> tuple[HotelSignal, HotelPatch]:
        """Extract guest_name or ask a voice-friendly follow-up question."""
        response = await ctx.llm_for_model(self.model).achat(
            [
                {"role": "system", "content": self.system_prompt},
                *state.messages,
            ],
            temperature=self.temperature,
        )
        data = _extract_json(response.text)
        guest_name = str(data.get("guest_name") or "").strip()
        voice = str(data.get("voice_reply") or response.text).strip()
        if guest_name:
            return HotelSignal.name_collected, HotelPatch(guest_name=guest_name)
        return HotelSignal.name_collected, HotelPatch(
            guest_name=guest_name,
            final_response=voice,
        )


class AskDatesVertex(LlmStateVertex):
    """Ask for stay dates and normalise them to ISO format."""

    model: Annotated[str, Field(
        json_schema_extra={"x-model-select": True},
    )] = "gpt-4o-mini"

    system_prompt: Annotated[str, Field(
        json_schema_extra={"x-textarea": True},
    )] = _ASK_DATES_SYSTEM

    async def run(
        self, state: HotelState, ctx: Context
    ) -> tuple[HotelSignal, HotelPatch]:
        """Parse check-in and check-out dates from the guest message."""
        response = await ctx.llm_for_model(self.model).achat(
            [
                {"role": "system", "content": self.system_prompt},
                *state.messages,
            ],
            temperature=self.temperature,
        )
        data = _extract_json(response.text)
        check_in = str(data.get("check_in") or "").strip()
        check_out = str(data.get("check_out") or "").strip()
        voice = str(data.get("voice_reply") or response.text).strip()
        if check_in and check_out:
            return HotelSignal.dates_collected, HotelPatch(
                check_in=check_in,
                check_out=check_out,
            )
        return HotelSignal.dates_collected, HotelPatch(
            check_in=check_in,
            check_out=check_out,
            final_response=voice,
        )


class AskCapacityVertex(LlmStateVertex):
    """Ask how many guests will stay."""

    model: Annotated[str, Field(
        json_schema_extra={"x-model-select": True},
    )] = "gpt-4o-mini"

    system_prompt: Annotated[str, Field(
        json_schema_extra={"x-textarea": True},
    )] = (
        f"{PERSONA_HEADER}\n\n{TTS_CONSTRAINTS}\n\n{ASR_CONSTRAINTS}\n\n"
        "Extract the number of guests. "
        'Respond JSON: {{"capacity": N, "voice_reply": "..."}}'
    )

    async def run(
        self, state: HotelState, ctx: Context
    ) -> tuple[HotelSignal, HotelPatch]:
        """Parse guest count from the message."""
        response = await ctx.llm_for_model(self.model).achat(
            [
                {"role": "system", "content": self.system_prompt},
                *state.messages,
            ],
            temperature=self.temperature,
        )
        data = _extract_json(response.text)
        capacity = int(data.get("capacity") or 0)
        voice = str(data.get("voice_reply") or response.text).strip()
        if capacity > 0:
            return HotelSignal.capacity_collected, HotelPatch(capacity=capacity)
        return HotelSignal.capacity_collected, HotelPatch(
            capacity=capacity,
            final_response=voice,
        )


class AvailabilityCheckerVertex(LlmStateVertex):
    """Check room availability and pick the best matching room."""

    model: Annotated[str, Field(
        json_schema_extra={"x-model-select": True},
    )] = "gpt-4o-mini"

    tools: Annotated[str, Field(description="Tool registry key.")] = "default"
    max_rounds: Annotated[int, Field(ge=1, le=10)] = 4

    system_prompt: Annotated[str, Field(
        json_schema_extra={"x-textarea": True},
    )] = (
        f"{PERSONA_HEADER}\n\n{TTS_CONSTRAINTS}\n\n"
        "Check room availability using tools. "
        "After checking, respond JSON: "
        '{"available": true/false, "selected_room_id": "red|blue|green|white", '
        '"total_price": 0.0, "voice_reply": "..."}'
    )

    async def run(
        self, state: HotelState, ctx: Context
    ) -> tuple[HotelSignal, HotelPatch]:
        """Call availability tools and select a room when possible."""
        user_hint = (
            f"Guest: {state.guest_name}, dates {state.check_in} to {state.check_out}, "
            f"capacity {state.capacity}."
        )
        response = await ctx.llm_for_model(self.model).achat_with_tools(
            messages=[
                {"role": "system", "content": self.system_prompt},
                *state.messages,
                {"role": "user", "content": user_hint},
            ],
            registry=ctx.get_tools(self.tools),
            max_rounds=self.max_rounds,
            temperature=self.temperature,
        )
        data = _extract_json(response.text)
        available = bool(data.get("available"))
        if available:
            return HotelSignal.available, HotelPatch(
                selected_room_id=str(data.get("selected_room_id") or ""),
                total_price=float(data.get("total_price") or 0.0),
                confirmation_pending=True,
                final_response=str(data.get("voice_reply") or response.text),
            )
        return HotelSignal.unavailable, HotelPatch(
            final_response=str(data.get("voice_reply") or response.text),
        )


class AlternativesVertex(LlmStateVertex):
    """Present alternative rooms or dates after a conflict."""

    model: Annotated[str, Field(
        json_schema_extra={"x-model-select": True},
    )] = "gpt-4o-mini"

    tools: Annotated[str, Field(description="Tool registry key.")] = "default"
    max_rounds: Annotated[int, Field(ge=1, le=10)] = 4

    system_prompt: Annotated[str, Field(
        json_schema_extra={"x-textarea": True},
    )] = (
        f"{PERSONA_HEADER}\n\n{TTS_CONSTRAINTS}\n\n"
        "Use find_alternatives when the requested room is unavailable. "
        "Present options voice-friendlily. "
        'Respond JSON: {"accepted": true/false, "selected_room_id": "", '
        '"check_in": "", "check_out": "", "total_price": 0.0, "voice_reply": "..."}'
    )

    async def run(
        self, state: HotelState, ctx: Context
    ) -> tuple[HotelSignal, HotelPatch]:
        """Offer alternatives and capture the guest selection."""
        response = await ctx.llm_for_model(self.model).achat_with_tools(
            messages=[
                {"role": "system", "content": self.system_prompt},
                *state.messages,
            ],
            registry=ctx.get_tools(self.tools),
            max_rounds=self.max_rounds,
            temperature=self.temperature,
        )
        data = _extract_json(response.text)
        if not data.get("accepted"):
            return HotelSignal.declined, HotelPatch(
                final_response=str(data.get("voice_reply") or response.text),
            )
        return HotelSignal.alternatives_ok, HotelPatch(
            selected_room_id=str(data.get("selected_room_id") or state.selected_room_id),
            check_in=str(data.get("check_in") or state.check_in),
            check_out=str(data.get("check_out") or state.check_out),
            total_price=float(data.get("total_price") or state.total_price),
            confirmation_pending=True,
            final_response=str(data.get("voice_reply") or response.text),
        )


class ConfirmationVertex(LlmStateVertex):
    """Read back the booking summary and wait for explicit approval."""

    model: Annotated[str, Field(
        json_schema_extra={"x-model-select": True},
    )] = "gemini-3.5-flash"

    system_prompt: Annotated[str, Field(
        json_schema_extra={"x-textarea": True},
    )] = (
        f"{PERSONA_HEADER}\n\n{TTS_CONSTRAINTS}\n\n"
        "Read back the full booking summary and ask for explicit confirmation. "
        'Respond JSON: {"confirmed": true/false, "voice_reply": "..."} '
        'Positive phrases include: yes, go ahead, confirmed, book it, please do.'
    )

    async def run(
        self, state: HotelState, ctx: Context
    ) -> tuple[HotelSignal, HotelPatch]:
        """Confirm or decline the booking based on guest reply."""
        summary = (
            f"Room {state.selected_room_id}, guest {state.guest_name}, "
            f"{state.check_in} to {state.check_out}, total €{state.total_price:.0f}."
        )
        response = await ctx.llm_for_model(self.model).achat(
            [
                {"role": "system", "content": self.system_prompt},
                *state.messages,
                {"role": "user", "content": summary},
            ],
            temperature=self.temperature,
        )
        data = _extract_json(response.text)
        confirmed = bool(data.get("confirmed"))
        voice = str(data.get("voice_reply") or response.text).strip()
        if confirmed:
            return HotelSignal.confirmed, HotelPatch(
                confirmation_pending=True,
                final_response=voice,
            )
        return HotelSignal.declined, HotelPatch(
            confirmation_pending=False,
            final_response=voice,
        )


class BookingExecutorVertex(StateVertex):
    """Create the reservation after confirmation — pure Python, no LLM."""

    async def run(
        self, state: HotelState, ctx: Context
    ) -> tuple[HotelSignal, HotelPatch]:
        """Persist the booking when confirmation_pending is set."""
        if not state.confirmation_pending:
            _logger.error("BookingExecutor called without confirmation_pending")
            return HotelSignal.declined, HotelPatch()
        try:
            reservation = _STORE.create_reservation(
                state.selected_room_id,
                state.guest_name,
                date.fromisoformat(state.check_in),
                date.fromisoformat(state.check_out),
            )
        except ValueError as exc:
            _logger.error("Booking failed: %s", exc)
            return HotelSignal.declined, HotelPatch(final_response=str(exc))
        room = _STORE.get_room(state.selected_room_id)
        message = (
            f"Booked {room.name} for {state.guest_name} "
            f"from {state.check_in} to {state.check_out}. "
            f"Total €{reservation.total_price:.0f}."
        )
        return HotelSignal.done, HotelPatch(
            reservation_id=reservation.reservation_id,
            final_response=message,
        )


class CancellationFlowVertex(LlmStateVertex):
    """Find, confirm, and cancel an existing reservation."""

    model: Annotated[str, Field(
        json_schema_extra={"x-model-select": True},
    )] = "gemini-3.5-flash"

    tools: Annotated[str, Field(description="Tool registry key.")] = "default"
    max_rounds: Annotated[int, Field(ge=1, le=10)] = 6

    system_prompt: Annotated[str, Field(
        json_schema_extra={"x-textarea": True},
    )] = (
        f"{PERSONA_HEADER}\n\n{TTS_CONSTRAINTS}\n\n{ASR_CONSTRAINTS}\n\n"
        "Find the reservation first, read back details, ask for explicit confirmation, "
        "then cancel only after approval. "
        'Respond JSON: {"cancelled": true/false, "reservation_id": "", "voice_reply": "..."}'
    )

    async def run(
        self, state: HotelState, ctx: Context
    ) -> tuple[HotelSignal, HotelPatch]:
        """Run find/cancel tool loop for cancellation requests."""
        response = await ctx.llm_for_model(self.model).achat_with_tools(
            messages=[
                {"role": "system", "content": self.system_prompt},
                *state.messages,
            ],
            registry=ctx.get_tools(self.tools),
            max_rounds=self.max_rounds,
            temperature=self.temperature,
        )
        data = _extract_json(response.text)
        voice = str(data.get("voice_reply") or response.text).strip()
        if data.get("cancelled"):
            return HotelSignal.done, HotelPatch(
                reservation_id=str(data.get("reservation_id") or ""),
                final_response=voice,
            )
        return HotelSignal.declined, HotelPatch(final_response=voice)


class InquiryVertex(LlmStateVertex):
    """Answer informational questions about rooms and availability."""

    model: Annotated[str, Field(
        json_schema_extra={"x-model-select": True},
    )] = "gpt-4o-mini"

    tools: Annotated[str, Field(description="Tool registry key.")] = "default"
    max_rounds: Annotated[int, Field(ge=1, le=10)] = 4

    system_prompt: Annotated[str, Field(
        json_schema_extra={"x-textarea": True},
    )] = (
        f"{PERSONA_HEADER}\n\n{TTS_CONSTRAINTS}\n\n"
        "Answer general questions about rooms, prices, and availability using tools."
    )

    async def run(
        self, state: HotelState, ctx: Context
    ) -> tuple[HotelSignal, HotelPatch]:
        """Answer an inquiry and finish."""
        response = await ctx.llm_for_model(self.model).achat_with_tools(
            messages=[
                {"role": "system", "content": self.system_prompt},
                *state.messages,
            ],
            registry=ctx.get_tools(self.tools),
            max_rounds=self.max_rounds,
            temperature=self.temperature,
        )
        return HotelSignal.done, HotelPatch(final_response=response.text.strip())


class OtherHandlerVertex(LlmStateVertex):
    """Remind off-topic guests of the assistant scope (max two reminders)."""

    model: Annotated[str, Field(
        json_schema_extra={"x-model-select": True},
    )] = "gpt-4o-mini"

    system_prompt: Annotated[str, Field(
        json_schema_extra={"x-textarea": True},
    )] = (
        f"{PERSONA_HEADER}\n\n{TTS_CONSTRAINTS}\n\n"
        "The guest has asked about something outside your role. "
        "Remind them briefly what you can help with: room bookings, cancellations, "
        "room information. Then ask how you may assist. Be friendly, never judgmental."
    )

    async def run(
        self, state: HotelState, ctx: Context
    ) -> tuple[HotelSignal, HotelPatch]:
        """Increment reminder count or end after the second reminder."""
        reminder_num = state.other_reminder_count + 1
        prompt = (
            f"{self.system_prompt}\n"
            f"This is reminder number {reminder_num} of 2.\n"
            "If this is reminder 2, say goodbye politely and end the conversation."
        )
        response = await ctx.llm_for_model(self.model).achat(
            [
                {"role": "system", "content": prompt},
                *state.messages,
            ],
            temperature=self.temperature,
        )
        voice = response.text.strip()
        if state.other_reminder_count < 1:
            return HotelSignal.reminder_sent, HotelPatch(
                other_reminder_count=reminder_num,
                final_response=voice,
            )
        return HotelSignal.done, HotelPatch(
            other_reminder_count=reminder_num,
            final_response=voice,
        )


class VoiceFormatterVertex(LlmStateVertex):
    """Format the final result as a warm TTS-ready voice reply."""

    model: Annotated[str, Field(
        json_schema_extra={"x-model-select": True},
    )] = "gemini-3.5-flash"

    system_prompt: Annotated[str, Field(
        json_schema_extra={"x-textarea": True},
    )] = (
        f"{PERSONA_HEADER}\n\n{TTS_CONSTRAINTS}\n\n"
        "Format the result in state.final_response as a warm, complete voice reply. "
        "Keep it natural."
    )

    async def run(
        self, state: HotelState, ctx: Context
    ) -> tuple[HotelSignal, HotelPatch]:
        """Polish final_response for voice output."""
        response = await ctx.llm_for_model(self.model).achat(
            [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": state.final_response or _last_user_content(state)},
            ],
            temperature=self.temperature,
        )
        return HotelSignal.done, HotelPatch(final_response=response.text.strip())
