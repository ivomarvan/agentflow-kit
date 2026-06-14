"""Shared base class and prompt utilities for Hotel Booking vertices.

Defines HotelBookingVertexBase (extends LlmStateVertex) which provides:
  - Standard prompt snippets (persona, TTS/ASR rules, data policy).
  - Room catalogue helper.
  - make_partial_order_schema(): dynamic Pydantic model for LLM-extracted fields.
  - build_messages(): combine accumulated history with a per-call instruction.
  - parse_llm_json(): safe JSON → Pydantic parsing with error fallback.
"""

from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

from pydantic import BaseModel, Field, ValidationError, create_model

from agentflow.statemachine import LlmStateVertex
from ..state import HotelBookingPatch, HotelBookingSignal, HotelBookingState, Order

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared prompt snippets
# All user-facing text stays in English here so the system prompt is uniform.
# Czech translations are in comments for reference.
# ---------------------------------------------------------------------------

PERSONA = (
    "You are Emma, a virtual receptionist at the Four Colours Hotel.\n"
    "Your role: help guests book rooms, cancel reservations, and answer questions about rooms.\n"
    "Always respond to guests in Czech (čeština) with a warm and professional tone.\n"
    # cs: Jste Emma, virtuální recepční hotelu Four Colours.
    # cs: Vaše role: pomáhat hostům s rezervací, zrušením a informacemi o pokojích.
    # cs: Vždy odpovídejte hostem česky, teplým a profesionálním tónem.
)

TTS_RULES = (
    "Respond as if speaking on the phone. "
    "Maximum two sentences per response. "
    "No bullet points, no URLs, no markdown, no special characters. "
    "Write all numbers and monetary amounts in words. "
    "Warm and professional tone."
    # cs: Odpovídejte jako při telefonním hovoru. Max. dvě věty.
    # cs: Žádné odrážky, URL, markdown ani speciální znaky.
    # cs: Čísla a peněžní částky pište slovy. Teplý a profesionální tón.
)

ASR_RULES = (
    "The user input may come from a speech recogniser. "
    "Parse dates and names flexibly "
    "(e.g. 'fourteenth of July', '14. 7.', '14. července', '14. 7. 2026'). "
    "If input is unclear, ask for clarification — up to three times, then escalate gracefully."
    # cs: Vstup může pocházet z ASR. Daty a jména parsujte flexibilně.
    # cs: Při nejasném vstupu žádejte opakování — max. 3×, pak zdvořile eskalujte.
)

DATA_POLICY = (
    "NEVER ask for information not required by the current task.\n"
    "Forbidden topics: phone number, e-mail, payment method, credit card, "
    "home address, nationality, loyalty card number, special requests.\n"
    "If the guest voluntarily mentions such data, acknowledge politely and ignore it."
    # cs: NIKDY se neptejte na informace, které nejsou součástí aktuálního úkolu.
    # cs: Zakázáno: telefon, email, platba, kreditní karta, adresa, národnost,
    # cs: číslo věrnostního programu, speciální požadavky.
    # cs: Pokud host tyto informace dobrovolně uvede, zdvořile je potvrďte a ignorujte je.
)

FORMAT_RULES = (
    "ALWAYS respond with a single valid JSON object matching the schema "
    "provided in the <output_schema> tag. "
    "No explanation, no markdown fences, no extra text outside the JSON."
    # cs: Vždy odpovídejte VÝHRADNĚ jako validní JSON odpovídající schématu.
    # cs: Žádné vysvětlování, markdown uvozovky ani text mimo JSON.
)


# ---------------------------------------------------------------------------
# Room catalogue helper
# ---------------------------------------------------------------------------

def get_room_catalogue_json() -> str:
    """Return the room catalogue as a JSON string for prompt injection.

    Returns:
        JSON array with id, name, capacity, price_per_night_eur for each room.
    """
    from ..live_state import _ROOM_CATALOGUE
    catalogue = [
        {"id": r[0], "name": r[1], "capacity": r[2], "price_per_night_eur": r[3]}
        for r in _ROOM_CATALOGUE
    ]
    return json.dumps(catalogue, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Dynamic schema builder  (Pattern: Factory Method)
# ---------------------------------------------------------------------------

# Field specifications used to build partial schemas.
# Only fields with empty/zero values in the current Order are included,
# so the schema shrinks as the guest fills in information.

_BOOKING_FIELD_SPECS: dict[str, tuple[type, Any]] = {
    "guest_name": (str, Field(default="", description="Full name of the guest.")),
    "check_in":   (str, Field(default="", description="Check-in date (YYYY-MM-DD).")),
    "check_out":  (str, Field(default="", description="Check-out date (YYYY-MM-DD).")),
    "capacity":   (int, Field(default=0, ge=0, le=3, description="Number of guests (1–3).")),
    "selected_room_id": (
        str,
        Field(
            default="",
            description="Room ID. Must be exactly one of: red, blue, green, white. Empty string if not yet chosen.",
            json_schema_extra={"enum": ["red", "blue", "green", "white", ""]},
        ),
    ),
}

_CANCELLATION_FIELD_SPECS: dict[str, tuple[type, Any]] = {
    "guest_name":     (str, Field(default="", description="Full name of the guest.")),
    "reservation_id": (str, Field(default="", description="Reservation UUID if known; leave empty if unknown.")),
    "check_in":       (str, Field(default="", description="Check-in date (YYYY-MM-DD) to identify the booking; leave empty if unknown.")),
}

# Type variable for the return type of make_partial_order_schema.
_M = TypeVar("_M", bound=BaseModel)


def make_partial_order_schema(
    order: Order,
    field_specs: dict[str, tuple[type, Any]],
) -> type[BaseModel]:
    """Build a dynamic Pydantic model containing only the unfilled Order fields.

    The returned model always includes:
      - user_question (str, required): TTS-ready text for the guest.
      - is_off_topic (bool, default False): True if the guest is asking
        something unrelated to the current flow.
    Only the Order fields whose current value is empty / zero are added so the
    schema shrinks as the conversation progresses, giving the LLM a precise
    list of what is still needed.

    Args:
        order:       Current Order state with partially filled fields.
        field_specs: Mapping of field_name → (type, FieldInfo) for the active
                     flow.  Use _BOOKING_FIELD_SPECS or _CANCELLATION_FIELD_SPECS.

    Returns:
        A freshly created Pydantic BaseModel subclass named "OrderUpdate".
    """
    definitions: dict[str, Any] = {
        "user_question": (
            str,
            Field(
                description=(
                    "TTS-ready question or statement for the guest. "
                    "Respond in Czech. Two sentences maximum."
                    # cs: Otázka nebo sdělení pro hosta, max. dvě věty, česky.
                ),
            ),
        ),
        "is_off_topic": (
            bool,
            Field(
                default=False,
                description=(
                    "Set True only if the guest is clearly asking about something "
                    "unrelated to hotel booking or room information."
                    # cs: True pokud se host ptá na něco nesouvisejícího s hotelem.
                ),
            ),
        ),
    }
    for field_name, (field_type, field_info) in field_specs.items():
        current_val = getattr(order, field_name, None)
        is_empty = current_val == "" or current_val == 0 or current_val is None
        if is_empty:
            definitions[field_name] = (field_type, field_info)
    return create_model("OrderUpdate", **definitions)


# ---------------------------------------------------------------------------
# Base vertex
# ---------------------------------------------------------------------------

class HotelBookingVertexBase(LlmStateVertex):
    """Base class for all Hotel Booking LLM vertices.

    Provides:
      - base_system_prompt(): combined persona + TTS + ASR + data policy + catalogue.
      - build_messages(): messages list for an achat() call.
      - parse_llm_json(): safe JSON → Pydantic with error fallback.

    Default model is gpt-4o-mini. Override per subclass when a different
    model is needed (e.g. model = "models/gemini-2.5-flash").
    """

    # Re-declare with a concrete default so all hotel booking vertices use
    # gpt-4o-mini unless the subclass or caller explicitly overrides it.
    model: str = "gpt-4o-mini"

    # ------------------------------------------------------------------
    # Prompt helpers
    # ------------------------------------------------------------------

    def base_system_prompt(self) -> str:
        """Return the combined system prompt shared by all hotel booking vertices.

        Returns:
            Multi-section prompt string.
        """
        return (
            f"<persona>\n{PERSONA}\n</persona>\n\n"
            f"<tts_rules>\n{TTS_RULES}\n</tts_rules>\n\n"
            f"<asr_rules>\n{ASR_RULES}\n</asr_rules>\n\n"
            f"<data_policy>\n{DATA_POLICY}\n</data_policy>\n\n"
            f"<format_rules>\n{FORMAT_RULES}\n</format_rules>\n\n"
            f"<room_catalogue>\n{get_room_catalogue_json()}\n</room_catalogue>"
        )

    def build_messages(
        self,
        state: HotelBookingState,
        extraction_prompt: str,
        extra_system: str = "",
    ) -> list[dict]:
        """Build the message list for an achat() call.

        Layout:
          [system: base + extra_system]
          [... state.messages (accumulated user/assistant history) ...]
          [user: extraction_prompt (instructs the LLM what to extract/respond)]

        The extraction_prompt is appended as a user-role message so it is
        treated as the current task rather than part of the conversation.

        Args:
            state:            Current graph state with message history.
            extraction_prompt: Instruction for the LLM for this specific call.
            extra_system:     Additional vertex-specific system instructions.

        Returns:
            Message list ready for achat().
        """
        system_content = self.base_system_prompt()
        if extra_system:
            system_content = f"{system_content}\n\n{extra_system}"
        msgs: list[dict] = [{"role": "system", "content": system_content}]
        msgs.extend(state.messages)
        msgs.append({"role": "user", "content": extraction_prompt})
        return msgs

    # ------------------------------------------------------------------
    # JSON parsing helper
    # ------------------------------------------------------------------

    def parse_llm_json(
        self,
        content: str | None,
        schema: type[BaseModel],
    ) -> BaseModel | None:
        """Parse a JSON string into a Pydantic model, returning None on failure.

        Args:
            content: JSON string returned by the LLM (may be None on error).
            schema:  Pydantic BaseModel subclass to validate against.

        Returns:
            Validated model instance, or None if parsing / validation failed.
        """
        if not content:
            logger.warning("parse_llm_json: empty content for schema=%s", schema.__name__)
            return None
        try:
            data = json.loads(content)
            return schema(**data)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            logger.warning(
                "parse_llm_json: failed for schema=%s  error=%s  content=%.80r",
                schema.__name__, exc, content,
            )
            return None

    # ------------------------------------------------------------------
    # Standard error patch (emits need_more_data with a fallback response)
    # ------------------------------------------------------------------

    @staticmethod
    def error_patch(msg: str = "Promiňte, nerozuměl jsem. Mohli byste to zopakovat?") -> HotelBookingPatch:
        # cs: Standardní chybová odpověď, pokud se nepodaří zpracovat výstup LLM.
        """Return a patch that asks the guest to repeat when LLM output is unparseable.

        Args:
            msg: Czech TTS-ready fallback message.

        Returns:
            HotelBookingPatch with the fallback message as final_response.
        """
        return HotelBookingPatch(
            messages=({"role": "assistant", "content": msg},),
            final_response=msg,
        )
