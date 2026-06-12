---
apm_category: task-spec
apm_ref: E010.T030
apm_level: task
created_by: Planner
model: claude-sonnet-4-6
intended_for: Coder
created_at: 2026-06-12
updated_at: 2026-06-12
---

# Task T030 — State Machine: HotelState, HotelPatch, HotelSignal, Vertices, and System Prompts

## Goal

Implement the complete agent state machine for the hotel booking assistant:
the dataclass state, patch, signal enum, all 13 vertices with their system prompts,
and unit tests for signal routing.

---

## Inputs

- [`../../../../assignment.en.md`](../../../../assignment.en.md) §4, §6 — full architecture spec
- [`../task-010-data-model/spec.md`](../task-010-data-model/spec.md) — `HotelBookState` fields
- [`../task-020-tools/spec.md`](../task-020-tools/spec.md) — tool names and signatures
- `examples/agents/06_smart_home.py` — reference for `State`, `Patch`, `Signal`, `Vertex` pattern
- `src/agentflow/statemachine/` — framework source (read-only)

---

## Outputs

### Files to create

- `examples/hotel_booking/state.py` — `HotelState`, `HotelPatch`, `HotelSignal`
- `examples/hotel_booking/vertices.py` — all 13 vertex classes + `SYSTEM_PROMPT_*` constants
- `tests/examples/hotel_booking/test_signal_routing.py` — signal routing unit tests

---

## `state.py` Specification

### `HotelState`

```python
@dataclass(frozen=True)
class HotelState:
    messages:             Annotated[tuple[dict, ...], operator.add] = field(default_factory=tuple)
    intent:               str = ""                # "NEW_BOOKING" | "CANCELLATION" | "INQUIRY" | "OTHER" | ""
    guest_name:           str = ""
    check_in:             str = ""                # ISO date string or ""
    check_out:            str = ""                # ISO date string or ""
    capacity:             int = 0
    selected_room_id:     str = ""
    total_price:          float = 0.0
    reservation_id:       str = ""                # filled after create_reservation
    alternatives:         tuple[dict, ...] = field(default_factory=tuple)
    confirmation_pending: bool = False
    other_reminder_count: int = 0
    final_response:       str = ""
```

### `HotelPatch`

```python
@dataclass(frozen=True)
class HotelPatch:
    """Partial update returned by a vertex. Only set fields that changed."""
    intent:               str | None = None
    guest_name:           str | None = None
    check_in:             str | None = None
    check_out:            str | None = None
    capacity:             int | None = None
    selected_room_id:     str | None = None
    total_price:          float | None = None
    reservation_id:       str | None = None
    alternatives:         tuple[dict, ...] | None = None
    confirmation_pending: bool | None = None
    other_reminder_count: int | None = None
    final_response:       str | None = None
```

### `HotelSignal`

```python
class HotelSignal(Signal):
    intent_new           = "intent_new"
    intent_cancel        = "intent_cancel"
    intent_inquiry       = "intent_inquiry"
    intent_other         = "intent_other"
    reminder_sent        = "reminder_sent"
    data_complete        = "data_complete"
    need_name            = "need_name"
    need_dates           = "need_dates"
    need_capacity        = "need_capacity"
    name_collected       = "name_collected"
    dates_collected      = "dates_collected"
    capacity_collected   = "capacity_collected"
    available            = "available"
    unavailable          = "unavailable"
    confirmed            = "confirmed"
    declined             = "declined"
    alternatives_ok      = "alternatives_ok"
    cancelled            = "cancelled"
    done                 = "done"
```

---

## `vertices.py` Specification

### Shared system prompt fragments

Define module-level string constants so they can be referenced (and tested) independently:

```python
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
```

### Vertex specifications

#### `IntentParserVertex`

- **Type:** LLM vertex (economy tier)
- **System prompt:** `PERSONA_HEADER + TTS_CONSTRAINTS + ASR_CONSTRAINTS`
  plus instruction to classify into exactly one of: `NEW_BOOKING`, `CANCELLATION`, `INQUIRY`, `OTHER`
  with 4 few-shot examples (one per intent, including an `OTHER` edge-case)
- **Output format:** JSON `{"intent": "NEW_BOOKING", "guest_name": "...", "check_in": "...", "check_out": "...", "capacity": N}`
  — fill any fields extractable from the message, leave others as `""` / `0`
- **Returns:** `HotelPatch(intent=..., guest_name=..., check_in=..., check_out=..., capacity=...)` + signal

| Parsed intent | Signal |
|---------------|--------|
| `NEW_BOOKING` | `HotelSignal.intent_new` |
| `CANCELLATION` | `HotelSignal.intent_cancel` |
| `INQUIRY` | `HotelSignal.intent_inquiry` |
| `OTHER` | `HotelSignal.intent_other` |

#### `DataDispatcherVertex`

- **Type:** pure Python (no LLM call)
- **Logic:**
  1. If `state.guest_name == ""` → `HotelSignal.need_name`
  2. Elif `state.check_in == "" or state.check_out == ""` → `HotelSignal.need_dates`
  3. Elif `state.capacity == 0` → `HotelSignal.need_capacity`
  4. Else → `HotelSignal.data_complete`
- **Returns:** `HotelPatch()` (no fields changed) + signal

#### `AskGuestNameVertex`

- **Type:** LLM vertex (economy tier)
- **System prompt:** `PERSONA_HEADER + TTS_CONSTRAINTS + ASR_CONSTRAINTS`
  plus: "Generate a short, voice-friendly question asking for the guest's name."
- **Extracts the answer** from the user's reply → `HotelPatch(guest_name=...)` + `HotelSignal.name_collected`

#### `AskDatesVertex`

- **Type:** LLM vertex (economy tier)
- **System prompt:** `PERSONA_HEADER + TTS_CONSTRAINTS + ASR_CONSTRAINTS`
  plus: "Generate a question for check-in and check-out dates. Parse the answer flexibly."
  Include 3 few-shot date-parsing examples.
- **Extracts:** `HotelPatch(check_in=..., check_out=...)` + `HotelSignal.dates_collected`

#### `AskCapacityVertex`

- **Type:** LLM vertex (economy tier)
- **System prompt:** `PERSONA_HEADER + TTS_CONSTRAINTS + ASR_CONSTRAINTS`
  plus: "Generate a question for the number of guests."
- **Extracts:** `HotelPatch(capacity=N)` + `HotelSignal.capacity_collected`

#### `AvailabilityCheckerVertex`

- **Type:** LLM vertex (economy tier) with tools: `CheckAvailabilityTool`, `GetRoomDetailsTool`, `CalculatePriceTool`
- **System prompt:** `PERSONA_HEADER + TTS_CONSTRAINTS`
  plus: "Check room availability and select the best matching room. Set selected_room_id and total_price."
- **Returns:**
  - If rooms found: `HotelPatch(selected_room_id=..., total_price=..., confirmation_pending=True)` + `HotelSignal.available`
  - If not: `HotelSignal.unavailable`

#### `AlternativesVertex`

- **Type:** LLM vertex (economy tier) with tool: `FindAlternativesTool`
- **System prompt:** `PERSONA_HEADER + TTS_CONSTRAINTS`
  plus: "Present the alternatives voice-friendlily. Ask the guest to choose."
- **On guest selection:** `HotelPatch(selected_room_id=..., check_in=..., check_out=..., total_price=..., confirmation_pending=True)` + `HotelSignal.alternatives_ok`
- **If guest declines:** `HotelSignal.declined`

#### `ConfirmationVertex`

- **Type:** LLM vertex (**quality tier**)
- **System prompt:** `PERSONA_HEADER + TTS_CONSTRAINTS`
  plus: "Read back the full booking summary. Ask for explicit confirmation. Reply with JSON: {confirmed: true/false}."
  Positive examples of confirmation phrases: "yes", "go ahead", "confirmed", "book it", "please do".
- **Returns:**
  - `confirmed=true`: `HotelPatch(confirmation_pending=True)` + `HotelSignal.confirmed`
  - `confirmed=false`: `HotelPatch(confirmation_pending=False)` + `HotelSignal.declined`

#### `BookingExecutorVertex`

- **Type:** pure Python (no LLM)
- **Action:** Call `_STORE.create_reservation(state.selected_room_id, state.guest_name, state.check_in, state.check_out)`
- **Guard:** if `not state.confirmation_pending`, log error and emit `HotelSignal.declined`
- **Returns:** `HotelPatch(reservation_id=..., final_response=...)` + `HotelSignal.done`

#### `CancellationFlowVertex`

- **Type:** LLM vertex (**quality tier**) with tools: `FindReservationTool`, `CancelReservationTool`
- **System prompt:** `PERSONA_HEADER + TTS_CONSTRAINTS + ASR_CONSTRAINTS`
  plus: "Find the reservation first. Read back the details. Ask for explicit confirmation. Only then cancel."
- **Returns:** `HotelPatch(final_response=..., reservation_id=...)` + `HotelSignal.done`
  (or `HotelSignal.declined` if not confirmed)

#### `InquiryVertex`

- **Type:** LLM vertex (economy tier) with tools: `GetRoomDetailsTool`, `CheckAvailabilityTool`
- **System prompt:** `PERSONA_HEADER + TTS_CONSTRAINTS`
  plus: "Answer general questions about rooms, prices, and availability."
- **Returns:** `HotelPatch(final_response=...)` + `HotelSignal.done`

#### `OtherHandlerVertex`

- **Type:** LLM vertex (economy tier)
- **System prompt:** `PERSONA_HEADER + TTS_CONSTRAINTS`
  plus:
  ```
  The guest has asked about something outside your role.
  Remind them briefly what you can help with: room bookings, cancellations, room information.
  Then ask how you may assist. Be friendly, never judgmental.
  This is reminder #{{other_reminder_count + 1}} of 2.
  If this is reminder #2, say goodbye politely and end the conversation.
  ```
- **Returns:**
  - If `state.other_reminder_count < 2`: `HotelPatch(other_reminder_count=state.other_reminder_count + 1)` + `HotelSignal.reminder_sent`
  - If `state.other_reminder_count >= 2`: `HotelPatch(final_response=...)` + `HotelSignal.done`

#### `VoiceFormatterVertex`

- **Type:** LLM vertex (**quality tier**)
- **System prompt:** `PERSONA_HEADER + TTS_CONSTRAINTS`
  plus: "Format the result in state.final_response as a warm, complete voice reply. Keep it natural."
- **Returns:** `HotelPatch(final_response=...)` + `HotelSignal.done` → StdEnd

---

## Context Bundle

### Do NOT modify
- `agentflow/` framework source
- `examples/hotel_booking/live_state.py`, `booking_store.py`, `tools.py`
- `doc/**` other than this task's `dod.md` / `report.md`

### Read
- `examples/hotel_booking/live_state.py`, `booking_store.py`, `tools.py`
- `examples/agents/06_smart_home.py` — `Vertex`, `State`, `Patch`, `Signal` pattern
- `src/agentflow/statemachine/vertex.py` — base class
- `src/agentflow/statemachine/signal.py` — `Signal` base

---

## Dependencies

- T010 and T020 must be complete.

---

## Test Specification

File: `tests/examples/hotel_booking/test_signal_routing.py`

Test `DataDispatcherVertex` in isolation (pure Python — no LLM mock needed):

| Test | Scenario |
|------|----------|
| `test_dispatcher_all_missing_routes_need_name` | Empty state → `HotelSignal.need_name` |
| `test_dispatcher_name_present_routes_need_dates` | `guest_name="Brown"`, dates empty → `HotelSignal.need_dates` |
| `test_dispatcher_dates_present_routes_need_capacity` | name+dates set, capacity=0 → `HotelSignal.need_capacity` |
| `test_dispatcher_all_present_routes_data_complete` | All fields set → `HotelSignal.data_complete` |

Also test `OtherHandlerVertex.run()` routing by patching the LLM call:

| Test | Scenario |
|------|----------|
| `test_other_handler_first_reminder_increments_count` | `other_reminder_count=0` → signal `reminder_sent`, count=1 |
| `test_other_handler_second_reminder_routes_done` | `other_reminder_count=1` → signal `done` |

---

## Definition of Done

See `dod.md` in this directory.
