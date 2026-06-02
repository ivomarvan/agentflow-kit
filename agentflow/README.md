# agentflow — LLM Agent Library

Thin, design-clean abstraction over LLM backends. Supports Ollama, OpenAI, Gemini,
DeepSeek (OpenAI-compatible API) and Anthropic (native API).

## Directory layout

```
agentflow/
├── cli.py                          shared CLI helpers (logging, argparse)
├── __init__.py                     public re-exports — import from here
├── agents/
│   └── ToolAgent.py                ReAct-style agent: tools + system prompt + loop
├── llm/
│   ├── LlmConfig.py                env vars, backend detection, API keys
│   ├── LlmConnector.py             abstract interface + factory
│   ├── ChatResponse.py             typed response value objects
│   ├── OllamaManager.py            local Ollama server & model management
│   └── connectors/
│       ├── OpenAiConnector.py      openai, ollama, gemini, deepseek
│       └── AnthropicConnector.py   claude-* models
└── tools/
    ├── Tool.py                     ToolBase ABC + @param_desc + schema builder
    ├── ToolRegistry.py             register tools, build schemas, dispatch calls
    └── common_tools/
        └── Calculator.py           safe arithmetic tool (reusable)
```

## Quick Start

```python
from agentflow import LlmConfig, LlmConnector

config = LlmConfig.from_env()
connector = LlmConnector.create(config)
print(connector.describe())

response = connector.chat([{"role": "user", "content": "Hello!"}])
print(response.text)
print(response.usage)
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LLM_BACKEND` | auto | `ollama` / `openai` / `gemini` / `deepseek` / `anthropic` |
| `LLM_MODEL` | backend default | Model name; backend auto-detected from prefix |
| `LLM_BASE_URL` | backend default | Override endpoint URL |
| `LLM_TIMEOUT` | `120` | Request timeout in seconds |
| `OPENAI_API_KEY` | — | Required for `openai` backend |
| `GOOGLE_API_KEY` | — | Required for `gemini` backend |
| `DEEPSEEK_API_KEY` | — | Required for `deepseek` backend |
| `ANTHROPIC_API_KEY` | — | Required for `anthropic` backend |
| `OLLAMA_MODELS` | — | Comma-separated list of available Ollama models |
| `OPENAI_MODELS` | — | Comma-separated list of available OpenAI models |
| `GEMINI_MODELS` | — | Comma-separated list of available Gemini models |
| `DEEPSEEK_MODELS` | — | Comma-separated list of available DeepSeek models |
| `ANTHROPIC_MODELS` | — | Comma-separated list of available Anthropic models |

## Writing Tools

```python
from agentflow import ToolBase, ToolRegistry, param_desc

class GetWeather(ToolBase):
    """Return current weather for a city."""  # <- sent to LLM as description

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key  # tools carry state

    @param_desc(
        city="City name, e.g. 'Prague'",
        unit="Temperature unit: 'celsius' or 'fahrenheit'",
    )
    def execute(self, city: str, unit: str = "celsius") -> str:
        return f"22 C, sunny in {city}"

registry = ToolRegistry()
registry.register(GetWeather(api_key="..."))

# schemas() produces the list for a tool-capable connector (future LlmToolConnector):
schemas = registry.schemas()

# dispatch a call returned by the LLM:
result = registry.execute(call.name, call.arguments)
```

The JSON schema is derived entirely from:
- Class docstring → `description`
- `execute()` type annotations → parameter types
- `@param_desc(...)` → parameter descriptions
- Default values → required vs optional fields

## ToolAgent — agent with tools

`ToolAgent` encapsulates the full ReAct-style agentic loop
(Reason → Act → Observe) in a single object.  No subclassing needed — all
configuration is passed in the constructor.

```python
from agentflow import LlmConfig, LlmConnector, ToolAgent
from agentflow.tools.common_tools.Calculator import Calculator

agent = ToolAgent(
    connector=LlmConnector.create(LlmConfig.from_env()),
    tools=[Calculator()],
    system_prompt="You are a helpful math assistant. Use tools when needed.",
    name="math_demo",
    description="Demonstrates calculator tool-calling.",
    max_steps=6,
)

answer = agent.run("What is 1234 * 5678?")
print(answer)
```

### Self-documenting output

```python
print(agent.describe())           # Markdown: config, system prompt, tool list
import json
print(json.dumps(agent.to_json(), indent=2))  # JSON: full config as dict
```

### Planned extensions

| Future class | Purpose |
|---|---|
| `MultiModelAgent` | Orchestrator + specialist sub-agents |

## agentflow.statemachine

Declarative state-graph orchestration for AI agents using the Bulk Synchronous Parallel
(BSP) model. Define frozen dataclass state, async vertex nodes, and signal-based
transitions; the runner executes parallel super-steps with automatic patch merging.

| Key Class | Purpose |
|-----------|---------|
| `StateGraph` | Declarative topology: start node, transitions, parallel fan-out |
| `StateVertex` | Abstract base for graph nodes (`async run()` → signal + patch) |
| `StateGraphRunner` | BSP execution loop with hooks, checkpointing, and sync entry point |

```python
from dataclasses import dataclass
from agentflow.statemachine import (
    Context, StateGraph, StateGraphRunner, StateVertex,
    StdEnd, StdSignal, Transition,
)
from agentflow.statemachine.testing import FakeLlmConnector

@dataclass(frozen=True)
class S:
    msg: str = ""

@dataclass
class P:
    msg: str | None = None

class Hello(StateVertex):
    async def run(self, state, ctx):
        return StdSignal.ok, P(msg="Hello!")

graph = StateGraph(Hello, [Transition(Hello, StdSignal.ok, StdEnd)])
StateGraphRunner(graph, Context(FakeLlmConnector())).run_sync(S())
```

See [statemachine/README.md](statemachine/README.md) for the full reference.

## Unified CLI (`Describable` / `AgentApp`)

Runnable scripts call `run_argparse()` or `AgentApp.cli()` as the `if __name__ == "__main__"` entry-point.
With **no arguments**, the script prints help (including full grammar for every subcommand) and exits.

```text
script.py -h
script.py run [QUESTION...]
script.py gui [--host HOST] [--port PORT] [--no-browser]   # AgentApp only
script.py describe [--format markdown|json|html] [-o|--output FILE]
script.py graph [--format dot|svg|svg-raw|html|png] [-o|--output FILE]
script.py graph --browser
```

```bash
uv run python examples/quickstart/01_brief_example.py run
uv run python examples/quickstart/01_brief_example.py graph --browser
uv run python examples/agents/01_tool_calling_agent.py describe --format json -o desc.json
```

## Ollama model management

Models are stored in `~/.ollama/models/` — shared system-wide across all projects and venvs.

```bash
python agentflow/llm/OllamaManager.py status
python agentflow/llm/OllamaManager.py ensure qwen2.5:1.5b
python agentflow/llm/OllamaManager.py list
```

## Logging

All classes use `logging.getLogger(__name__)`. Enable DEBUG for full request/response tracing:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Standalone testing (each module has `__main__`)

Every module can be run directly for manual testing:

```bash
python agentflow/llm/LlmConfig.py --help
python agentflow/llm/LlmConfig.py show
python agentflow/llm/LlmConfig.py backends
python agentflow/llm/LlmConfig.py infer gpt-4o

python agentflow/llm/LlmConnector.py show
python agentflow/llm/LlmConnector.py ping

python agentflow/llm/OllamaManager.py status
python agentflow/llm/OllamaManager.py list
```

## Testing

Tests live in `agentflow/tests/` and travel with the library when it is split
into its own repository.

### Unit tests — no network, no API key required

```bash
pytest                            # from project root — runs unit tests only (default)
pytest agentflow/tests/             # lib tests only
pytest -m unit                    # explicit marker
```

### Integration tests — live LLM API calls (spend API tokens!)

```bash
pytest -m integration             # default model: gpt-4o-mini (cheapest)
TEST_LLM_BACKEND=ollama pytest -m integration   # use local Ollama
```

Integration tests are **excluded by default** (`addopts = "-m 'not integration'"` in
`pyproject.toml`).  Run them explicitly — never automatically on save.

### Test markers

| Marker | When to use |
|---|---|
| `@pytest.mark.unit` | Pure logic, no I/O — run on every change |
| `@pytest.mark.integration` | Live LLM call — run explicitly only |

## Environment setup

This library is part of the `ai_agents_education` repository.
See the root `README.md` for full environment setup instructions (`uv sync`).

If this library is ever extracted as a standalone package:

```bash
uv sync          # or: pip install -e ".[dev]"
cp .env.example .env   # fill in API keys
```

## Comparison with LangGraph and CrewAI

| Feature | **agentflow** | LangGraph | CrewAI |
|---------|--------------|-----------|--------|
| Execution model | BSP (deterministic super-steps) | Event-driven DAG | Role-based multi-agent |
| State management | Frozen dataclasses + typed reducers | TypedDict (mutable) | Pydantic models |
| Parallel execution | `Parallel(A, B)` with barrier sync | `Send()` API | Agent delegation |
| Graph visualization | Built-in SVG/HTML/DOT (`Describable`) | LangSmith (external service) | — |
| Checkpointing | Protocol-based (memory/file/DB) | PostgresSaver, RedisSaver | — |
| Pause / resume | `run_until()` + `resume()` | `interrupt_before/after` | — |
| Type safety | `mypy --strict`, frozen state | Partial | Partial |
| LLM agnostic | Yes (connector protocol) | Yes (LangChain) | Yes |
| Streaming tokens | ❌ not yet | ✅ | ✅ |
| Distributed execution | ❌ not yet | ❌ | ✅ (agents as services) |
| Production maturity | 🔬 educational | ✅ production-ready | ✅ production-ready |

agentflow prioritizes transparency and correctness over features. It is designed for learning
and prototyping. For production workloads requiring streaming or distributed execution, consider
LangGraph.
