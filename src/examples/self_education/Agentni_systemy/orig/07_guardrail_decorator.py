"""Chapter 07 demo: a minimal `@guardrail` decorator pattern.

Idea: every tool exposed to an LLM gets wrapped with a validator.
If the validator rejects the inputs, we return an error string
(the LLM sees it as an observation and can correct itself) -
no dangerous code actually runs.

Run:
    python 07_guardrail_decorator.py
"""

from __future__ import annotations

import re
from collections.abc import Callable
from functools import wraps
from typing import Any


# -----------------------------------------------------------------------------
# Tiny guardrail framework
# -----------------------------------------------------------------------------
Validator = Callable[[dict[str, Any]], tuple[bool, str]]


def guardrail(validator: Validator) -> Callable:
    """Decorator: run `validator(kwargs)` before the actual function."""

    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(**kwargs: Any) -> Any:
            ok, reason = validator(kwargs)
            if not ok:
                return f"GUARDRAIL REJECTED: {reason}"
            return fn(**kwargs)

        return wrapper

    return deco


# -----------------------------------------------------------------------------
# Validators
# -----------------------------------------------------------------------------
SAFE_MATH_RE = re.compile(r"^[0-9+\-*/(). ]+$")


def validate_calculator(kwargs: dict[str, Any]) -> tuple[bool, str]:
    expr = kwargs.get("expression", "")
    if not isinstance(expr, str):
        return False, "expression must be a string"
    if not SAFE_MATH_RE.match(expr):
        return False, "only digits and + - * / ( ) . are allowed"
    if len(expr) > 100:
        return False, "expression too long (>100 chars)"
    return True, "ok"


ALLOWED_POLICY_TOPICS = {"vacation", "sick days", "remote work", "parking"}


def validate_search_policy(kwargs: dict[str, Any]) -> tuple[bool, str]:
    query = kwargs.get("query", "")
    if not isinstance(query, str) or not query.strip():
        return False, "query must be a non-empty string"
    if len(query) > 200:
        return False, "query too long (>200 chars)"
    return True, "ok"


# -----------------------------------------------------------------------------
# Tools wrapped with guardrails
# -----------------------------------------------------------------------------
@guardrail(validate_calculator)
def calculator(expression: str) -> str:
    # Safe to eval because validator restricted the character set.
    return str(eval(expression))  # noqa: S307


@guardrail(validate_search_policy)
def search_policy(query: str) -> str:
    policies = {
        "vacation": "25 days/year",
        "sick days": "3 days/year without doctor note",
        "remote work": "up to 4 days/week",
        "parking": "free at HQ",
    }
    q = query.lower()
    for k, v in policies.items():
        if k in q:
            return f"{k}: {v}"
    return "No matching policy."


# -----------------------------------------------------------------------------
# Demo: see what happens with benign vs. adversarial inputs
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    cases = [
        ("calculator", {"expression": "2 + 2 * 3"}),
        ("calculator", {"expression": "__import__('os').system('ls')"}),   # injection
        ("calculator", {"expression": "9" * 200}),                          # too long
        ("search_policy", {"query": "vacation"}),
        ("search_policy", {"query": ""}),                                   # empty
        ("search_policy", {"query": "A" * 300}),                            # too long
    ]

    fns = {"calculator": calculator, "search_policy": search_policy}

    print(f"{'tool':<16} {'args':<40} -> result")
    print("-" * 90)
    for tool_name, args in cases:
        out = fns[tool_name](**args)
        args_repr = str(args)
        if len(args_repr) > 38:
            args_repr = args_repr[:35] + "..."
        print(f"{tool_name:<16} {args_repr:<40} -> {out}")
