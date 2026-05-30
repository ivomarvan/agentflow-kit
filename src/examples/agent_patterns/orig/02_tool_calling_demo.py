"""Chapter 02 demo: LLM calls two real Python functions via tool-calling.

Flow:
    user prompt  ->  LLM returns tool_calls  ->  we execute them  ->
    feed results back  ->  LLM returns final text answer.

Run:
    # 1) Local (default): Ollama running + tool-capable model pulled:
    #    ollama pull qwen3:8b
    # 2) From the examples/ directory:
    #    pip install -r requirements.txt
    #    python 02_tool_calling_demo.py
    #
    # Other backends (see llm_client.py):
    #    LLM_BACKEND=openai python 02_tool_calling_demo.py
    #    LLM_BACKEND=gemini python 02_tool_calling_demo.py
"""

from __future__ import annotations

import json

from llm_client import BACKEND, MODEL, chat

from pprint import pprint

# -----------------------------------------------------------------------------
# Real Python implementations of the tools
# -----------------------------------------------------------------------------
def calculator(expression: str) -> str:
    """Evaluate a math expression. Extremely restricted for safety."""
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed:
        return "ERROR: disallowed characters"
    try:
        return str(eval(expression))  # noqa: S307 - intentional for demo
    except Exception as e:  # noqa: BLE001
        return f"ERROR: {e}"


def get_weather(city: str) -> str:
    """A fake weather lookup - in real life you'd call an API."""
    fake_db = {
        "Prague": "12 C, cloudy",
        "Tokyo": "24 C, sunny",
        "New York": "18 C, windy",
    }
    return fake_db.get(city, "Unknown city")


TOOLS_IMPL = {"calculator": calculator, "get_weather": get_weather}


# -----------------------------------------------------------------------------
# JSON schemas describing the tools to the LLM
# -----------------------------------------------------------------------------
TOOLS_SCHEMA: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a math expression and return the numeric result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Math expression, e.g. '19 * 23'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Return the current weather for a given city name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name, e.g. 'Prague'"}
                },
                "required": ["city"],
            },
        },
    },
]


def run(question: str, max_steps: int = 4) -> str:
    messages: list[dict] = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant. When a tool would give a more reliable "
                "answer, call it. Otherwise answer directly. Be concise."
            ),
        },
        {"role": "user", "content": question},
    ]

    for step in range(1, max_steps + 1):
        print(f"\n--- step {step} ---")

        print("--- DBG: MESSAGES -----------------------")
        pprint(messages, indent=4)
        print("--------------------------------")
        
        response = chat(messages=messages, tools=TOOLS_SCHEMA)
        messages.append(response)
        
        print("--- DBG: LLM RESPONSE -----------------------")
        pprint(response, indent=4)
        print("--------------------------------")

        tool_calls = response.get("tool_calls")
        
        print("--- DBG: TOOL CALLS -----------------------")
        pprint(tool_calls, indent=4)
        print("--------------------------------")
        
        if not tool_calls:
            # Final answer
            return response.get("content", "").strip()

        for call in tool_calls:
            name = call["function"]["name"]
            args_raw = call["function"]["arguments"] or "{}"
            try:
                args = json.loads(args_raw)
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

    return "AGENT ERROR: exceeded max steps"


if __name__ == "__main__":
    print(f"LLM backend : {BACKEND}")
    print(f"LLM model   : {MODEL}")
    print("-" * 40)

    # q = "What's the weather in Prague, and what is 19 times 23?"
    q = "What's the wether in Prague. And give me the themperature in Prague times 23?"
    print(f"QUESTION: {q}")
    answer = run(q)
    print("\n========== FINAL ANSWER ==========")
    print(answer)
