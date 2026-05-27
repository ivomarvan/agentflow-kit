"""Shared CLI utilities for standalone script execution across src/lib.

Each script in this library can be run directly (``python src/lib/llm/LlmConfig.py``).
These helpers ensure a consistent logging format and argparse style across all of them.

Usage in a script's ``if __name__ == "__main__"`` block::

    from src.agentflow.cli import setup_logging, make_arg_parser

    setup_logging()
    parser = make_arg_parser(__doc__)
    subparsers = parser.add_subparsers(dest="command")
    ...
"""

from __future__ import annotations

import argparse
import logging
import sys

_LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with a consistent format for CLI output.

    Args:
        level: Logging level (e.g. ``logging.DEBUG``). Defaults to ``INFO``.
    """
    logging.basicConfig(level=level, format=_LOG_FORMAT, stream=sys.stderr)


def make_arg_parser(doc: str | None) -> argparse.ArgumentParser:
    """Create an ArgumentParser that uses the calling module's docstring as description.

    The docstring is displayed verbatim (``RawDescriptionHelpFormatter``), so
    its existing indentation and line breaks are preserved.

    Args:
        doc: Module-level ``__doc__`` string of the calling script.

    Returns:
        Configured ``ArgumentParser`` instance ready for subcommands or arguments.
    """
    return argparse.ArgumentParser(
        description=doc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


if __name__ == "__main__":
    setup_logging()
    parser = make_arg_parser(__doc__)
    parser.parse_args()
    print("cli.py: helper module, no standalone functionality.")
