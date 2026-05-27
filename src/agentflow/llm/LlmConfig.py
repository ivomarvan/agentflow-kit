"""LLM backend configuration resolved from environment variables.

Supports five backends:
  - ollama     — local, free, no API key needed (default); OpenAI-compatible API
  - openai     — requires OPENAI_API_KEY; OpenAI-compatible API
  - gemini     — requires GOOGLE_API_KEY (or GEMINI_API_KEY); OpenAI-compatible API
  - deepseek   — requires DEEPSEEK_API_KEY; OpenAI-compatible API
  - anthropic  — requires ANTHROPIC_API_KEY; native Anthropic API (NOT OpenAI-compatible;
                  LlmConnector will handle this backend separately)

Environment variables read by ``LlmConfig.from_env()``:
  LLM_MODEL     model name; backend auto-detected from prefix when LLM_BACKEND is unset
  LLM_BACKEND   explicit backend override:
                  "ollama" | "openai" | "gemini" | "deepseek" | "anthropic"
  LLM_BASE_URL  override base URL (useful for custom Ollama endpoints)
  LLM_TIMEOUT   request timeout in seconds (default: 120)

  OPENAI_API_KEY, GOOGLE_API_KEY / GEMINI_API_KEY, DEEPSEEK_API_KEY, ANTHROPIC_API_KEY
  OLLAMA_MODELS, OPENAI_MODELS, GEMINI_MODELS, DEEPSEEK_MODELS, ANTHROPIC_MODELS
  (comma-separated lists)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from git_root_to_syspath import agr
agr()

from src.agentflow.describable.describable import Describable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backend registry
# ---------------------------------------------------------------------------

SUPPORTED_BACKENDS: frozenset[str] = frozenset(
    {"openai", "gemini", "ollama", "deepseek", "anthropic"}
)

# Backends that use the OpenAI-compatible API (handled by openai.OpenAI client).
# Anthropic is intentionally absent — it needs its own SDK in LlmConnector.
OPENAI_COMPATIBLE_BACKENDS: frozenset[str] = frozenset(
    {"openai", "gemini", "ollama", "deepseek"}
)

_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "gemini": "gemini-3.5-flash",
    "ollama": "qwen2.5:1.5b",  # lightweight default — works on modest hardware
    "deepseek": "deepseek-chat",
    "anthropic": "claude-haiku-4-5",
}

_DEFAULT_BASE_URLS: dict[str, str] = {
    "ollama": "http://localhost:11434/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "deepseek": "https://api.deepseek.com",
    # openai: SDK uses its own default — no override needed
    # anthropic: SDK uses its own default — no override needed
}

# Model-name prefixes that identify a backend unambiguously.
_MODEL_PREFIX_TO_BACKEND: dict[str, str] = {
    "gpt-": "openai",
    "o1-": "openai",
    "o3-": "openai",
    "o4-": "openai",
    "gemini-": "gemini",
    "models/gemini-": "gemini",
    "deepseek-": "deepseek",
    "claude-": "anthropic",
}

# Env vars that hold the per-backend list of supported models.
_MODELS_ENV_KEY: dict[str, str] = {
    "openai": "OPENAI_MODELS",
    "gemini": "GEMINI_MODELS",
    "ollama": "OLLAMA_MODELS",
    "deepseek": "DEEPSEEK_MODELS",
    "anthropic": "ANTHROPIC_MODELS",
}

# Env vars checked (in order) for each backend's API key.
_API_KEY_ENV_VARS: dict[str, list[str]] = {
    "openai": ["OPENAI_API_KEY"],
    "gemini": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    # ollama: no key required
}


# ---------------------------------------------------------------------------
# LlmConfig
# ---------------------------------------------------------------------------


@dataclass
class LlmConfig(Describable):
    """Immutable snapshot of the active LLM backend configuration.

    Holds all parameters needed to build an OpenAI-compatible client:
    backend name, model, endpoint URL, credentials, timeout, and the
    advertised model lists per backend from the environment.

    Prefer the ``from_env()`` factory over direct instantiation.
    """

    backend: str
    model: str
    base_url: str | None
    api_key: str | None
    timeout: float
    available_models: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialise Describable attributes after the dataclass fields are set."""
        Describable.__init__(self, name=f"{self.backend}/{self.model}")

    def _get_own_attributes(self) -> dict[str, Any]:
        """Expose only the key configuration fields, omitting API keys and full model lists."""
        return {
            "backend": self.backend,
            "model": self.model,
            "base_url": self.base_url,
            "timeout": self.timeout,
        }

    # ------------------------------------------------------------------
    # Private static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_backend(model: str) -> str | None:
        """Return the backend inferred from the model name prefix, or None.

        Args:
            model: Model name string (e.g. ``"gpt-4o-mini"``).

        Returns:
            Backend name string, or ``None`` when no prefix matches.
        """
        for prefix, backend in _MODEL_PREFIX_TO_BACKEND.items():
            if model.startswith(prefix):
                return backend
        return None

    @staticmethod
    def _load_model_list(backend: str) -> list[str]:
        """Parse the comma-separated ``BACKEND_MODELS`` env var for a given backend.

        Args:
            backend: Backend name key into ``_MODELS_ENV_KEY``.

        Returns:
            List of model name strings.  Empty when the env var is unset or empty.
        """
        env_key = _MODELS_ENV_KEY.get(backend, "")
        raw = os.getenv(env_key, "")
        return [m.strip() for m in raw.split(",") if m.strip()]

    @staticmethod
    def _resolve_api_key(backend: str) -> str | None:
        """Return the first non-empty API key env value for the backend, or None.

        Args:
            backend: Backend name.

        Returns:
            API key string, or ``None`` when the backend needs no key (ollama)
            or all candidate env vars are empty.
        """
        for env_var in _API_KEY_ENV_VARS.get(backend, []):
            value = os.getenv(env_var)
            if value:
                return value
        return None

    @staticmethod
    def _find_env_file(start: Path) -> Path | None:
        """Walk upward from *start* and return the first ``.env`` file found.

        Args:
            start: Directory to begin the search from.

        Returns:
            Path to the first ``.env`` file found, or ``None``.
        """
        current = start.resolve()
        for _ in range(5):  # guard against infinite loops on odd FS layouts
            candidate = current / ".env"
            if candidate.is_file():
                return candidate
            parent = current.parent
            if parent == current:
                break
            current = parent
        return None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> LlmConfig:
        """Build LlmConfig by reading environment variables.

        Loads a ``.env`` file first (without overriding already-set shell
        variables).  Backend resolution order:
          1. ``LLM_BACKEND`` env var (explicit)
          2. Inferred from ``LLM_MODEL`` prefix (e.g. ``"gpt-"`` → openai)
          3. Default: ``"ollama"``

        Args:
            env_file: Path to a ``.env`` file to load.  When ``None``,
                      searches upward from this file's directory.

        Returns:
            Fully resolved ``LlmConfig`` ready to pass to ``LlmConnector``.

        Raises:
            ValueError: If ``LLM_BACKEND`` names an unsupported backend.
            RuntimeError: If the chosen backend requires an API key that is
                          not set in the environment.
        """
        if env_file is None:
            env_file = cls._find_env_file(Path(__file__).parent)

        if env_file and env_file.is_file():
            load_dotenv(env_file, override=False)
            logger.debug("Loaded env file: path=%s", env_file)

        explicit_backend = os.getenv("LLM_BACKEND", "").lower().strip() or None
        model_env = os.getenv("LLM_MODEL", "").strip()

        if explicit_backend:
            if explicit_backend not in SUPPORTED_BACKENDS:
                raise ValueError(
                    f"Unsupported LLM_BACKEND={explicit_backend!r}. "
                    f"Valid options: {sorted(SUPPORTED_BACKENDS)}"
                )
            backend = explicit_backend
            model = model_env or _DEFAULT_MODELS[backend]
            inferred = cls._infer_backend(model)
            if inferred and inferred != backend:
                logger.warning(
                    "Backend mismatch: LLM_MODEL=%r suggests backend=%r "
                    "but LLM_BACKEND=%r is set explicitly",
                    model,
                    inferred,
                    backend,
                )
        elif model_env:
            inferred = cls._infer_backend(model_env)
            backend = inferred or "ollama"
            model = model_env
            if not inferred:
                logger.info(
                    "LLM_MODEL=%r prefix not recognised; assuming backend=ollama. "
                    "Set LLM_BACKEND explicitly to override.",
                    model,
                )
        else:
            backend = "ollama"
            model = _DEFAULT_MODELS[backend]

        timeout = float(os.getenv("LLM_TIMEOUT", "120"))
        base_url: str | None = os.getenv("LLM_BASE_URL") or _DEFAULT_BASE_URLS.get(backend)
        api_key = cls._resolve_api_key(backend)

        if backend in _API_KEY_ENV_VARS and not api_key:
            env_var_names = ", ".join(_API_KEY_ENV_VARS[backend])
            raise RuntimeError(
                f"Backend {backend!r} requires an API key. "
                f"Set one of: {env_var_names}"
            )

        available_models = {b: cls._load_model_list(b) for b in SUPPORTED_BACKENDS}

        cfg = cls(
            backend=backend,
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            available_models=available_models,
        )
        logger.info(
            "LlmConfig resolved: backend=%s model=%s timeout=%.0fs",
            backend,
            model,
            timeout,
        )
        return cfg

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def requires_api_key(self) -> bool:
        """True for cloud backends that must supply an API key."""
        return self.backend in _API_KEY_ENV_VARS

    def models_for_backend(self, backend: str | None = None) -> list[str]:
        """Return the list of configured available models for a backend.

        Args:
            backend: Backend name.  Defaults to the active backend.

        Returns:
            List of model name strings from the environment, or empty list
            when no ``BACKEND_MODELS`` env var was set.
        """
        return self.available_models.get(backend or self.backend, [])

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def describe(self) -> str:
        """Return a multi-line human-readable summary of the active configuration.

        Returns:
            String suitable for logging or printing at startup.
        """
        lines: list[str] = [
            f"Backend : {self.backend}",
            f"Model   : {self.model}",
        ]
        if self.base_url:
            lines.append(f"Base URL: {self.base_url}")
        lines.append(f"Timeout : {self.timeout:.0f}s")
        avail = self.models_for_backend()
        if avail:
            lines.append(f"Available ({self.backend}): {', '.join(avail)}")
        return "\n".join(lines)

    def __str__(self) -> str:
        return f"LlmConfig(backend={self.backend!r}, model={self.model!r})"

    def __repr__(self) -> str:
        return (
            f"LlmConfig(backend={self.backend!r}, model={self.model!r}, "
            f"base_url={self.base_url!r}, timeout={self.timeout})"
        )


if __name__ == "__main__":
    import sys

    from git_root_to_syspath import agr  # locate project root and add it to sys.path
    agr()

    from src.agentflow.cli import make_arg_parser, setup_logging

    setup_logging()
    parser = make_arg_parser(__doc__)
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("show", help="Show active configuration resolved from the environment.")

    subparsers.add_parser("backends", help="List all backends with their configured model lists.")

    p_infer = subparsers.add_parser(
        "infer", help="Show which backend is inferred for a given model name."
    )
    p_infer.add_argument(
        "model", help="Model name to test, e.g. 'gpt-4o-mini' or 'gemini-3.5-flash'."
    )

    args = parser.parse_args()
    # Default to "show" when no subcommand is given.
    if args.command is None:
        args.command = "show"

    if args.command == "infer":
        result = LlmConfig._infer_backend(args.model)
        if result:
            print(f"Model {args.model!r} -> backend: {result}")
        else:
            print(f"Model {args.model!r} -> backend not recognised (would default to ollama)")
        sys.exit(0)

    # Commands that need a resolved config:
    try:
        cfg = LlmConfig.from_env()
    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.command == "show":
        print(cfg.describe())

    elif args.command == "backends":
        for backend in sorted(SUPPORTED_BACKENDS):
            models = cfg.models_for_backend(backend)
            label = f"  {backend:10s}"
            print(f"{label}: {', '.join(models) if models else '(no models configured)'}")
