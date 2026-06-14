"""Pretty logging formatter for agentflow development and debugging.

Applies hierarchical indentation to log records based on the logger name,
giving a visual overview of the BSP execution nesting:

    ◆ run_start: state=ReactState
      ↳ llm_call: model=gpt-4o-mini  [cache miss]
          · stored to cache
    ◆ step #1 end  →  [ToolExecutionVertex]
      ↳ tool_call: get_weather(location="Prague", units="C")
      ↳ tool_result: get_weather  →  12°C, cloudy
    ◆ step #2 end  →  [LlmCallVertex]
      ↳ llm_call: model=gpt-4o-mini  ← cache hit
    ◆ step #3 end  →  [StdEnd]
    ◆ run_end: state=ReactState

Indent levels by logger-name prefix:

    statemachine.runner  →  0 spaces   ◆
    statemachine         →  2 spaces   ↳
    agentflow.llm        →  4 spaces   ·

Usage::

    from agentflow.logging_config import setup_pretty_logging
    setup_pretty_logging()   # call once in run_workflow() or __main__
"""

from __future__ import annotations

import logging

# (prefix, indent_spaces, prefix_char)
# Ordered from most-specific to least-specific so the first match wins.
_INDENT_RULES: list[tuple[str, int, str]] = [
    ("statemachine.runner", 0, "◆"),
    ("statemachine",        2, "↳"),
    ("agentflow.llm",       4, "·"),
    ("agentflow",           2, "↳"),
]


class PrettyFormatter(logging.Formatter):
    """Logging formatter with visual indentation for agentflow log hierarchies.

    Logger-name prefix determines indentation level and prefix character
    according to ``_INDENT_RULES``.  WARNING and above additionally show
    the level name in brackets (e.g. ``[WARNING]``).
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record with indentation and prefix based on logger name.

        Args:
            record: Log record to format.

        Returns:
            Formatted string with leading indent, prefix, and message.
        """
        indent, prefix = self._resolve(record.name)
        msg = record.getMessage()
        if record.levelno >= logging.WARNING:
            return f"{' ' * indent}{prefix} [{record.levelname}] {msg}"
        return f"{' ' * indent}{prefix} {msg}"

    @staticmethod
    def _resolve(name: str) -> tuple[int, str]:
        for prefix, indent, char in _INDENT_RULES:
            if name == prefix or name.startswith(f"{prefix}."):
                return indent, char
        return 0, "·"


def setup_pretty_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with PrettyFormatter for agentflow output.

    Replaces all existing handlers on the root logger with a single
    ``StreamHandler`` that uses ``PrettyFormatter``.  Call once per
    process — typically at the top of ``run_workflow()`` or ``__main__``.

    Also silences noisy third-party loggers that produce INFO-level chatter
    irrelevant to the agent workflow (httpx request logs, httpcore transport
    details).  Their WARNING+ records still propagate so real errors are visible.

    Args:
        level: Minimum log level; defaults to ``logging.INFO``.
    """
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    handler = logging.StreamHandler()
    handler.setFormatter(PrettyFormatter())
    root.addHandler(handler)
    root.setLevel(level)

    # Suppress per-request INFO chatter from HTTP transport libraries.
    # Their loggers inherit the root handler but get a higher effective level
    # so only WARNING+ messages propagate (connection errors, timeouts, etc.).
    for noisy_logger in ("httpx", "httpcore", "openai._base_client"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
