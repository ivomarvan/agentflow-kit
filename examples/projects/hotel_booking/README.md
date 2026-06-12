# Hotel Booking Voice Assistant

Educational `agentflow` example demonstrating a multi-turn hotel receptionist
(Emma) with explicit state-machine routing, tool-backed booking logic, and a
custom Live State hotel guest book panel.

## Run modes

```bash
uv run python examples/hotel_booking/hotel_booking_app.py run
uv run python examples/hotel_booking/hotel_booking_app.py gui
uv run python examples/hotel_booking/hotel_booking_app.py graph --browser
```

## Agent architecture

| Vertex | Role |
|--------|------|
| `IntentParserVertex` | Classifies NEW_BOOKING / CANCELLATION / INQUIRY / OTHER |
| `DataDispatcherVertex` | Pure-Python hub — routes to missing-field ask vertices |
| `AskGuestNameVertex` | Collects guest name |
| `AskDatesVertex` | Collects check-in / check-out dates |
| `AskCapacityVertex` | Collects number of guests |
| `AvailabilityCheckerVertex` | Calls availability tools, selects a room |
| `AlternativesVertex` | Offers alternate rooms or dates on conflict |
| `ConfirmationVertex` | Reads back summary, waits for explicit approval |
| `BookingExecutorVertex` | Pure Python — writes reservation after confirmation |
| `CancellationFlowVertex` | Finds and cancels with confirmation |
| `InquiryVertex` | Answers room and price questions |
| `OtherHandlerVertex` | Off-topic guard (max two reminders) |
| `VoiceFormatterVertex` | Polishes the final TTS-ready reply |

## Prompt engineering highlights

- **Persona:** Emma's role and AI identity in every system prompt (`PERSONA_HEADER`)
- **XML delimiters:** `<tts_constraints>` and `<asr_constraints>` separate voice rules
- **Few-shot examples:** intent classification and flexible date parsing
- **Confirmation pattern:** dedicated `ConfirmationVertex` plus executor guard
- **Decomposition:** hub-and-spoke data collection; dispatcher and executor are pure Python

## Sample questions

1. *New booking:* "Book a room for two from July 20 to 22 for Smith."
2. *Cancellation:* "Cancel the reservation for Novak family arriving July 10."
3. *Inquiry:* "How much is the Red Room per night?"
4. *Conflict:* "Book the Blue Room from July 8 to 10 for Brown."
5. *Off-topic:* "What's the weather today?"

## Live State panel

In `gui` mode the Chat tab shows `HotelBookPanel.vue` — a room × date matrix
(guest book) reflecting `_HOTEL` reservations in real time, including amber
flash on newly booked or cancelled cells.

## Extending the example

- Add room photos or amenity icons in row headers
- Introduce loyalty discounts via a `calculate_price` rule extension
- Send email confirmation after `BookingExecutorVertex` succeeds
