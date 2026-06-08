"""Render Python source files as syntax-highlighted HTML for the GUI server.

Serves read-only views of ``.py`` files that are reachable from allowed
roots (cwd, ``sys.path``, and the installed ``agentflow`` package tree).
"""

from __future__ import annotations

import html as html_module
import sys
from pathlib import Path

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer

_SOURCE_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{pygments_css}
body {{
  margin: 0;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  background: #ffffff;
  color: #24292e;
}}
.source-header {{
  position: sticky;
  top: 0;
  z-index: 2;
  padding: 0.65rem 1rem;
  background: #f6f8fa;
  border-bottom: 1px solid #d0d7de;
  font-size: 0.85rem;
  font-family: ui-monospace, "Cascadia Code", "Source Code Pro", monospace;
}}
.source-header .path {{
  color: #0969da;
  word-break: break-all;
}}
.source-header .line {{
  color: #57606a;
  margin-left: 0.5rem;
}}
.highlight-wrap {{
  overflow: auto;
  padding: 0.5rem 0;
}}
.highlight {{
  margin: 0;
  background: transparent !important;
}}
.highlight pre {{
  margin: 0;
  padding: 0 1rem 1rem;
  line-height: 1.45;
  font-size: 0.82rem;
}}
.highlighttable {{
  width: 100%;
  border-collapse: collapse;
}}
.highlighttable td.linenos {{
  width: 3.5em;
  padding: 0 0.75rem 0 1rem;
  text-align: right;
  color: #8c959f;
  user-select: none;
  vertical-align: top;
  border-right: 1px solid #d0d7de;
  background: #f6f8fa;
}}
.highlighttable td.code {{
  padding-left: 0.75rem;
  width: 100%;
  background: #ffffff;
}}
.hll {{
  background-color: #fff8c5 !important;
  display: block;
  margin: 0 -0.75rem;
  padding: 0 0.75rem;
}}
</style>
</head>
<body>
<header class="source-header">
  <span class="path">{escaped_path}</span>{line_badge}
</header>
<div class="highlight-wrap">
{highlighted}
</div>
{scroll_script}
</body>
</html>
"""


def allowed_source_roots() -> list[Path]:
    """Return directory roots from which source files may be served.

    Includes the current working directory, every existing ``sys.path`` entry,
    and the installed ``agentflow`` package directory when importable.

    Returns:
        List of absolute, resolved directory paths (may contain duplicates).
    """
    from agentflow.describable.graph_renderer import GraphRenderer

    roots: list[Path] = [Path.cwd().resolve()]
    package_root = GraphRenderer._agentflow_package_root()
    if package_root is not None:
        roots.append(package_root)
    for entry in sys.path:
        if not entry:
            continue
        try:
            candidate = Path(entry).resolve()
        except OSError:
            continue
        if candidate.is_dir():
            roots.append(candidate)
    return roots


def resolve_source_path(path_str: str) -> Path:
    """Resolve and authorize a filesystem path for read-only serving.

    Args:
        path_str: Absolute or relative path to a ``.py`` file.

    Returns:
        Resolved absolute path to an existing regular file.

    Raises:
        FileNotFoundError: When the path does not exist or is not a file.
        ValueError: When the file is not a ``.py`` source file.
        PermissionError: When the resolved path is outside allowed roots.
    """
    try:
        path = Path(path_str).expanduser().resolve(strict=True)
    except OSError as exc:
        raise FileNotFoundError(path_str) from exc

    if not path.is_file():
        raise FileNotFoundError(str(path))
    if path.suffix.lower() != ".py":
        raise ValueError("Only .py source files can be viewed")

    for root in allowed_source_roots():
        try:
            if path.is_relative_to(root):
                return path
        except ValueError:
            continue
    raise PermissionError(f"Source path not allowed: {path}")


def render_source_html(path: Path, *, line: int | None = None) -> str:
    """Return a standalone HTML page with Pygments-highlighted Python source.

    Args:
        path: Resolved path to a ``.py`` file (must pass ``resolve_source_path``).
        line: Optional 1-based line number to highlight and scroll into view.

    Returns:
        Complete HTML document string.

    Raises:
        ValueError: When *line* is not a positive integer.
    """
    if line is not None and line < 1:
        raise ValueError("line must be a positive integer")

    source = path.read_text(encoding="utf-8")
    hl_lines: list[str] = [str(line)] if line is not None else []
    formatter = HtmlFormatter(
        style="default",
        linenos="table",
        anchorlinenos=True,
        lineanchors="L",
        hl_lines=hl_lines,
        wrapcode=True,
    )
    highlighted = highlight(source, PythonLexer(), formatter)
    escaped_path = html_module.escape(str(path))
    line_badge = (
        f'<span class="line">line {line}</span>' if line is not None else ""
    )
    scroll_script = ""
    if line is not None:
        scroll_script = (
            f"<script>document.getElementById('L-{line}')"
            "?.scrollIntoView({block:'center'});</script>"
        )
    return _SOURCE_PAGE_TEMPLATE.format(
        title=html_module.escape(f"{path.name} — source"),
        pygments_css=formatter.get_style_defs(".highlight"),
        escaped_path=escaped_path,
        line_badge=line_badge,
        highlighted=highlighted,
        scroll_script=scroll_script,
    )
