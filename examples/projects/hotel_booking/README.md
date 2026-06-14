# Hotel Booking Voice Assistant

> **Version:** 1.0 (first complete implementation, June 2026).  
> Further development is planned — see [Known Limitations](#known-limitations-and-planned-improvements) below.

A multi-turn voice assistant for the fictional **Four Colours Hotel**.  
Emma (the AI receptionist) helps guests book rooms, cancel reservations, and answer
room availability questions.  She always replies in Czech (čeština) — the LLM handles
language switching automatically without any explicit localisation code.

---

## Quick Start

Run from the repository root (`ai_agents_education/`):

```bash
# Interactive GUI chat (recommended)
uv run python examples/projects/hotel_booking/hotel_booking_app.py gui

# Single-turn CLI test
uv run python examples/projects/hotel_booking/hotel_booking_app.py run "Dobrý den, chtěl bych pokoj"

# State-machine graph visualisation
uv run python examples/projects/hotel_booking/hotel_booking_app.py graph --browser

# LiveModel standalone demo — hotel guest book without LLM
uv run python examples/projects/hotel_booking/hotel_booking_model.py
```

---

## Project Structure

```
hotel_booking/
├── hotel_booking_app.py      # Entry point, HotelBookingApp, graph topology, tool registry
├── state.py                  # HotelBookingState / Patch / Signal, Order Pydantic model
├── live_state.py             # Pydantic live-state models: HotelBookState, RoomState, Reservation
├── booking_store.py          # In-memory CRUD store (create / cancel / find / availability)
├── hotel_booking_model.py    # HotelBookingModel (LiveModel) + install_hotel_model()
├── hotel_model.py            # Standalone LiveModel demo entry point
├── vertices/
│   ├── _base.py              # HotelBookingVertexBase, make_partial_order_schema(), prompts
│   ├── order_direction_vertex.py     # Intent detection and routing
│   ├── order_details_vertex.py       # Iterative booking data collection
│   ├── cancellation_details_vertex.py# Iterative cancellation data collection
│   ├── inquiry_vertex.py             # Room information questions (uses tools)
│   ├── other_handler_vertex.py       # Off-topic guard
│   ├── availability_vertex.py        # Availability check (StateVertex, no LLM)
│   ├── order_confirmation_vertex.py  # Present summary, collect explicit confirmation
│   ├── execute_booking_vertex.py     # Create reservation (StateVertex, no LLM)
│   └── execute_cancellation_vertex.py# Cancel reservation (StateVertex, no LLM)
├── tools/
│   ├── check_availability_tool.py
│   ├── get_room_details_tool.py
│   ├── calculate_price_tool.py
│   ├── create_reservation_tool.py
│   ├── cancel_reservation_tool.py
│   ├── find_reservation_tool.py
│   └── find_alternatives_tool.py
└── doc/
    └── assignment.md         # Formal project specification
```

---

## Architecture

### State Machine

Every conversation turn starts at `OrderDirectionVertex`.  When `flow == "initial"` the
LLM detects the guest's intent; for subsequent turns in the same flow the vertex
short-circuits without an LLM call.

```
┌──────────────────────┐
│  OrderDirectionVertex │  ← every turn starts here
│  (intent detection)   │
└──────┬───────────────┘
       │
       ├─[order_request]─────────► OrderDetailsVertex
       │                                 │ data_complete
       │                                 ▼
       │                           AvailabilityVertex
       │                                 │ available
       │                                 ▼
       ├─[awaiting_confirmation]──► OrderConfirmationVertex
       │                                 │ confirmed
       │                                 ▼
       │                           ExecuteBookingVertex → StdEnd
       │
       ├─[order_cancellation]────► CancellationDetailsVertex
       │                                 │ data_complete
       │                                 ▼
       │                           ExecuteCancellationVertex → StdEnd
       │
       ├─[order_inquiry]─────────► InquiryVertex → StdEnd
       │
       └─[order_other]───────────► OtherHandlerVertex → StdEnd
```

### Key Design Patterns

#### 1. Multi-turn State Persistence
`HotelBookingApp` subclasses `AgentApp` and overrides `run_workflow()` to maintain
`_session_state` (messages, order, flow) across turns.  The base class creates a fresh
state each turn; this subclass carries the conversation forward.

```python
class HotelBookingApp(AgentApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._session_state: HotelBookingState | None = None

    async def run_workflow(self) -> str | None:
        # Prepend session state to new user message, run graph, save result
        ...
```

#### 2. Dynamic Schema Generation
`make_partial_order_schema()` uses `pydantic.create_model()` to build a schema
containing **only the unfilled `Order` fields** for the current turn.  The LLM's
`response_schema` therefore shrinks as the conversation progresses, which:
- reduces token waste on already-collected fields
- prevents the LLM from accidentally overwriting confirmed data

```python
schema = make_partial_order_schema(state.order, _BOOKING_FIELD_SPECS)
# If guest_name is already filled, the schema has no guest_name field.
response = await ctx.llm_for_model(self.model).achat(
    messages, response_schema=schema
)
```

#### 3. Pure StateVertex for Side-Effecting Operations
`AvailabilityVertex`, `ExecuteBookingVertex`, and `ExecuteCancellationVertex` are
`StateVertex` subclasses (no LLM) that call `BookingStore` directly.  This avoids
the overhead and non-determinism of an LLM call for pure data operations.

#### 4. Order Reset After Completion
After a successful booking or cancellation the patch resets `order=Order()` and
`flow="initial"`.  The next user turn therefore starts with a clean slate — the guest
can immediately request a new booking without residual data from the previous one.

#### 5. Structured LLM Output
Every LLM vertex passes a Pydantic model as `response_schema` to `achat()`.  The
`OpenAiConnector` transforms it into an OpenAI Structured Outputs request
(`response_format = {type: json_schema, strict: True}`).

---

## Hotel Data

### Rooms

| ID      | Name        | Beds | Price / night |
|---------|-------------|-----:|-------------:|
| `red`   | Red Room    |    3 |         €120 |
| `blue`  | Blue Room   |    2 |          €85 |
| `green` | Green Room  |    2 |          €85 |
| `white` | White Room  |    1 |          €55 |

### Seed Reservations (pre-loaded at startup)

| Room  | Guest          | Check-in   | Check-out  |
|-------|----------------|------------|------------|
| Red   | Novak family   | 2026-07-10 | 2026-07-14 |
| Blue  | Jana Dvorakova | 2026-07-08 | 2026-07-11 |
| Blue  | Peter Schmidt  | 2026-07-15 | 2026-07-18 |
| Green | Marie Horakova | 2026-07-12 | 2026-07-15 |
| White | Tomas Vesely   | 2026-07-09 | 2026-07-10 |

---

## Concepts Demonstrated

| Concept | Where |
|---------|-------|
| `AgentApp` subclassing for multi-turn persistence | `HotelBookingApp.run_workflow()` |
| Typed immutable state (frozen dataclass) + patch objects | `state.py` |
| Signal-based routing in a state machine | `HotelBookingSignal`, `hotel_booking_app.py` |
| Dynamic Pydantic schema via `pydantic.create_model()` | `vertices/_base.py` |
| `response_schema` for structured LLM output | every `LlmStateVertex.run()` |
| Pure `StateVertex` (no LLM) for deterministic operations | `AvailabilityVertex`, `ExecuteBookingVertex`, `ExecuteCancellationVertex` |
| `achat_with_tools()` for tool-augmented LLM calls | `InquiryVertex` |
| `LiveModel` + custom Vue component (hotel guest book) | `hotel_booking_model.py`, `HotelBookPanel.vue` |
| `PrivateAttr` for injecting dependencies into vertices | `AvailabilityVertex`, `ExecuteBookingVertex` |
| OpenAI Structured Outputs strict schema transformation | `OpenAiConnector._to_openai_strict_schema()` |

---

## Example Conversation

```
Turn 1
  User: Chtěl bych červený pokoj na 15–18 července, jsem Ivo
  → OrderDirectionVertex detects order_request, extracts partial data
  → OrderDetailsVertex: all fields collected (capacity missing)
  → StdEnd  Emma: "Pro kolik hostů?"

Turn 2
  User: Pro dvě osoby
  → OrderDirectionVertex (flow='booking', no LLM)
  → OrderDetailsVertex: data_complete
  → AvailabilityVertex: room available, price computed
  → OrderConfirmationVertex: summary presented
  → StdEnd  Emma: "Červený pokoj 15.–18. 7. za 360 EUR. Potvrzujete?"

Turn 3
  User: Ano
  → OrderDirectionVertex (flow='awaiting_confirmation', no LLM)
  → OrderConfirmationVertex: confirmed
  → ExecuteBookingVertex: reservation created, Guest Book updated
  → StdEnd  Emma: "Vaše rezervace byla úspěšně vytvořena."

Turn 4
  User: Chtěl bych objednat zelený pokoj
  → Order reset to empty by ExecuteBookingVertex; fresh intent detection
  → OrderDirectionVertex: order_request (new booking, no residual data)
```

---

## Known Limitations and Planned Improvements

This is the **first working version** of the example.  The following areas are known
to need further work:

- **Unavailable room handling** — when `AvailabilityVertex` emits `unavailable`, the
  guest is currently informed and the conversation ends.  An `AlternativesVertex` that
  suggests free rooms or alternative dates should be added.
- **Message history growth** — the full message history is passed to the LLM each turn.
  For long conversations this may exceed the context window or confuse the LLM with
  outdated context.  A summary or sliding-window mechanism is planned.
- **Date validation** — `OrderDetailsVertex` relies on the LLM to parse spoken dates.
  A dedicated date-normalisation step would make parsing more robust.
- **Multiple reservations per guest** — `ExecuteCancellationVertex` warns when multiple
  matching reservations exist but cancels only the first.  A disambiguation flow would
  improve this.
- **Persistent storage** — `BookingStore` is in-memory only; data is lost on restart.
- **Language flexibility** — the system prompt currently targets Czech responses.
  Parameterising the persona language would make the example more reusable.
