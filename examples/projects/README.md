# examples/projects — Full applications

Multi-file projects with their own data models, tool layers, state machines, and documentation.
Each project has its own `README.md` with detailed instructions.

## Projects

| Directory | Description |
|-----------|-------------|
| `hotel_booking/` | **Hotel Booking Voice Assistant (Emma)** — multi-turn voice assistant, hub-and-spoke data collection, safety-gated reservations, GUI Live State hotel guest book |

## Running

```bash
uv run python examples/projects/hotel_booking/hotel_booking_app.py --help
uv run python examples/projects/hotel_booking/hotel_booking_app.py run
uv run python examples/projects/hotel_booking/hotel_booking_app.py gui
```
