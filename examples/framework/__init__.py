"""State machine mechanics — no or mock LLM required.

Ordered progression:

  01_hello_state_machine.py  — Minimal StateGraph: two vertices, pure Python.
  02_parallel_and_loop.py    — Parallel fan-out/fan-in + review loop (FakeLlmConnector).
  03_live_graph.py           — LiveGraphHooks: DOT snapshot per super-step.
  04_checkpoint_resume.py    — Checkpoint pause/resume with InMemoryCheckpointStore.

All scripts support the standard subcommands::

    uv run python examples/framework/<file>.py run
    uv run python examples/framework/<file>.py graph --browser
"""
