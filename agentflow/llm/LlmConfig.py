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
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level cache for discover_available_models()
# ---------------------------------------------------------------------------
_discover_cache: dict[str, list[str]] = {}
_discover_cache_time: float = 0.0
_DISCOVER_CACHE_TTL: float = 300.0  # 5 minutes — avoids hammering remote APIs

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
    "deepseek": "deepseek-v4-flash",
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


class LlmConfig(BaseModel):
    """Snapshot of the active LLM backend configuration.

    Holds all parameters needed to build an OpenAI-compatible client:
    backend name, model, endpoint URL, credentials, timeout, and the
    advertised model lists per backend from the environment.

    Prefer the ``from_env()`` factory over direct instantiation.
    """

    model_config = ConfigDict(frozen=False, arbitrary_types_allowed=True)

    backend: str = Field(
        description="Active LLM backend name (ollama/openai/gemini/deepseek/anthropic)."
    )
    model: str = Field(description="Model identifier passed to the backend API.")
    base_url: str | None = Field(
        default=None, description="Override base URL for the backend API endpoint."
    )
    api_key: str | None = Field(
        default=None, description="API key for authenticated backends; None for ollama."
    )
    timeout: float = Field(default=120.0, description="Request timeout in seconds.")
    available_models: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Per-backend lists of available model names from environment variables.",
    )

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

    def with_overrides(
        self,
        *,
        backend: str | None = None,
        model: str | None = None,
    ) -> LlmConfig:
        """Return a copy with backend/model overrides and re-resolved connection fields.

        When *model* is overridden without an explicit *backend*, the backend is
        re-inferred from the model name prefix (e.g. ``gpt-`` → openai).

        Args:
            backend: Explicit backend override.  When ``None`` and *model* implies a
                     different backend, the inferred backend is used.
            model: Model name override.  When ``None``, the current model is kept.

        Returns:
            New ``LlmConfig`` with updated backend, model, base_url, and api_key.

        Raises:
            ValueError: If *backend* names an unsupported backend.
            RuntimeError: If the resolved backend requires an API key that is missing.
        """
        new_model = model if model is not None else self.model
        if backend is not None:
            if backend not in SUPPORTED_BACKENDS:
                raise ValueError(
                    f"Unsupported backend={backend!r}. "
                    f"Valid options: {sorted(SUPPORTED_BACKENDS)}"
                )
            new_backend = backend
        elif model is not None:
            inferred = self._infer_backend(model)
            new_backend = inferred if inferred else self.backend
        else:
            new_backend = self.backend

        base_url_env = os.getenv("LLM_BASE_URL", "").strip() or None
        new_base_url = base_url_env if base_url_env else _DEFAULT_BASE_URLS.get(new_backend)
        new_api_key = self._resolve_api_key(new_backend)
        # When the backend is unchanged and no env key is found, preserve the
        # existing api_key so that runtime overrides (e.g. via GUI) work even
        # when the key was supplied programmatically rather than via env vars.
        if not new_api_key and new_backend == self.backend:
            new_api_key = self.api_key

        if new_backend in _API_KEY_ENV_VARS and not new_api_key:
            env_var_names = ", ".join(_API_KEY_ENV_VARS[new_backend])
            raise RuntimeError(
                f"Backend {new_backend!r} requires an API key. "
                f"Set one of: {env_var_names}"
            )

        return self.model_copy(update={
            "backend": new_backend,
            "model": new_model,
            "base_url": new_base_url,
            "api_key": new_api_key,
        })

    # ------------------------------------------------------------------
    # Dynamic model discovery
    # ------------------------------------------------------------------

    @staticmethod
    def _discover_openai_compatible_models(
        backend: str, api_key: str | None, base_url: str | None
    ) -> list[str]:
        """Fetch model list from an OpenAI-compatible ``GET /v1/models`` endpoint.

        This is a pure metadata call — it does **not** consume any tokens.

        Args:
            backend: Backend name (used only for log messages).
            api_key: API key; pass ``None`` for keyless backends (ollama).
            base_url: Base URL override.  Uses the SDK default when ``None``.

        Returns:
            Sorted list of model ID strings, or empty list on any failure.
        """
        try:
            from openai import OpenAI  # lazy import — keep module startup fast

            client = OpenAI(
                api_key=api_key or "dummy",  # SDK rejects empty string
                base_url=base_url,
                timeout=8,
                max_retries=0,
            )
            models = client.models.list()
            result = sorted(m.id for m in models.data)
            logger.debug("Model discovery: backend=%s found=%d", backend, len(result))
            return result
        except Exception as exc:
            logger.debug("Model discovery failed: backend=%s error=%s", backend, exc)
            return []

    @classmethod
    def discover_available_models(cls) -> dict[str, list[str]]:
        """Return available models for every backend by querying their APIs.

        Makes a token-free ``GET /v1/models`` call to each OpenAI-compatible
        backend that has an API key configured.  Results are cached for
        ``_DISCOVER_CACHE_TTL`` seconds so repeated GUI refreshes do not
        hammer remote endpoints.

        The live API response is the **authoritative** source — env-var model
        lists (``BACKEND_MODELS``) are intentionally not merged so that only
        models the backend actually supports are shown.

        Fallback chain per backend:
          1. Live API discovery result (primary source).
          2. ``_DEFAULT_MODELS`` constant — only when the API is unreachable,
             so the dropdown is never empty.

        Returns:
            Dict ``{backend: [model_name, ...]}`` for every backend that has
            a reachable API or a configured default model.
        """
        global _discover_cache, _discover_cache_time  # noqa: PLW0603

        if _discover_cache and (time.monotonic() - _discover_cache_time) < _DISCOVER_CACHE_TTL:
            logger.debug("discover_available_models: returning cached result")
            return _discover_cache

        # Ensure .env is loaded before reading API keys
        env_file = cls._find_env_file(Path(__file__).parent)
        if env_file and env_file.is_file():
            load_dotenv(env_file, override=False)

        result: dict[str, list[str]] = {}

        for backend in sorted(OPENAI_COMPATIBLE_BACKENDS):
            api_key = cls._resolve_api_key(backend)
            base_url = os.getenv("LLM_BASE_URL") or _DEFAULT_BASE_URLS.get(backend)

            if backend in _API_KEY_ENV_VARS and not api_key:
                # No key — cannot query live API; fall back to default model only
                discovered: list[str] = []
            else:
                discovered = cls._discover_openai_compatible_models(backend, api_key, base_url)

            if discovered:
                # Live API is the authoritative source — do not mix in env-var lists
                result[backend] = discovered
            else:
                # API unreachable — fall back to the known default so the dropdown
                # is never empty and the user can still run a request
                default = _DEFAULT_MODELS.get(backend)
                if default:
                    result[backend] = [default]

        # Anthropic has no public models endpoint — use known default only
        anthro_default = _DEFAULT_MODELS.get("anthropic")
        if anthro_default:
            result["anthropic"] = [anthro_default]

        _discover_cache = result
        _discover_cache_time = time.monotonic()
        logger.info(
            "discover_available_models: %s",
            {b: len(m) for b, m in result.items()},
        )
        return result

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

    from agentflow.cli import make_arg_parser, setup_logging

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
