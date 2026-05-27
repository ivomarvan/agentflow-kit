"""Chapter 04 demo: a full ReAct agent in plain Python (no framework).

The agent combines:
  * search_policy  - a toy in-memory "RAG" over company policies
  * calculator     - safe math evaluator

Example question that exercises both:
    "What is twice the number of vacation days in our policy?"

The LLM must first call search_policy, read the answer, then call calculator.

Run:
    pip install -r requirements.txt
    ollama pull qwen2.5:7b-instruct
    python 04_react_agent_plain.py
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from dateutil import parser
from pprint import pprint
from llm_client import chat

# -----------------------------------------------------------------------------
# Tool implementations
# -----------------------------------------------------------------------------
POLICIES: dict[str, str] = {
    "vacation": "Employees are entitled to 25 days of paid vacation per year.",
    "sick days": "Employees may take up to 3 sick days per year without a doctor's note.",
    "remote work": "Remote work is allowed up to 4 days a week.",
    "parking": "Parking at the HQ is free for all employees.",
}


def search_policy(query: str) -> str:
    q = query.lower()
    hits: list[str] = []
    for key, text in POLICIES.items():
        if key in q:
            hits.append(text)
            continue
        if any(w in q for w in key.split()):
            hits.append(text)
    return "\n".join(hits) if hits else "No relevant policy found."


def calculator(expression: str) -> str:
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed:
        return "ERROR: disallowed characters"
    try:
        return str(eval(expression))  # noqa: S307
    except Exception as e:  # noqa: BLE001
        return f"ERROR: {e}"

def get_current_date(format: str) -> str:
    # check if the format is valid
    if format not in ["YYYY-MM-DD", "DD-MM-YYYY", "MM-DD-YYYY"]:
        return "ERROR: invalid format"
    format_map = {
        "YYYY-MM-DD": "%Y-%m-%d",
        "DD-MM-YYYY": "%d-%m-%Y",
        "MM-DD-YYYY": "%m-%d-%Y"
    }
    return datetime.now().strftime(format_map[format])

def add_days_to_date(date: str, days: int) -> str:
    # check if the date is valid
    result_datetime = valid_date(date)
    if isinstance(result_datetime, str):
        return result_datetime  # return the error message
    # check if the days is a positive integer
    if days < 0:
        return "ERROR: days must be a positive integer"
    # add the days to the date
    return (result_datetime + timedelta(days=days)).strftime("%Y-%m-%d")


def valid_date(date: str) -> datetime.datetime | str:
    """
    Accepts a text string as a date. Understands any reasonable format.
    Returns the result as datetime.datetime or returns a text description of the error.
    """
    # Check if the input is empty or contains only whitespace
    if not date or not date.strip():
        return "Error: Input string is empty."

    try:
        # Use dateutil.parser to handle various date formats automatically.
        # dayfirst=True is preferred for European/International formats (DD.MM.YYYY).
        # fuzzy=False ensures we don't accidentally ignore too much "garbage" text.
        dt = parser.parse(date, fuzzy=False, dayfirst=True)
        return dt
    
    except (ValueError, OverflowError, TypeError) as e:
        # Return a string description of the error if parsing fails
        return f"Error: Could not recognize the date format. ({str(e)})"



TOOLS_IMPL = {
    "search_policy": search_policy, 
    "calculator": calculator, 
    "get_current_date": get_current_date,
    "add_days_to_date": add_days_to_date
    }


TOOLS_SCHEMA: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_policy",
            "description": (
                "Search the company's internal policies (vacation, sick days, "
                "remote work, parking, ...). Returns the most relevant policy text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What you want to look up"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a simple math expression.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "e.g. '25 * 2'"}
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_date",
            "description": "Get the current date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "format": {"type": "string", "description": "The format of the date to return. e.g. 'YYYY-MM-DD'"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_days_to_date",
            "description": "Add a given number of days to a date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "The date to add the days to. e.g. 'YYYY-MM-DD'"},
                    "days": {"type": "integer", "description": "The number of days to add. e.g. 3"}
                },
                "required": ["date", "days"],
            },
        },
    },
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
# The ReAct loop
# -----------------------------------------------------------------------------
MAX_STEPS = 7


def run_agent(question: str) -> str:
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    total_tokens = 0

    for step in range(1, MAX_STEPS + 1):
        print(f"\n--- step {step} ---")

        print("--- DBG: MESSAGES -----------------------")
        pprint(messages, indent=4)
        print("--------------------------------")
        response = chat(messages=messages, tools=TOOLS_SCHEMA)

        print("--- DBG: RESPONSE -----------------------")
        pprint(response, indent=4)
        print("--------------------------------")

        usage = response.pop("_usage", None)
        if usage:
            total_tokens += usage["total_tokens"]
            print(f"  (tokens this step: {usage['total_tokens']}, running total: {total_tokens})")

        messages.append(response)

        tool_calls = response.get("tool_calls")
        if not tool_calls:
            print("  LLM -> FINAL")
            return response.get("content", "").strip()

        for call in tool_calls:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            print(f"  LLM -> tool call: {name}({args})")

            if name not in TOOLS_IMPL:
                result = f"ERROR: unknown tool '{name}'"
            else:
                try:
                    result = TOOLS_IMPL[name](**args)
                except Exception as e:  # noqa: BLE001
                    result = f"ERROR: {e}"

            print(f"  tool -> {result}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "name": name,
                    "content": str(result),
                }
            )

    return "AGENT ERROR: exceeded MAX_STEPS"


if __name__ == "__main__":
    # q = "What is twice the number of vacation days in our company policy?"
    # q = "What is the current date in the format YYYY-MM-DD?"
    q = "I haven't had any vacation yet. If I take it all in three days from today, when will the vacation end?"
    print(f"QUESTION: {q}")
    answer = run_agent(q)
    print("\n========== FINAL ANSWER ==========")
    print(answer)
