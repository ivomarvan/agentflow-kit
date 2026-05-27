"""Safe arithmetic calculator tool for LLM tool-calling.

Evaluates simple math expressions using only digits, operators and parentheses.
Intentionally restricted — no imports, no string manipulation, no arbitrary code.
"""

from __future__ import annotations

import logging
from typing import Any

from git_root_to_syspath import agr
agr()

from src.agentflow.tools.Tool import ToolBase, param_desc

logger = logging.getLogger(__name__)


class Calculator(ToolBase):
    """Evaluate a safe arithmetic expression and return the numeric result.

    Accepts only digits, basic operators (+-*/), parentheses, and spaces.
    Any other characters are rejected to prevent code injection.
    """

    _ALLOWED_CHARS: frozenset[str] = frozenset("0123456789+-*/(). ")

    _SELF_TEST_CASES: list[tuple[str, str]] = [
        ("2 + 2",          "4"),
        ("19 * 23",        "437"),
        ("(100 - 5) / 5",  "19.0"),
        ("import os",      "ERROR"),   # injection attempt
        ("1 / 0",          "ERROR"),   # division by zero
    ]

    @param_desc(expression="Arithmetic expression to evaluate, e.g. '19 * 23' or '(4 + 5) / 3'.")
    def execute(self, expression: str) -> str:
        """Evaluate the expression and return its result as a string.

        Args:
            expression: Arithmetic expression using digits and +-*/(). only.

        Returns:
            Numeric result as a string, or an error message prefixed with ``ERROR:``.
        """
        if not set(expression) <= self._ALLOWED_CHARS:
            disallowed = sorted(set(expression) - self._ALLOWED_CHARS)
            logger.warning("Calculator: disallowed chars=%s expression=%r", disallowed, expression)
            return f"ERROR: disallowed characters: {disallowed}"
        try:
            result = eval(expression)  # noqa: S307 — intentionally restricted input
            logger.debug("Calculator: %s = %s", expression, result)
            return str(result)
        except Exception as exc:
            logger.warning("Calculator: eval failed: expression=%r error=%s", expression, exc)
            return f"ERROR: {exc}"


    # ------------------------------------------------------------------
    # Argparse hooks — adds "test" command to the inherited CLI
    # ------------------------------------------------------------------

    def _add_argparse_commands(self, subparsers: Any) -> None:
        """Register the ``test`` subcommand for self-testing."""
        subparsers.add_parser("test", help="Run built-in self-test examples.")

    def _handle_argparse_command(self, args: Any) -> None:
        """Dispatch the ``test`` command."""
        import sys
        if args.command == "test":
            ok = True
            for expr, expected_prefix in self._SELF_TEST_CASES:
                result = self.execute(expression=expr)
                status = "OK" if result.startswith(expected_prefix) else "FAIL"
                if status == "FAIL":
                    ok = False
                print(f"  [{status}] {expr!r:25s} -> {result}")
            sys.exit(0 if ok else 1)
        else:
            print(f"Unknown command: {args.command!r}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    Calculator().run_argparse(doc=__doc__, name=__name__)
