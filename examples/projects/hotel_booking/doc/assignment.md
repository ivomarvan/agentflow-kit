# Hotel Booking Voice Assistant — Project Specification

> **Status:** Implemented (v1.0, June 2026). First working version;
> further development planned.  
> Legacy prototype preserved in `examples/hotel_booking_bak/`.
>
> **Language policy:** All code, system prompts, comments, and documentation are in English.
> The LLM responds in the user's language (Czech) automatically — no explicit
> language-switching code needed.

---

## 1. Goal

Build a **production-quality educational example of a hotel booking voice assistant**
using the `agentflow` framework.

The example demonstrates:
- Multi-turn conversation managed by an explicit state machine
- A complete **booking workflow**: data collection, availability check, and confirmation
- A complete **cancellation workflow**: reservation lookup, confirmation, and execution
- **Room inquiry** handling: answering questions about rooms via tool calls
- Protection against off-topic input: intent `OTHER` → friendly reminder of the assistant's purpose
- **Dynamic Pydantic schema** (`pydantic.create_model()`) for LLM structured output that
  shrinks as the conversation progresses
- **LiveModel** panel rendered as a hotel guest book (custom Vue component)
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

### 2.2 Order (booking request)

The `Order` Pydantic model accumulates booking data across turns:

```python
class Order(BaseModel):
    model_config = ConfigDict(frozen=True)
    action: Literal["booking", "cancellation", ""] = Field(default="", ...)
    room_id: str = Field(default="", description="Room ID: red | blue | green | white")
    guest_name: str = Field(default="", description="Guest full name")
    check_in: str = Field(default="", description="Check-in date YYYY-MM-DD")
    check_out: str = Field(default="", description="Check-out date YYYY-MM-DD")
    capacity: int = Field(default=0, description="Number of guests (1–3)")
    reservation_id: str = Field(default="", description="Reservation ID (for cancellation)")
```

### 2.3 Reservation record (in `BookingStore`)

Fields: `reservation_id` (auto UUID), `room_id`, `guest_name`, `check_in` (`YYYY-MM-DD`),
`check_out` (`YYYY-MM-DD`), `total_price` (computed: nights × price_per_night).

### 2.4 Seed data (pre-filled at startup)

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
- **Columns (days):** only days that have at least one reservation; range = `min(check_in)` to `max(check_out)`
- **Rows (rooms):** always all four rooms, fixed order
- **Cell:** guest name truncated to ~5 chars; empty = available
- **Row background:** tinted with the room's name colour (red → light red, etc.)
- **Implementation:** standalone `HotelBookPanel.vue` — not an extension of `StateViewerPanel.vue`

### 3.1 Pydantic Live State model

```python
class Reservation(BaseModel):
    reservation_id: str
    guest_name: str
    check_in: date
    check_out: date
    total_price: float

class RoomState(BaseModel):
    room_id: str
    name: str
    capacity: int
    price_per_night: float
    reservations: list[Reservation] = Field(default_factory=list)

class HotelBookState(BaseModel):
    """Live state model — mutated by tools, observed by GUI Live State panel."""
    rooms: list[RoomState]
    last_action: str = ""   # human-readable summary of the last mutation
```

---

## 4. Agent Architecture (state machine)

### 4.1 Vertex overview

```
                    ┌──────────────────────┐
                    │  OrderDirectionVertex │  ← every turn starts here
                    └──────┬───────────────┘
       ┌────────────────────┼────────────────┬────────────────┐
       ▼                    ▼                ▼                ▼
OrderDetailsVertex  CancellationDetails  InquiryVertex  OtherHandlerVertex
(booking data)      Vertex (cancel data) (tool calls)   (off-topic guard)
       │ data_complete      │ data_complete    │ done           │ done
       ▼                    ▼                  ▼               ▼
AvailabilityVertex  ExecuteCancellation      StdEnd          StdEnd
       │ available   Vertex (no LLM)
       ▼                    │ done
OrderConfirmation           ▼
Vertex              StdEnd
       │ confirmed
       ▼
ExecuteBookingVertex
(no LLM)
       │ done
       ▼
     StdEnd
```

`OrderDirectionVertex` also routes directly to `OrderConfirmationVertex` when
`flow == "awaiting_confirmation"` (no LLM call needed).

### 4.2 Vertex responsibilities

| Vertex | Responsibility | Type |
|--------|---------------|------|
| `OrderDirectionVertex` | Detect intent (booking / cancellation / inquiry / other) and extract partial data | `LlmStateVertex` |
| `OrderDetailsVertex` | Collect all missing booking fields iteratively in a single vertex | `LlmStateVertex` |
| `CancellationDetailsVertex` | Collect guest name / reservation ID for cancellation | `LlmStateVertex` |
| `AvailabilityVertex` | Check room availability, compute price | `StateVertex` (no LLM) |
| `OrderConfirmationVertex` | Present booking summary, collect explicit "yes/no" | `LlmStateVertex` |
| `ExecuteBookingVertex` | Call `BookingStore.create_reservation()` | `StateVertex` (no LLM) |
| `ExecuteCancellationVertex` | Call `BookingStore.cancel_reservation()` | `StateVertex` (no LLM) |
| `InquiryVertex` | Answer informational questions using tools | `LlmStateVertex` |
| `OtherHandlerVertex` | Remind guest of the assistant's purpose | `LlmStateVertex` |

### 4.3 Tools

| Tool | Description |
|------|-------------|
| `CheckAvailabilityTool` | Returns rooms available for given dates and capacity |
| `GetRoomDetailsTool` | Returns room name, capacity, and price |
| `CalculatePriceTool` | Computes total stay cost (nights × rate) |
| `CreateReservationTool` | Writes a reservation to `BookingStore` |
| `CancelReservationTool` | Removes a reservation by name + check-in or ID |
| `FindReservationTool` | Looks up a reservation by name / date / ID |
| `FindAlternativesTool` | Returns alternative rooms or dates on conflict |

### 4.4 Signals

```python
class HotelBookingSignal(Signal):
    order_request          # → OrderDetailsVertex (new booking flow)
    order_cancellation     # → CancellationDetailsVertex
    order_inquiry          # → InquiryVertex
    order_other            # → OtherHandlerVertex (off-topic)
    awaiting_confirmation  # → OrderConfirmationVertex (flow shortcut)
    need_more_data         # → StdEnd (wait for next user turn)
    data_complete          # → AvailabilityVertex / ExecuteCancellationVertex
    available              # → OrderConfirmationVertex
    unavailable            # → StdEnd (guest informed; AlternativesVertex planned)
    confirmed              # → ExecuteBookingVertex
    declined               # → StdEnd
    done                   # → StdEnd (operation completed)
    fail                   # → StdEnd (unrecoverable error)
```

---

## 5. Booking Rules

- **Overlap check:** `new_check_in < existing_check_out AND new_check_out > existing_check_in`
- `check_out` is the departure day — the room is free from that morning; a new guest may
  check in on the same day as a prior guest's `check_out`
- `check_in >= today`; stay length: 1–30 nights
- **On conflict:** the guest is currently informed and the flow ends; an `AlternativesVertex`
  is planned for a future iteration
- **Cancellation:** identified by guest name + check-in date or `reservation_id`; explicit
  confirmation required before the booking is deleted
- **Order reset:** after every successful booking or cancellation `order=Order()` and
  `flow="initial"` are written to the patch — the next turn starts clean

---

## 6. Communication Protocol

### 6.1 Fields collected for booking

The assistant asks **only** for the fields defined in the `Order` model:

| Field | Description |
|-------|-------------|
| `room_id` | Which room (`red`, `blue`, `green`, or `white`) |
| `guest_name` | Guest's full name |
| `check_in` | Arrival date (ISO `YYYY-MM-DD`) |
| `check_out` | Departure date (ISO `YYYY-MM-DD`) |
| `capacity` | Number of guests (1–3) |

No other personal data (phone, email, payment method) is requested or stored.

### 6.2 Confirmation pattern (critical)

Before calling any write tool:
1. Read back all key details verbally (room name, guest, dates, total price)
2. Ask explicitly for approval ("Shall I confirm this booking?")
3. Wait for an explicit "yes" / "confirmed" / "go ahead"
4. Only then call the tool

### 6.3 Voice (TTS) output constraints

System prompt instruction added to every LLM vertex:

```
Reply as if speaking on the phone. Maximum two sentences per turn.
No markdown, bullet points, URLs, or special formatting.
Write all numbers and amounts in words ("three hundred forty euros", "July tenth").
Use natural language with a warm and professional tone.
```

### 6.4 ASR input tolerance

```
The user's text may come from a speech recogniser and contain phonetic errors
or informal phrasing (e.g. "fourteenth of july", "jul 14", "14.7.").
Parse dates flexibly.
```

### 6.5 Identity and persona

System prompt header for every vertex:

```
You are Emma, a virtual receptionist for the Four Colours Hotel.
Your role: help guests book rooms, cancel reservations, and answer room questions.
You are an AI assistant — never claim to be a human.
```

### 6.6 Off-topic (OTHER) handling

`OtherHandlerVertex` gently redirects the guest back to room bookings, cancellations,
and room information.  After two off-topic exchanges the assistant says goodbye.

---

## 7. State Definitions

### Agent state

```python
@dataclass(frozen=True)
class HotelBookingState:
    messages:       Annotated[tuple[dict, ...], operator.add] = ()
    order:          Order     = field(default_factory=Order)
    flow:           str       = "initial"  # "initial" | "booking" | "cancellation" | "awaiting_confirmation"
    final_response: str       = ""
```

### Patch

```python
@dataclass
class HotelBookingPatch:
    messages:       tuple[dict, ...] | UNSET_TYPE = UNSET
    order:          Order            | UNSET_TYPE = UNSET
    flow:           str              | UNSET_TYPE = UNSET
    final_response: str              | UNSET_TYPE = UNSET
```

---

## 8. Test Scenarios

```
[Happy path — new booking]
User: Chtěl bych červený pokoj na 15–18 července, jsem Ivo.
→ data collected across turns → Red Room available → 360 EUR confirmed → reservation created.

[Cancellation]
User: Zrušte prosím rezervaci rodiny Novák od 10. července.
→ Novak family / Red / Jul 10–14 found → summary shown → confirmed → cancelled.

[Room inquiry]
User: Je zelený pokoj v červenci volný?
→ InquiryVertex calls CheckAvailabilityTool → answers with available periods.

[Off-topic]
User: Jaké je dnes počasí?
→ OtherHandlerVertex: "Mohu vám pomoci s rezervací nebo informacemi o pokojích."
   (max 2 times, then polite goodbye)

[Unavailable room]
User: Chci modrý pokoj od 8. do 11. července.
→ AvailabilityVertex: unavailable (Dvorakova conflict) → guest informed → StdEnd.
   (AlternativesVertex planned for future version)
```

---

## 9. Prompt Engineering Principles Applied (from course)

### 9.1 Basic techniques (ch. 02)
- **Role/Persona:** Emma has a name, role, and boundaries in every system prompt
- **XML delimiters:** `<tts_rules>`, `<asr_rules>`, `<data_policy>` separate instruction types
- **Positive instructions:** "call the tool ONLY after explicit approval"
- **Output format:** every LLM vertex specifies `response_schema` (Pydantic model)

### 9.2 Conversational AI and voicebots (ch. 09) — most relevant chapter
- **TTS constraints:** 2 sentences, numbers as words, no markdown — in every vertex system prompt
- **ASR tolerance:** flexible date parsing — in `OrderDetailsVertex` and `CancellationDetailsVertex`
- **Confirmation pattern:** dedicated `OrderConfirmationVertex` before any write operation
- **Persona:** Emma's identity declared in a shared `PERSONA` constant in `vertices/_base.py`

### 9.3 Decomposition and chaining (ch. 05)
- Sequential pipeline: Intent → DataCollection → Availability → Confirm → Execute
- `AvailabilityVertex` and `ExecuteBookingVertex` are pure Python (`StateVertex`) — faster, cheaper

### 9.4 Structured outputs (ch. 04)
- Tool parameters defined as `@param_desc`-annotated methods → JSON schema generated automatically
- Every LLM vertex uses `response_schema=` with `pydantic.create_model()` for structured output
- `OrderDirectionVertex` returns an enum-constrained field, not free text

### 9.5 Dynamic schema (ch. 04, advanced)
- `make_partial_order_schema()` builds a schema with **only unfilled** `Order` fields per turn
- The schema shrinks as the conversation progresses, saving tokens and preventing overwriting

### 9.6 What we deliberately skip in this version
- **Alternative suggestions on conflict:** planned for v2
- **Message history summarisation:** full history is passed each turn; not an issue for short demos
- **Explicit CoT prompts:** reasoning models handle this internally; explicit CoT adds voice latency

---

## 10. Known Limitations and Future Work

| Issue | Status |
|-------|--------|
| `unavailable` path ends the conversation — no alternatives offered | Planned for v2 |
| Message history grows unbounded across many turns | Planned: sliding window / summary |
| `BookingStore` is in-memory — data lost on restart | Planned: persistent storage |
| Multiple reservations with the same name require manual disambiguation | Planned: disambiguation flow |
| Language is hardcoded to Czech in prompts | Planned: configurable persona language |
