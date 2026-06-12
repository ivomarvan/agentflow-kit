# Hotel Booking Voice Assistant — Project Specification

> **Status:** Approved for implementation (2026-06-12).
> Legacy prototype preserved in `examples/hotel_booking_bak/`.
>
> **Language policy:** All code, system prompts, comments, and documentation are in English.
> The LLM naturally responds in the user's language — no explicit language switching needed.

---

## 1. Goal

Build a **production-quality educational example of a hotel booking voice assistant**
using the `agentflow` framework.

The example demonstrates:
- Multi-turn conversation managed by an explicit state machine
- A complete **booking workflow**: validation, conflict detection, alternatives, and confirmation
- Protection against off-topic input: intent `OTHER` → friendly reminder of the assistant's purpose
- **Hub-and-spoke data collection**: multiple dedicated vertices instead of one iterative loop
  (cleaner state graph, easier to debug and explain)
- **Live State panel** rendered as a hotel guest book (custom Vue component, calendar view)
- Best-practice prompt engineering applied throughout (see Section 9)

---

## 2. Hotel Data Model

### 2.1 Rooms

| ID      | Name        | Beds | Price / night |
|---------|-------------|-----:|-------------:|
| `red`   | Red Room    |    3 |         €120 |
| `blue`  | Blue Room   |    2 |          €85 |
| `green` | Green Room  |    2 |          €85 |
| `white` | White Room  |    1 |          €55 |

### 2.2 Reservation record

Fields: `reservation_id` (auto), `room_id`, `guest_name`, `check_in` (`YYYY-MM-DD`),
`check_out` (`YYYY-MM-DD`), `total_price` (computed: nights × price_per_night).

### 2.3 Seed data (pre-filled at startup)

| Room  | Guest           | Check-in   | Check-out  |
|-------|-----------------|------------|------------|
| Red   | Novak family    | 2026-07-10 | 2026-07-14 |
| Blue  | Jana Dvorakova  | 2026-07-08 | 2026-07-11 |
| Blue  | Peter Schmidt   | 2026-07-15 | 2026-07-18 |
| Green | Marie Horakova  | 2026-07-12 | 2026-07-15 |
| White | Tomas Vesely    | 2026-07-09 | 2026-07-10 |

---

## 3. Live State — Hotel Guest Book (GUI panel)

A custom Vue component (`HotelBookPanel.vue`) renders the booking state as a
**room × date matrix** (hotel guest book style).

```
         │ Jul 8│ Jul 9│Jul 10│Jul 11│Jul 12│Jul 13│Jul 14│Jul 15│Jul 16│Jul 17│
─────────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┤
Red Room │      │      │Novak │Novak │Novak │Novak │      │      │      │      │
Blue Room│Dvora │Dvora │Dvora │      │      │      │Schmi │Schmi │Schmi │      │
Green Rm │      │      │      │      │Horak │Horak │Horak │      │      │      │
White Rm │Vesel │      │      │      │      │      │      │      │      │      │
```

**Display rules:**
- **Columns (days):** only days that have at least one reservation; range = `min(check_in) − 1` to `max(check_out) + 1`
- **Rows (rooms):** always all four rooms, fixed order
- **Cell:** guest name truncated to ~5 chars; empty = available
- **Row header:** room name + bed icon + price (`🛏 Red Room · 3 beds · €120/night`)
- **Highlight:** newly created or cancelled cells flash amber (same mechanism as SmartHome)
- **Implementation:** standalone `HotelBookPanel.vue` — not an extension of `StateViewerPanel.vue`

### 3.1 Pydantic Live State model

```python
class Reservation(BaseModel):
    model_config = ConfigDict(frozen=False)
    reservation_id: str
    guest_name: str
    check_in: date
    check_out: date
    total_price: float

class RoomState(BaseModel):
    model_config = ConfigDict(frozen=False)
    room_id: str
    name: str
    capacity: int
    price_per_night: float
    reservations: list[Reservation] = Field(default_factory=list)

class HotelBookState(BaseModel):
    """Live state model — mutated by tools, observed by GUI Live State panel."""
    model_config = ConfigDict(frozen=False)
    rooms: list[RoomState]
    last_action: str = ""   # human-readable summary of the last mutation
```

---

## 4. Agent Architecture (state machine)

### 4.1 Vertex overview

```
                    ┌──────────────────────┐
                    │  IntentParserVertex   │
                    │  → NEW_BOOKING        │
                    │  → CANCELLATION       │
                    │  → INQUIRY            │
                    │  → OTHER              │  ← off-topic guard
                    └──────┬───────────────┘
       ┌───────────────────┼──────────────┬──────────────┐
       ▼                   ▼              ▼               ▼
DataDispatcherVertex  CancellationFlow InquiryVertex OtherHandler
       │               Vertex           (→ StdEnd)    Vertex
       │                                               │
  ┌────┴────────────────────┐               reminder_sent │
  │  What's still missing?  │           ┌───────────────┘
  ▼                         │           ▼
AskGuestNameVertex ─────────┤       IntentParserVertex
AskDatesVertex ─────────────┤
AskCapacityVertex ──────────┘
       │ data_complete
       ▼
AvailabilityCheckerVertex   ← calls tools
       │
   ┌───┴───┐
 free   occupied
   │         │
   ▼         ▼
Confirmation  AlternativesVertex
Vertex              │
   │ confirmed       │ alternatives_ok
   ▼                ▼
BookingExecutorVertex ←─────┘
   │
   ▼
VoiceFormatterVertex → StdEnd
```

### 4.2 Vertex responsibilities

| Vertex | Responsibility | LLM tier |
|--------|---------------|----------|
| `IntentParserVertex` | Classify intent into `NEW_BOOKING \| CANCELLATION \| INQUIRY \| OTHER` | economy |
| `DataDispatcherVertex` | Check which required fields are missing; route to the right "ask" vertex | no LLM (pure Python) |
| `AskGuestNameVertex` | Generate a voice-friendly question for the guest's name | economy |
| `AskDatesVertex` | Generate a question for check-in / check-out dates | economy |
| `AskCapacityVertex` | Generate a question for the number of guests | economy |
| `AvailabilityCheckerVertex` | Call `check_availability` + `get_room_details` tools | economy |
| `AlternativesVertex` | Call `find_alternatives` + present options to guest | economy |
| `ConfirmationVertex` | Summarise the booking and wait for explicit approval | quality |
| `BookingExecutorVertex` | Call `create_reservation` after confirmed | no LLM (pure Python) |
| `CancellationFlowVertex` | Find reservation, summarise, confirm, call `cancel_reservation` | quality |
| `InquiryVertex` | Answer informational questions about rooms and availability | economy |
| `OtherHandlerVertex` | Remind guest of the assistant's purpose; max 2 reminders | economy |
| `VoiceFormatterVertex` | Convert the final result into a TTS-ready voice reply | quality |

### 4.3 Tools

| Tool name             | Description                                          |
|-----------------------|------------------------------------------------------|
| `check_availability`  | Returns available rooms for given dates and capacity |
| `get_room_details`    | Returns room name, capacity, price                   |
| `calculate_price`     | Computes total stay cost (nights × rate)             |
| `create_reservation`  | Writes a reservation (only after confirmation guard) |
| `cancel_reservation`  | Removes a reservation by ID or name+date             |
| `find_reservation`    | Looks up a reservation by name / date / ID           |
| `find_alternatives`   | Returns alternative rooms or dates on conflict       |

### 4.4 Signals

```python
class HotelSignal(Signal):
    intent_new           = "intent_new"           # → DataDispatcherVertex
    intent_cancel        = "intent_cancel"         # → CancellationFlowVertex
    intent_inquiry       = "intent_inquiry"        # → InquiryVertex
    intent_other         = "intent_other"          # → OtherHandlerVertex
    reminder_sent        = "reminder_sent"         # → IntentParserVertex
    data_complete        = "data_complete"         # → AvailabilityCheckerVertex
    need_name            = "need_name"             # → AskGuestNameVertex
    need_dates           = "need_dates"            # → AskDatesVertex
    need_capacity        = "need_capacity"         # → AskCapacityVertex
    name_collected       = "name_collected"        # → DataDispatcherVertex
    dates_collected      = "dates_collected"       # → DataDispatcherVertex
    capacity_collected   = "capacity_collected"    # → DataDispatcherVertex
    available            = "available"             # → ConfirmationVertex
    unavailable          = "unavailable"           # → AlternativesVertex
    confirmed            = "confirmed"             # → BookingExecutorVertex
    declined             = "declined"              # → StdEnd
    alternatives_ok      = "alternatives_ok"       # → ConfirmationVertex
    cancelled            = "cancelled"             # → VoiceFormatterVertex
    done                 = "done"                  # → StdEnd
```

---

## 5. Booking Rules

- **Overlap check:** `new_check_in < existing_check_out AND new_check_out > existing_check_in`
- `check_out` is the departure day — the room is free from that morning; a new guest may check in the same day
- `check_in >= today`; stay length: 1–30 nights
- **On conflict:** offer (1) same capacity room ±3 days, (2) different room same capacity same dates
- **Cancellation:** identified by guest name + check-in date or `reservation_id`; confirmation required
- **Confirmation guard:** `create_reservation` / `cancel_reservation` reject silently if `confirmation_pending != True` on the context — double-safety outside the LLM

---

## 6. Communication Protocol

### 6.1 Confirmation pattern (critical)

Before calling any write tool:
1. Read back all key details verbally (room name, guest, dates, total price)
2. Ask explicitly for approval ("Shall I confirm this booking?")
3. Wait for an explicit "yes" / "confirmed" / "go ahead"
4. Only then call the tool

### 6.2 Voice (TTS) output constraints

System prompt instruction added to every LLM vertex:

```
<tts_constraints>
Reply as if speaking on the phone. Maximum two sentences per turn.
No markdown, bullet points, URLs, or special formatting.
Write all numbers and amounts in words ("three hundred forty euros", "July tenth").
Use natural language with a warm and professional tone.
</tts_constraints>
```

### 6.3 ASR input tolerance

```
<asr_constraints>
The user's text may come from a speech recogniser and contain phonetic errors
or informal phrasing (e.g. "fourteenth of july", "jul 14", "14.7.").
Parse dates flexibly. If you cannot understand the input, say:
"Sorry, I didn't catch that. Could you repeat?" (max 3 attempts, then hand-off).
</asr_constraints>
```

### 6.4 Identity and persona

System prompt header for every vertex:

```
You are Emma, a virtual receptionist for the Four Colours Hotel.
Your role: help guests book rooms, cancel reservations, and answer room questions.
You are an AI assistant — never claim to be a human.
```

### 6.5 Off-topic (OTHER) handling

`OtherHandlerVertex` system prompt:

```
The guest has gone off-topic. Gently remind them what you can help with:
room bookings, cancellations, and room information.
Ask how you may help. Maximum 2 reminders; after the second, say goodbye politely.
```

---

## 7. Sample Agent State

```python
@dataclass(frozen=True)
class HotelState:
    messages:              Annotated[tuple[dict, ...], operator.add] = field(default_factory=tuple)
    intent:                str = ""
    guest_name:            str = ""
    check_in:              str = ""   # ISO date string
    check_out:             str = ""
    capacity:              int = 0
    selected_room_id:      str = ""
    total_price:           float = 0.0
    reservation_id:        str = ""   # set after create_reservation
    alternatives:          tuple[dict, ...] = field(default_factory=tuple)
    confirmation_pending:  bool = False
    other_reminder_count:  int = 0
    final_response:        str = ""
```

---

## 8. Test Scenarios

```
[Happy path — new booking]
User: Book a room for two from July 15 to 18, name Schmidt.
→ Blue or Green room selected, €255 total, confirmed, written to _HOTEL.

[Conflict — alternative offered]
User: Book the Blue Room from July 8 to 10 for Brown.
→ Conflict (Dvorakova 8–11). Offer: Green Room same dates OR Blue Room from Jul 11.

[Cancellation]
User: Cancel the reservation for Novak family arriving July 10.
→ Find Red Room / Novak 10–14 Jul, show summary, wait for confirmation.

[Off-topic]
User: What's the weather today?
→ Emma: "I can only help with room bookings and reservations. How may I assist you?"
   (max 2 times, then polite goodbye)

[ASR error]
User: i want a room from fourteenth to seventeeth of july for mister horak
→ Parser normalises to 2026-07-14 – 2026-07-17, continues.
```

---

## 9. Prompt Engineering Principles Applied (from course)

### 9.1 Basic techniques (ch. 02)
- **Role/Persona:** Emma has a name, role, and boundaries in every system prompt
- **XML delimiters:** `<tts_constraints>`, `<asr_constraints>`, `<hotel_info>` separate instruction types
- **Positive instructions:** "call the tool ONLY after explicit approval" not "don't call without approval"
- **Output format:** every LLM vertex specifies its expected output format (intent enum, voice text, JSON)

### 9.2 Conversational AI and voicebots (ch. 09) — most relevant chapter
- **TTS constraints:** 2 sentences, numbers as words, no markdown — in every vertex system prompt
- **ASR tolerance:** repair pattern and 3-strike rule — in DataDispatcher and every "ask" vertex
- **Confirmation pattern:** dedicated `ConfirmationVertex` + guard inside the tool
- **Persona:** Emma's identity declared once, referenced everywhere via a shared prompt header
- **Error fallback:** 3 misunderstandings → hand-off; off-topic → `OtherHandlerVertex`

### 9.3 Decomposition and chaining (ch. 05)
- Sequential pipeline: Intent → DataDispatch → Availability → Confirm → Execute → Format
- Hub-and-spoke for data collection: DataDispatcher routes to the right "ask" vertex
- `BookingExecutorVertex` and `DataDispatcherVertex` are pure Python (no LLM) — faster, cheaper

### 9.4 Structured outputs (ch. 04)
- Tool parameters are Pydantic models (guaranteed JSON structure)
- `IntentParserVertex` returns an enum value, not free text
- `AvailabilityCheckerVertex` returns a structured list

### 9.5 Few-shot examples (ch. 03)
- `DataDispatcherVertex` prompt: 2–3 examples of date formats (spoken, numeric, ISO)
- `IntentParserVertex` prompt: edge-case examples (mixed intents, partial off-topic)

### 9.6 What we deliberately skip
- **Explicit CoT prompts:** reasoning models handle this internally; explicit CoT increases voice latency
- **Self-consistency:** overkill for a deterministic booking task
