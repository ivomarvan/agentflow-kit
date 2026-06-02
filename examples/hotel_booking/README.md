# Hotel Booking Demo

Demonstrates **domain events** and a **custom GUI renderer** in agentflow.

`HotelBookingApp` uses `FakeLlmConnector` — no API key required.

## Run

```bash
# Show help
uv run python examples/hotel_booking/hotel_booking_app.py -h

# Text workflow (no GUI)
uv run python examples/hotel_booking/hotel_booking_app.py run

# GUI server (auto-discovers renderer, rebuilds, opens browser)
uv run python examples/hotel_booking/hotel_booking_app.py gui

# Graph visualization
uv run python examples/hotel_booking/hotel_booking_app.py graph --browser
```

## Architecture

```
HotelBookingApp (AgentApp)
├── connector: FakeLlmConnector
├── registry: ToolRegistry
│   └── HotelBookingTool (name="book_hotel_room")
│       ├── stores   → ReservationStore (in-memory list)
│       └── emits    → ReservationEvent → EventBus → GUI
└── graph: StateGraph
    └── ProcessBooking → Done → StdEnd
```

## Custom GUI Renderer

`gui_renderers/hotel_reservation.vue` renders `ReservationEvent` as a styled table
in the GUI log panel instead of the default JSON dump.

The build script discovers and registers the renderer automatically when you run:

```bash
uv run python examples/hotel_booking/hotel_booking_app.py gui
```

### Adding Your Own Renderer

1. Create `gui_renderers/<your_event_type>.vue` next to your app script.
   - Filename convention: underscores map to dots in the event type key,
     e.g. `order_placed.vue` → registers for `order.placed` events.
2. Define the component — it receives a single `event` prop:
   ```vue
   <script setup lang="ts">
   defineProps<{ event: Record<string, unknown> }>()
   </script>
   ```
3. Run with `gui` subcommand — the build script auto-generates the registry.

## Domain Event

`ReservationEvent` (event_type `hotel.reservation`) is emitted by `HotelBookingTool.run()`
and stored in the `EventBus` history.  The GUI renders it using the custom renderer.

```python
class ReservationEvent(AgentEvent):
    event_type: Literal["hotel.reservation"] = "hotel.reservation"
    guest_name: str
    room: str
    check_in: str
    check_out: str
```

## Notes

- `ReservationStore` is fully functional without a GUI — useful for unit tests.
- Without the GUI, events appear in Python logging at `DEBUG` level.
- `ReservationEvent.event_type = "hotel.reservation"` is the renderer lookup key.
