# examples — agentflow examples

## Where to start

```
examples/
├── framework/   ← Start here: learn how the StateGraph works (no API key needed)
├── agents/      ← Then: agent patterns with a real LLM (Ollama or cloud API)
└── projects/    ← Finally: full multi-file applications
```

---

## `framework/` — State machine mechanics

No real LLM required. All scripts work with FakeLlmConnector or pure Python.

| File | What it shows |
|------|---------------|
| `01_hello_state_machine.py` | `AgentApp` + minimal `StateGraph`: two vertices, pure Python |
| `02_parallel_and_loop.py` | `Parallel` fan-out/fan-in + review loop |
| `03_live_graph.py` | `LiveGraphHooks` — DOT snapshot per super-step |
| `04_checkpoint_resume.py` | Pause / resume with `InMemoryCheckpointStore` |
| `05_counter_live_model.py` | `LiveModel` standalone demo (`/demo` GUI) |

```bash
uv run python examples/framework/01_hello_state_machine.py run   # → HELLO
uv run python examples/framework/02_parallel_and_loop.py graph --browser
uv run python examples/framework/05_counter_live_model.py          # LiveModel /demo GUI
```

---

## `agents/` — Agent patterns with real LLM

Require a running LLM backend (Ollama default) or a cloud API key.

| File | Pattern |
|------|---------|
| `01_tool_calling.py` | Minimal ReAct: LLM + 2 tools |
| `02_react_agent.py` | Full ReAct: 4 tools, chained tool calls |
| `03_review_loop.py` | Retrieve → Generate → Review retry loop |
| `04_pipeline.py` | Sequential multi-agent pipeline |
| `05_validated_tools.py` | Guardrailed tools with input validation |
| `06_smart_home.py` | Worker/Judge loop with safety validation |
| `07_smart_home_live.py` | Same + GUI Live State panel |

```bash
# Install a local model first:
ollama pull qwen2.5:7b-instruct

uv run python examples/agents/01_tool_calling.py run
uv run python examples/agents/07_smart_home_live.py gui
```

---

## `projects/` — Full applications

Multi-file projects with their own data models, tools, and documentation.

| Directory | Description |
|-----------|-------------|
| `hotel_booking/` | Hotel booking voice assistant (Emma) — multi-turn conversation, hub-and-spoke data collection, GUI Live State hotel guest book |

```bash
uv run python examples/projects/hotel_booking/hotel_booking_app.py gui
```

---

## Common subcommands

Every example script supports the same subcommands:

```bash
uv run python examples/.../<file>.py --help        # show help
uv run python examples/.../<file>.py run           # run workflow in terminal
uv run python examples/.../<file>.py gui           # start GUI (agents + projects only)
uv run python examples/.../<file>.py graph --browser  # open state graph in browser
```
