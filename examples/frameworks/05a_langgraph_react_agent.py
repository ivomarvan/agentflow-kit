"""Chapter 05a demo: Combining the ReAct tools from chapter 04 with LangGraph.

This example takes the custom tools we built in `04_react_agent_plain.py`
and orchestrates them using `langgraph` instead of our custom while-loop.

Run:
    pip install -r requirements.txt
    python 05a_langgraph_react_agent.py
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from dateutil import parser
from pprint import pprint

# LangGraph and LangChain imports
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage

# We will use our custom chat function to simulate the LLM. 
# In a real LangChain app, you would use ChatOpenAI or ChatOllama directly,
# but we are wrapping it manually here to keep it framework-agnostic at the LLM level.
from llm_client import chat

# -----------------------------------------------------------------------------
# Tool implementations (Same as Chapter 04)
# -----------------------------------------------------------------------------
POLICIES: dict[str, str] = {
    "vacation": "Employees are entitled to 25 days of paid vacation per year.",
    "sick days": "Employees may take up to 3 sick days per year without a doctor's note.",
    "remote work": "Remote work is allowed up to 4 days a week.",
    "parking": "Parking at the HQ is free for all employees.",
}

def search_policy(query: str) -> str:
    q = query.lower()
    hits = [text for key, text in POLICIES.items() if key in q or any(w in q for w in key.split())]
    return "\n".join(hits) if hits else "No relevant policy found."

def calculator(expression: str) -> str:
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed:
        return "ERROR: disallowed characters"
    try:
        return str(eval(expression))  # noqa: S307
    except Exception as e:
        return f"ERROR: {e}"

def get_current_date(format: str) -> str:
    if format not in ["YYYY-MM-DD", "DD-MM-YYYY", "MM-DD-YYYY"]:
        return "ERROR: invalid format"
    format_map = {"YYYY-MM-DD": "%Y-%m-%d", "DD-MM-YYYY": "%d-%m-%Y", "MM-DD-YYYY": "%m-%d-%Y"}
    return datetime.now().strftime(format_map[format])

def valid_date(date: str) -> datetime | str:
    if not date or not date.strip(): return "Error: Input string is empty."
    try:
        return parser.parse(date, fuzzy=False, dayfirst=True)
    except Exception as e:
        return f"Error: Could not recognize date format. ({e})"

def add_days_to_date(date: str, days: int) -> str:
    dt = valid_date(date)
    if isinstance(dt, str): return dt
    if days < 0: return "ERROR: days must be positive"
    return (dt + timedelta(days=days)).strftime("%Y-%m-%d")

TOOLS_IMPL = {
    "search_policy": search_policy, 
    "calculator": calculator, 
    "get_current_date": get_current_date,
    "add_days_to_date": add_days_to_date
}

# The JSON Schema representation
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_policy",
            "description": "Search the company's internal policies.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a simple math expression.",
            "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_date",
            "description": "Get the current date.",
            "parameters": {"type": "object", "properties": {"format": {"type": "string"}}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_days_to_date",
            "description": "Add a given number of days to a date.",
            "parameters": {"type": "object", "properties": {"date": {"type": "string"}, "days": {"type": "integer"}}, "required": ["date", "days"]},
        },
    }
]

tool_names = ", ".join([t["function"]["name"] for t in TOOLS_SCHEMA])

SYSTEM_PROMPT = (
    f"You are a helpful company assistant. "
    f"Break down each user question into elementary logical parts. "
    f"To obtain any fact or perform any date arithmetic, you MUST always use the appropriate tool from the following list: {tool_names}. "
    f"Never calculate days or perform math yourself, always call 'add_days_to_date' or 'calculator'. "
    f"Never assume you know the company policies, always call 'search_policy'. "
    f"Never assume you know the current date, always call 'get_current_date'. "
    f"Answer concisely in English."
)

# -----------------------------------------------------------------------------
# LangGraph State & Nodes
# -----------------------------------------------------------------------------

# In LangGraph, we define our memory as a class. 
# `add_messages` ensures that lists of messages are appended, not overwritten.
class AgentState(TypedDict):
    messages: Annotated[list[dict], add_messages]


def llm_node(state: AgentState) -> dict:
    """The brain of the agent. Calls the LLM with the current conversation history."""
    messages = state["messages"]
    
    # In LangGraph, `messages` are usually LangChain message objects (AIMessage, HumanMessage).
    # Since our custom `chat` function expects plain dicts, we need to convert them.
    plain_messages = []
    for m in messages:
        if isinstance(m, dict):
            plain_messages.append(m)
        else:
            # Basic conversion from LangChain object to plain dict
            role = "user"
            if isinstance(m, SystemMessage): role = "system"
            elif isinstance(m, AIMessage): role = "assistant"
            elif isinstance(m, ToolMessage): role = "tool"
            
            msg_dict = {"role": role, "content": m.content}
            if hasattr(m, "tool_calls") and m.tool_calls:
                # Need to map back to the format our `chat` function returned
                msg_dict["tool_calls"] = [{"type": "function", "id": tc["id"], "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])}} for tc in m.tool_calls]
            if isinstance(m, ToolMessage):
                msg_dict["tool_call_id"] = getattr(m, "tool_call_id", "")
                msg_dict["name"] = getattr(m, "name", "")
            plain_messages.append(msg_dict)
    
    print("--- DBG: LLM IS THINKING ---")
    response = chat(messages=plain_messages, tools=TOOLS_SCHEMA)
    
    # We clean up the response to append it to state
    usage = response.pop("_usage", None)
    if usage:
        print(f"  [tokens: {usage['total_tokens']}]")
        
    # LangChain strict checking requires 'content' key even if it's empty
    if "content" not in response or response["content"] is None:
        response["content"] = ""
        
    return {"messages": [response]}


def tools_node(state: AgentState) -> dict:
    """Executes the tools requested by the LLM."""
    messages = state["messages"]
    last_message = messages[-1]
    
    # Handle both dicts (from our plain chat) and LangChain AIMessage objects
    if hasattr(last_message, "tool_calls"):
        tool_calls = getattr(last_message, "tool_calls", [])
    else:
        tool_calls = last_message.get("tool_calls", [])
    
    results = []
    for call in tool_calls:
        # Depending on whether the tool call comes from a plain dict or AIMessage object
        # the structure might differ slightly.
        if "function" in call:
            name = call["function"]["name"]
            args_str = call["function"].get("arguments", "{}")
        else:
            # LangChain's parsed tool_call format
            name = call["name"]
            # args are already a dict in LangChain parsed tool calls, so we mock it
            args_str = json.dumps(call.get("args", {}))
            
        try:
            args = json.loads(args_str or "{}")
        except json.JSONDecodeError:
            args = {}
            
        print(f"  [ToolNode] Executing: {name}({args})")
        
        if name not in TOOLS_IMPL:
            result_str = f"ERROR: unknown tool '{name}'"
        else:
            try:
                result_str = str(TOOLS_IMPL[name](**args))
            except Exception as e:
                result_str = f"ERROR: {e}"
                
        results.append({
            "role": "tool",
            "tool_call_id": call["id"],
            "name": name,
            "content": result_str,
        })
        
    return {"messages": results}


def should_continue(state: AgentState) -> str:
    """Conditional router that decides if we are done or need to execute tools."""
    last_message = state["messages"][-1]
    
    # Handle both dicts (from our plain chat) and LangChain AIMessage objects
    has_tools = False
    if hasattr(last_message, "tool_calls"):
        has_tools = bool(getattr(last_message, "tool_calls", []))
    else:
        has_tools = bool(last_message.get("tool_calls", []))
        
    # If the LLM returned tool calls, we go to the "tools" node
    if has_tools:
        return "tools"
    # Otherwise, it answered the user directly, so we are done
    return END

# -----------------------------------------------------------------------------
# Build the graph
# -----------------------------------------------------------------------------
def build_graph():
    workflow = StateGraph(AgentState)
    
    # Add our two nodes
    workflow.add_node("agent", llm_node)
    workflow.add_node("tools", tools_node)
    
    # Entry point is always the LLM
    workflow.set_entry_point("agent")
    
    # After the agent thinks, we route based on its output
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", END: END}
    )
    
    # After tools execute, we always go back to the agent to evaluate the results
    workflow.add_edge("tools", "agent")
    
    return workflow.compile()


if __name__ == "__main__":
    app = build_graph()
    
    q = "I haven't had a vacation yet. If I take one in three days from today, when will the vacation end?"
    print(f"QUESTION: {q}\n")
    
    # Initialize the state with the system prompt and the user's question
    initial_state = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": q}
        ]
    }
    
    # Run the graph
    final_state = app.invoke(initial_state)
    
    print("\n========== FINAL ANSWER ==========")
    final_message = final_state["messages"][-1]
    if hasattr(final_message, "content"):
        print(final_message.content)
    else:
        print(final_message.get("content", ""))
