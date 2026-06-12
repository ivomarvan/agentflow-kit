# examples/agents — Agent patterns with agentflow

Each script demonstrates one canonical AI agent design pattern.
All examples require a running LLM (Ollama default, or a cloud API key).

## Examples

| File | Pattern | Complexity |
|------|---------|-----------|
| `01_tool_calling.py` | Minimal ReAct: LLM + Calculator + GetWeather | ★☆☆ |
| `02_react_agent.py` | Full ReAct: 4 tools, chained calls | ★★☆ |
| `03_review_loop.py` | Retrieve → Generate → Review retry loop | ★★☆ |
| `04_pipeline.py` | Sequential pipeline: Researcher → Writer → Editor | ★★☆ |
| `05_validated_tools.py` | Guardrailed tools with input validation | ★★☆ |
| `06_smart_home.py` | Worker/Judge loop with safety validation | ★★★ |
| `07_smart_home_live.py` | Same + GUI Live State panel | ★★★ |

## Running

```bash
# Install a local model first (or configure a cloud API key in .env):
ollama pull qwen2.5:7b-instruct

# Show help
uv run python examples/agents/01_tool_calling.py -h

# Run workflow in terminal
uv run python examples/agents/01_tool_calling.py run

# Open state graph in browser
uv run python examples/agents/01_tool_calling.py graph --browser

# Start GUI (web-based chat + settings + graph)
uv run python examples/agents/07_smart_home_live.py gui
```

Note: `03_review_loop.py` uses pure Python stubs — no LLM required.

## Key patterns illustrated

**ReAct loop (01, 02, 05):** `LlmCallVertex` calls the LLM and routes on whether
it wants to call tools or return a final answer. `ToolExecutionVertex` runs all
pending tool calls and loops back.

**Retry loop with quality gate (03):** a `Review` vertex either approves the draft
or requests a revision and routes back to `Generate`. A `max_attempts` guard prevents
infinite loops.

**Sequential pipeline (04):** each "agent" is a `StateVertex` with its own role
system prompt. State flows forward: `topic → research_notes → draft → final_post`.

**Guardrailed tools (05):** validation lives inside `ToolBase.execute()`. Invalid
inputs return a `GUARDRAIL: …` error string so the LLM can self-correct on the next turn.

**Worker/Judge (06, 07):** `DeviceWorkerVertex` proposes a plan using tools.
`SafetyJudgeVertex` validates safety rules and either approves or rejects with a reason.
On rejection, the Worker revises and resubmits (up to `max_revisions` times).
`07_smart_home_live.py` extends this with a Pydantic `HouseState` and GUI Live State panel.
