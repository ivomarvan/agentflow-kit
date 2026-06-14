"""LiveModel — self-describing domain model with @action API and GUI demo."""

from __future__ import annotations

import inspect
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from agentflow.live_model._action_adapter import _ActionToolAdapter
from agentflow.tools.Tool import ToolBase
from agentflow.tools.ToolRegistry import ToolRegistry

_DEFAULT_PORT = 8765


def _camel_to_title(name: str) -> str:
    """Convert CamelCase class name to a human-readable title.

    Examples: ``HotelModel`` → ``Hotel Model``, ``SmartHomeModel`` → ``Smart Home Model``.

    Args:
        name: CamelCase string (typically a Python class name).

    Returns:
        Space-separated title string.
    """
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)


def action(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Mark a LiveModel method as a public API action (tool).

    The decorator preserves the original callable and sets ``_is_action = True``
    so that ``LiveModel.tools()`` can discover it.
    """
    fn._is_action = True  # type: ignore[attr-defined]
    return fn


class LiveModel(ABC):
    """Base class for visual domain models that expose a typed API as tools.

    Subclasses declare ``@action`` methods with full type annotations and
    override the ``state`` property to return the current Pydantic live-state.
    """

    @property
    @abstractmethod
    def state(self) -> BaseModel:
        """Current live state — observed by the GUI Live State panel."""

    def tools(self) -> list[ToolBase]:
        """Return one ToolBase adapter per @action method."""
        adapters: list[ToolBase] = []
        for _name, member in inspect.getmembers(self, predicate=inspect.ismethod):
            if getattr(member, "_is_action", False):
                adapters.append(_ActionToolAdapter(self, member))
        return adapters

    def tool_registry(self) -> ToolRegistry:
        """Return a ToolRegistry containing all @action tool adapters."""
        return ToolRegistry(self.tools())

    @classmethod
    def demo(
        cls,
        port: int = _DEFAULT_PORT,
        open_browser: bool = True,
        *,
        _argv: list[str] | None = None,
    ) -> None:
        """Launch a standalone GUI demo (no LLM) for this model.

        Parses ``sys.argv`` for ``--port`` and ``--no-browser`` flags when
        called from a ``__main__`` block.  Pass ``_argv=[]`` in tests or
        programmatic calls to bypass CLI parsing and use ``port``/``open_browser``
        directly.

        Auto-rebuilds the Vue/TS frontend when source files have changed.

        Args:
            port: Default HTTP port (overridden by ``--port`` CLI flag).
            open_browser: Default browser-open behaviour (disabled by ``--no-browser``).
            _argv: Explicit argument list (testing / programmatic).  ``None`` means
                   parse from ``sys.argv``; pass ``[]`` to skip CLI parsing entirely.
        """
        import argparse
        import sys
        from pathlib import Path

        from agentflow import AgentApp
        from agentflow.gui.build import discover_and_build
        from agentflow.gui.server import serve

        display_name = _camel_to_title(cls.__name__)
        model_doc = inspect.cleandoc(cls.__doc__ or "")

        if _argv is not None:
            # Programmatic / test call — use keyword args directly, skip CLI parsing.
            resolved_port = port
            resolved_open_browser = open_browser
        else:
            parser = argparse.ArgumentParser(
                prog=Path(sys.argv[0]).name,
                description=(
                    f"LiveModel: {display_name}\n\n{model_doc}"
                    if model_doc
                    else f"LiveModel: {display_name}"
                ),
                formatter_class=argparse.RawDescriptionHelpFormatter,
            )
            parser.add_argument(
                "--port",
                type=int,
                default=port,
                metavar="PORT",
                help=f"HTTP port for the demo server (default: {port})",
            )
            parser.add_argument(
                "--no-browser",
                action="store_true",
                default=False,
                help="Do not open the browser automatically after startup",
            )
            # parse_known_args() silently ignores unknown flags (e.g. pytest runner args).
            args, _ = parser.parse_known_args()
            resolved_port = args.port
            resolved_open_browser = not args.no_browser

        app_script = Path(sys.argv[0]).resolve()
        discover_and_build(app_script=app_script)

        model = cls()
        app = AgentApp(
            doc=model_doc or f"{cls.__name__} — standalone demo",
            live_model=model,
        )
        # Override GUI header: title = "LiveModel: <human name>", tooltip = class __doc__
        app.gui_script_name = f"LiveModel: {display_name}"
        app.gui_script_doc = model_doc

        serve(
            app,
            port=resolved_port,
            open_browser=resolved_open_browser,
            demo_url_path="/demo",
        )
