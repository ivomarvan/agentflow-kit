"""Management of the local Ollama server: health, model listing, pull, delete.

Ollama stores models at ``~/.ollama/models/`` on Linux — this is a
**system-level directory shared across all projects and virtual environments**
on the machine.  Pulling a model once makes it available everywhere, regardless
of which Python project or venv you are working in.

REST API is used for all read operations (health, list, delete).
The ``ollama pull`` CLI is used for downloading because it streams a live
progress bar to the terminal automatically.

Default Ollama endpoint: http://localhost:11434.
Override with the ``OLLAMA_BASE_URL`` environment variable.

Usage example::

    from src.agentflow.llm.OllamaManager import OllamaManager

    mgr = OllamaManager()
    if not mgr.is_running():
        print("Start Ollama first: ollama serve")
    else:
        mgr.ensure_model("qwen2.5:1.5b")   # pulls only if not present
        for m in mgr.list_models():
            print(m)
"""

from __future__ import annotations

import json
import logging
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass

from git_root_to_syspath import agr
agr()

logger = logging.getLogger(__name__)

_DEFAULT_OLLAMA_URL = "http://localhost:11434"


@dataclass
class OllamaModelInfo:
    """Metadata for a single installed Ollama model."""

    name: str
    size_mb: int
    modified: str  # ISO-8601 string as returned by Ollama

    def __str__(self) -> str:
        return f"{self.name:40s} {self.size_mb:6d} MB  (modified {self.modified[:10]})"


class OllamaManager:
    """Manages the local Ollama server: health, model listing, pull, delete.

    All network calls go to the Ollama REST API.  Model downloads use the
    ``ollama pull`` CLI to provide a native progress bar.
    """

    def __init__(self, base_url: str | None = None) -> None:
        """Initialise the manager.

        Args:
            base_url: Ollama server base URL.  Reads ``OLLAMA_BASE_URL`` env
                      var when ``None``, falls back to ``http://localhost:11434``.
        """
        import os
        self._base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or _DEFAULT_OLLAMA_URL).rstrip("/")
        logger.debug("OllamaManager: base_url=%s", self._base_url)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        """Return True if the Ollama server is reachable and healthy.

        Returns:
            ``True`` when the ``/api/version`` endpoint responds with HTTP 200.
        """
        try:
            with urllib.request.urlopen(f"{self._base_url}/api/version", timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def version(self) -> str | None:
        """Return the Ollama server version string, or None if unreachable.

        Returns:
            Version string (e.g. ``"0.21.0"``), or ``None``.
        """
        try:
            with urllib.request.urlopen(f"{self._base_url}/api/version", timeout=3) as resp:
                return json.loads(resp.read())["version"]
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Model listing
    # ------------------------------------------------------------------

    def list_models(self) -> list[OllamaModelInfo]:
        """Return metadata for all locally installed Ollama models.

        Returns:
            List of ``OllamaModelInfo`` sorted by model name.

        Raises:
            RuntimeError: If the Ollama server is not reachable.
        """
        try:
            with urllib.request.urlopen(f"{self._base_url}/api/tags", timeout=10) as resp:
                data = json.loads(resp.read())
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Ollama server not reachable at {self._base_url}. "
                "Make sure Ollama is running: ollama serve"
            ) from exc

        models = [
            OllamaModelInfo(
                name=m["name"],
                size_mb=m.get("size", 0) // (1024 * 1024),
                modified=m.get("modified_at", ""),
            )
            for m in data.get("models", [])
        ]
        return sorted(models, key=lambda m: m.name)

    def is_installed(self, model: str) -> bool:
        """Return True if the model is already installed locally.

        Args:
            model: Model name, e.g. ``"qwen2.5:1.5b"``.  The ``:latest`` suffix
                   is matched loosely (``"llama3.2"`` matches ``"llama3.2:latest"``).

        Returns:
            ``True`` when the model is found in the local model list.
        """
        installed = {m.name for m in self.list_models()}
        return model in installed or f"{model}:latest" in installed

    # ------------------------------------------------------------------
    # Pull
    # ------------------------------------------------------------------

    def pull(self, model: str) -> None:
        """Download a model using the ``ollama pull`` CLI.

        Progress is streamed to the terminal by the Ollama CLI itself.
        The model becomes available system-wide after the download finishes
        (stored in ``~/.ollama/models/``).

        Args:
            model: Model name to pull, e.g. ``"qwen2.5:1.5b"``.

        Raises:
            RuntimeError: If the ``ollama`` CLI is not found or the pull fails.
        """
        logger.info("Pulling model: %s", model)
        try:
            result = subprocess.run(
                ["ollama", "pull", model],
                check=True,
            )
            _ = result  # check=True raises on non-zero exit
        except FileNotFoundError as exc:
            raise RuntimeError(
                "The 'ollama' CLI was not found. Install Ollama: https://ollama.com"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"ollama pull {model!r} failed with exit code {exc.returncode}") from exc
        logger.info("Model pulled successfully: %s", model)

    def ensure_model(self, model: str) -> None:
        """Pull the model only if it is not already installed.

        Args:
            model: Model name, e.g. ``"qwen2.5:1.5b"``.
        """
        if self.is_installed(model):
            logger.debug("Model already installed, skipping pull: %s", model)
            return
        logger.info("Model not found locally, pulling: %s", model)
        self.pull(model)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, model: str) -> None:
        """Delete a locally installed model.

        Args:
            model: Model name to delete, e.g. ``"qwen2.5:1.5b"``.

        Raises:
            RuntimeError: If the server is unreachable or the model is not found.
        """
        payload = json.dumps({"name": model}).encode()
        req = urllib.request.Request(
            f"{self._base_url}/api/delete",
            data=payload,
            method="DELETE",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10):
                pass
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Failed to delete model {model!r}: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Ollama server not reachable at {self._base_url}") from exc
        logger.info("Model deleted: %s", model)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def describe(self) -> str:
        """Return a human-readable summary of the Ollama server state.

        Returns:
            Multi-line string with server URL, version, and model list.
        """
        lines = [f"Ollama URL : {self._base_url}"]
        ver = self.version()
        if ver:
            lines.append(f"Version    : {ver}")
            models = self.list_models()
            lines.append(f"Models ({len(models)}):")
            for m in models:
                lines.append(f"  {m}")
        else:
            lines.append("Status     : NOT RUNNING")
        return "\n".join(lines)

    def __str__(self) -> str:
        return f"OllamaManager(url={self._base_url!r})"


if __name__ == "__main__":
    import sys

    from src.agentflow.cli import make_arg_parser, setup_logging

    setup_logging()
    parser = make_arg_parser(__doc__)
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("status", help="Show Ollama server status and installed models.")

    p_pull = subparsers.add_parser("pull", help="Download a model (skips if already installed).")
    p_pull.add_argument("model", help="Model name, e.g. 'qwen2.5:1.5b'.")
    p_pull.add_argument("--force", action="store_true", help="Pull even if already installed.")

    p_delete = subparsers.add_parser("delete", help="Delete a locally installed model.")
    p_delete.add_argument("model", help="Model name to delete.")

    p_ensure = subparsers.add_parser("ensure", help="Pull model only if not already installed.")
    p_ensure.add_argument("model", help="Model name to ensure is present.")

    subparsers.add_parser("list", help="List installed models.")

    args = parser.parse_args()
    if args.command is None:
        args.command = "status"

    mgr = OllamaManager()

    if args.command == "status":
        print(mgr.describe())

    elif args.command == "list":
        if not mgr.is_running():
            print("ERROR: Ollama is not running.", file=sys.stderr)
            sys.exit(1)
        for m in mgr.list_models():
            print(m)

    elif args.command in ("pull", "ensure"):
        if not mgr.is_running():
            print("ERROR: Ollama is not running.", file=sys.stderr)
            sys.exit(1)
        model = args.model
        if args.command == "pull" and getattr(args, "force", False):
            mgr.pull(model)
        else:
            mgr.ensure_model(model)

    elif args.command == "delete":
        if not mgr.is_running():
            print("ERROR: Ollama is not running.", file=sys.stderr)
            sys.exit(1)
        try:
            mgr.delete(args.model)
            print(f"Deleted: {args.model}")
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)
