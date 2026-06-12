# examples/agents — Agent patterns with agentflow

Each script demonstrates one canonical AI agent design pattern implemented
with `agentflow.statemachine`. For comparison, the equivalent implementation
using an external framework lives in `examples/frameworks/`.

## Examples

| File | Pattern | Equivalent in `examples/frameworks/` |
|------|---------|--------------------------------------|
| `01_tool_calling_agent.py` | Minimal ReAct: LLM + Calculator + GetWeather | `02_tool_calling_demo.py` |
| `02_react_agent.py` | Full ReAct: policy search + math + date tools | `04_react_agent_plain.py` |
| `03_rag_review_loop.py` | Retrieve → Generate → Review retry loop | `05_langgraph_review_loop.py` |
| `04_blog_pipeline.py` | Sequential pipeline: Researcher → Writer → Editor | `06_crewai_blog_team.py` |
| `05_validated_tools.py` | Guardrailed tools with input validation | `07_guardrail_decorator.py` |
| `06_smart_home.py` | Worker/Judge loop with safety validation | — |
| `06_smart_home_live.py` | Same as above + GUI Live State panel (imports from `06_smart_home.py`) | — |

## Running examples

```bash
# Show help
uv run python examples/agents/01_tool_calling_agent.py -h

# Run the workflow
uv run python examples/agents/01_tool_calling_agent.py run

# Open composition graph in browser
uv run python examples/agents/01_tool_calling_agent.py graph --browser

# Start the GUI (web-based chat + settings + graph)
uv run python examples/agents/01_tool_calling_agent.py gui
```

Examples 01, 02, 05 require a running LLM backend (Ollama default):

```bash
ollama pull qwen2.5:7b-instruct
```

Example 03 uses pure Python stubs — no LLM required.

Example 04 requires a real LLM for the Researcher/Writer/Editor roles.

## Key patterns illustrated

**ReAct loop** (01, 02, 05): `LlmCallVertex` calls the LLM and routes on whether
it wants to call tools or return a final answer. `ToolExecutionVertex` runs all
pending tool calls and loops back. Both vertices share the same `ReactState`.

**Retry loop with quality gate** (03): a `Review` vertex acts as a quality gate —
it either approves the draft and routes to `StdEnd`, or requests a revision and
routes back to `Generate`. A `max_attempts` guard prevents infinite loops.

**Sequential pipeline** (04): each "agent" is a `StateVertex` with its own role
system prompt. The LLM is called independently in each vertex with domain-specific
context. State flows forward: `topic → research_notes → draft → final_post`.

**Guardrailed tools** (05): validation lives inside `ToolBase.execute()`. Invalid
inputs return a `GUARDRAIL: …` error string (not an exception), so the LLM sees
the rejection as a tool observation and can self-correct on the next turn.

**Worker/Judge review loop** (06): the `DeviceWorker` vertex uses tools to
inspect the current room state and proposes a plan. A separate `SafetyJudge`
vertex validates safety rules and either approves or rejects the plan with a
reason. On rejection, the Worker revises and resubmits (up to `max_revisions`
times). `06_smart_home_live.py` extends this by replacing the dict-based tools
with Pydantic model tools that mutate a shared `HouseState` instance, enabling
the GUI Live State panel to show room changes in real-time.
