"""GUI build helpers — check, discover renderers, and trigger npm build for the Vue SPA.

The Vue SPA lives in ``gui/`` at the project root and is built to
``agentflow/gui/static/``.  This module checks whether the build output
is present, discovers custom event renderers from ``gui_renderers/``
directories next to example scripts, auto-generates ``index.ts``, and
optionally triggers ``npm run build``.

Build freshness is tracked via a SHA-256 hash of all GUI source files and
discovered renderer files, stored in ``agentflow/gui/static/.build-hash``.
The build runs only when the hash changes — similar to ``make``'s
timestamp-based dependency tracking.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

STATIC_DIR = Path(__file__).parent / "static"
DIST_INDEX = STATIC_DIR / "index.html"
HASH_FILE = STATIC_DIR / ".build-hash"
GUI_DIR = Path(__file__).parent.parent.parent / "gui"
RENDERER_INDEX = GUI_DIR / "src" / "event-renderers" / "index.ts"


def check_build() -> tuple[bool, str]:
    """Check whether the pre-built GUI is present.

    Returns:
        Tuple of ``(ok, message)`` where *ok* is ``True`` when
        ``agentflow/gui/static/index.html`` exists.
    """
    if not DIST_INDEX.exists():
        return False, "GUI not built. Run: cd gui && npm run build"
    return True, "ok"


def _compute_source_hash(renderers: list[tuple[str, Path]]) -> str:
    """Compute SHA-256 hash of GUI source files and discovered renderer files.

    Hashes the content and relative paths of all non-hidden files under
    ``gui/src/``, ``gui/package.json``, and each renderer ``.vue`` file.

    Args:
        renderers: Renderer list from ``discover_renderers()``.

    Returns:
        Hex-digest string of the combined SHA-256 hash.
    """
    h = hashlib.sha256()
    if GUI_DIR.exists():
        src_dir = GUI_DIR / "src"
        if src_dir.exists():
            for path in sorted(src_dir.rglob("*")):
                if path.is_file() and not path.name.startswith("."):
                    h.update(str(path.relative_to(GUI_DIR)).encode())
                    h.update(path.read_bytes())
        pkg = GUI_DIR / "package.json"
        if pkg.exists():
            h.update(pkg.read_bytes())
    for event_type, vue_file in sorted(renderers, key=lambda x: x[0]):
        h.update(event_type.encode())
        if vue_file.exists():
            h.update(vue_file.read_bytes())
    return h.hexdigest()


def _is_build_current(renderers: list[tuple[str, Path]]) -> bool:
    """Return True if the committed build matches the current source hash.

    Args:
        renderers: Renderer list used to compute the expected hash.

    Returns:
        ``True`` when the stored hash equals the computed hash and
        ``index.html`` exists; ``False`` otherwise.
    """
    if not DIST_INDEX.exists() or not HASH_FILE.exists():
        return False
    stored = HASH_FILE.read_text(encoding="utf-8").strip()
    return stored == _compute_source_hash(renderers)


def _save_build_hash(renderers: list[tuple[str, Path]]) -> None:
    """Persist the source hash after a successful build.

    Args:
        renderers: Renderer list used to compute the hash.
    """
    HASH_FILE.write_text(_compute_source_hash(renderers) + "\n", encoding="utf-8")


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
            try:
                answer = input("Build GUI now? [Y/n]: ").strip().lower()
            except EOFError:
                answer = "n"
            if answer in ("", "y", "yes"):
                discover_and_build()
            else:
                print("Serving without GUI build.", file=sys.stderr)
        return
    if force:
        discover_and_build(force=True)


def discover_renderers(app_script: Path | None = None) -> list[tuple[str, Path]]:
    """Discover .vue renderer files from gui_renderers/ directories.

    Searches for ``gui_renderers/`` directories next to the calling script
    (convention) and in all ``examples/`` subdirectories in the repo.

    The event_type is derived from the filename: underscores are replaced
    with dots and the ``.vue`` suffix is stripped.
    E.g.: ``hotel_reservation.vue`` → ``hotel.reservation``

    Args:
        app_script: Optional path to the running application script.
                    When provided, its sibling ``gui_renderers/`` dir is
                    searched first.

    Returns:
        List of ``(event_type, vue_file_path)`` tuples in discovery order.
        Duplicate event_types are silently deduplicated (first wins).
    """
    seen_event_types: set[str] = set()
    renderers: list[tuple[str, Path]] = []
    search_dirs: list[Path] = []

    if app_script is not None:
        renderer_dir = app_script.parent / "gui_renderers"
        if renderer_dir.is_dir():
            search_dirs.append(renderer_dir)

    # Also search all gui_renderers/ directories under the repo root
    repo_root = Path(__file__).parent.parent.parent
    for renderer_dir in sorted(repo_root.rglob("gui_renderers")):
        if renderer_dir.is_dir() and renderer_dir not in search_dirs:
            search_dirs.append(renderer_dir)

    for renderer_dir in search_dirs:
        for vue_file in sorted(renderer_dir.glob("*.vue")):
            event_type = vue_file.stem.replace("_", ".")
            if event_type not in seen_event_types:
                seen_event_types.add(event_type)
                renderers.append((event_type, vue_file))

    return renderers


def generate_renderer_index(renderers: list[tuple[str, Path]]) -> None:
    """Auto-generate gui/src/event-renderers/index.ts from discovered renderers.

    Copies each .vue file into the gui/src/event-renderers/ directory (if
    content differs) and writes a TypeScript registry mapping event_type
    strings to Vue components.

    Does nothing if the ``gui/`` source directory does not exist.

    Args:
        renderers: List of ``(event_type, vue_file_path)`` tuples as returned
                   by ``discover_renderers()``.
    """
    if not GUI_DIR.exists():
        return

    lines = [
        "// AUTO-GENERATED by agentflow-gui build script — do not edit manually",
        "// Regenerated each time 'gui' subcommand is invoked",
        "",
        "import type { Component } from 'vue'",
        "import GenericJsonRenderer from './GenericJsonRenderer.vue'",
        "",
    ]

    imports: list[str] = []
    registry_entries: list[str] = []

    for event_type, vue_file in renderers:
        target = GUI_DIR / "src" / "event-renderers" / vue_file.name
        if not target.exists() or target.read_bytes() != vue_file.read_bytes():
            target.write_bytes(vue_file.read_bytes())

        var_name = _to_camel_case(vue_file.stem)
        imports.append(f"import {var_name} from './{vue_file.name}'")
        registry_entries.append(f'  "{event_type}": {var_name},')

    lines.extend(imports)
    lines.append("")
    lines.append("export const EVENT_RENDERERS: Record<string, Component> = {")
    lines.extend(registry_entries)
    lines.append("}")
    lines.append("")
    lines.append("export { GenericJsonRenderer }")
    lines.append("")
    lines.append("export function getRenderer(eventType: string): Component {")
    lines.append("  return EVENT_RENDERERS[eventType] ?? GenericJsonRenderer")
    lines.append("}")
    lines.append("")

    RENDERER_INDEX.write_text("\n".join(lines), encoding="utf-8")


def _to_camel_case(snake: str) -> str:
    """Convert snake_case filename stem to PascalCase component name.

    Example: ``hotel_reservation`` → ``HotelReservation``

    Args:
        snake: Underscore-separated lowercase string.

    Returns:
        PascalCase string suitable for a Vue component variable name.
    """
    return "".join(word.capitalize() for word in snake.split("_"))


def discover_and_build(app_script: Path | None = None, *, force: bool = False) -> None:
    """Discover custom renderers, generate index.ts, build Vue app, copy to static.

    Skips the build entirely when the source hash is unchanged unless
    ``force=True``.  The hash is computed over all ``gui/src/`` files,
    ``gui/package.json``, and every discovered renderer ``.vue`` file.

    Args:
        app_script: Optional path to the running application script; passed
                    to ``discover_renderers()`` for convention-based discovery.
        force: When ``True``, rebuild unconditionally regardless of hash.
    """
    renderers = discover_renderers(app_script)

    if not force and _is_build_current(renderers):
        print("GUI build is up-to-date — skipping rebuild.", file=sys.stderr)
        return

    if renderers:
        print(
            f"Found {len(renderers)} custom renderer(s): {[e for e, _ in renderers]}",
            file=sys.stderr,
        )
    generate_renderer_index(renderers)
    if _run_build():
        _save_build_hash(renderers)


def _run_build() -> bool:
    """Execute ``npm run build`` in the ``gui/`` directory and copy dist to static.

    Prints status to stderr.  Does nothing if the GUI source directory
    is absent (e.g. in a minimal install).

    Returns:
        ``True`` on success, ``False`` on failure or missing source dir.
    """
    if not GUI_DIR.exists():
        print(f"GUI source directory not found: {GUI_DIR}", file=sys.stderr)
        return False
    print("Building GUI…", file=sys.stderr)
    result = subprocess.run(["npm", "run", "build"], cwd=GUI_DIR, check=False)
    if result.returncode != 0:
        print("GUI build failed.", file=sys.stderr)
        return False
    print("GUI built successfully.", file=sys.stderr)
    dist_dir = GUI_DIR / "dist"
    if dist_dir.exists():
        shutil.copytree(dist_dir, STATIC_DIR, dirs_exist_ok=True)
        print(f"Copied dist to {STATIC_DIR}", file=sys.stderr)
    return True
