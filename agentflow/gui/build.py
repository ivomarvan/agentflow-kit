"""GUI build helpers — check and trigger npm build for the Vue SPA.

The Vue SPA lives in ``gui/`` at the project root and is built to
``agentflow/gui/static/``.  This module checks whether the build output
is present and optionally triggers ``npm run build``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

STATIC_DIR = Path(__file__).parent / "static"
DIST_INDEX = STATIC_DIR / "index.html"
_GUI_SOURCE_DIR = Path(__file__).parent.parent.parent / "gui"


def check_build() -> tuple[bool, str]:
    """Check whether the pre-built GUI is present.

    Returns:
        Tuple of ``(ok, message)`` where *ok* is ``True`` when
        ``agentflow/gui/static/index.html`` exists.
    """
    if not DIST_INDEX.exists():
        return False, "GUI not built. Run: cd gui && npm run build"
    return True, "ok"


def ensure_build(*, force: bool = False, interactive: bool = True) -> None:
    """Ensure the GUI build is present; optionally prompt the user to build.

    Args:
        force: When ``True``, always rebuild even if the output exists.
        interactive: When ``True`` and the build is missing, ask the user
                     before triggering ``npm run build``.
    """
    ok, msg = check_build()
    if ok and not force:
        return
    if not ok:
        print(f"⚠  {msg}", file=sys.stderr)
        if interactive:
            answer = input("Build GUI now? [Y/n]: ").strip().lower()
            if answer in ("", "y", "yes"):
                _run_build()
            else:
                print("Serving without GUI build.", file=sys.stderr)
        return
    if force:
        _run_build()


def _run_build() -> None:
    """Execute ``npm run build`` in the ``gui/`` directory.

    Prints status to stderr.  Does nothing if the GUI source directory
    is absent (e.g. in a minimal install).
    """
    gui_dir = _GUI_SOURCE_DIR
    if not gui_dir.exists():
        print(f"GUI source directory not found: {gui_dir}", file=sys.stderr)
        return
    print("Building GUI...", file=sys.stderr)
    result = subprocess.run(["npm", "run", "build"], cwd=gui_dir, check=False)
    if result.returncode != 0:
        print("GUI build failed.", file=sys.stderr)
    else:
        print("GUI built successfully.", file=sys.stderr)
