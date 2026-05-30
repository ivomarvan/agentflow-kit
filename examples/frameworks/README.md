# agent_patterns — Pattern Examples

Agent design pattern examples implemented twice:

- `my/` — implementations using the **agentflow** framework
- `orig/` — reference implementations using LangGraph / CrewAI (for comparison)

## Running examples

```bash
# agentflow version
uv run python examples/patterns/02_tool_calling_demo.py

# LangGraph version (requires langgraph extra)
# uv run python examples/frameworks/05a_langgraph_react_agent.py
```

## Pattern overview

| File | Pattern | Framework |
|------|---------|-----------|
| `my/02_tool_calling_demo.py` | Tool Calling / ReAct | agentflow |
| `my/04_react_agent_statemachine.py` | ReAct with StateGraph | agentflow.statemachine |
| `orig/04_react_agent_plain.py` | ReAct plain LLM | agentflow (base) |
| `orig/05a_langgraph_react_agent.py` | ReAct | LangGraph |
| `orig/05_langgraph_review_loop.py` | Review loop | LangGraph |
| `orig/06_crewai_blog_team.py` | Multi-agent team | CrewAI |
