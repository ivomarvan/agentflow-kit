"""Convert Graphviz DOT to interactive HTML using the agentflow graph pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agentflow.describable.graph_renderer import GraphRenderer


def main(argv: list[str] | None = None) -> int:
    """Convert a DOT file to the same interactive HTML page as ``graph --browser`` / ``graph``.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` on success, ``2`` for usage errors, ``1`` for I/O or render failures.
    """
    parser = argparse.ArgumentParser(
        prog="dot2html",
        description=(
            "Render a Graphviz DOT file to an interactive HTML page "
            "(same SVG pipeline as agentflow graph --format html / graph --browser)."
        ),
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        type=Path,
        metavar="FILE",
        help="Input Graphviz DOT file",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        type=Path,
        metavar="FILE",
        help="Output HTML file",
    )
    parser.add_argument(
        "--title",
        default="",
        help="Page title (default: first label= attribute in the DOT file)",
    )
    args = parser.parse_args(argv)

    if not args.input.is_file():
        print(f"dot2html: input file not found: {args.input}", file=sys.stderr)
        return 1

    try:
        dot_source = args.input.read_text(encoding="utf-8")
        html = GraphRenderer.dot_to_html(dot_source, title=args.title)
        args.output.write_text(html, encoding="utf-8")
    except OSError as exc:
        print(f"dot2html: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(f"dot2html: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
