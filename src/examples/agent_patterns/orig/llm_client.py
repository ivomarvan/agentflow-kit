"""Shared LLM client used across all course examples.

Supports three backends, all via the OpenAI-compatible Chat Completions API:

  1) Ollama (default)
     - Local, free, offline. No API key required.
     - Endpoint: http://localhost:11434/v1
     - Recommended model: qwen3:8b (best tool calling at this size, May 2026).
     - Make sure the model is pulled: `ollama pull qwen3:8b`.

  2) OpenAI cloud
     - Requires OPENAI_API_KEY.
     - Recommended model: gpt-4o-mini (cheapest with strict structured outputs).

  3) Google Gemini cloud
     - Requires GEMINI_API_KEY (https://aistudio.google.com/apikey).
     - Uses Google's OpenAI-compatible endpoint, no SDK swap needed.
     - Recommended model: gemini-3.5-flash (released 19 May 2026; 1M context,
       multimodal, strong tool calling, generous free tier).

Configuration (env variables or examples/.env):
  On import, loads examples/.env if present (via python-dotenv).
  Shell env vars already set take precedence over .env values.

  LLM_MODEL     -> model name; backend is auto-detected from the prefix:
                     gpt-*, o1-*, o3-*, o4-*  -> openai
                     gemini-*                  -> gemini
                     anything else             -> ollama (local)
  LLM_BACKEND   -> override backend explicitly: "ollama" | "openai" | "gemini"
                   (only needed when auto-detection would be wrong)
  LLM_BASE_URL  -> override base URL (only for ollama / custom endpoints)
  LLM_TIMEOUT   -> request timeout in seconds (default: 120 for slow CPU inference)

  API keys in .env: OPENAI_API_KEY, GEMINI_API_KEY or GOOGLE_API_KEY

Examples:
  # Auto-detected backends — just set the model:
  LLM_MODEL=gpt-4o-mini          python 02_tool_calling_demo.py   # -> openai
  LLM_MODEL=gemini-3.5-flash     python 02_tool_calling_demo.py   # -> gemini
  LLM_MODEL=qwen3:8b             python 02_tool_calling_demo.py   # -> ollama

Examples:
  # Local default (offline, free, slow on CPU)
  python 02_tool_calling_demo.py

  # Cheap cloud (best for prompt iteration)
  LLM_BACKEND=openai python 02_tool_calling_demo.py

  # Gemini Flash (free tier; great tool calling)
  LLM_BACKEND=gemini python 02_tool_calling_demo.py

Usage in code:
  from llm_client import chat, BACKEND, MODEL
  response = chat(messages=[...], tools=[...])
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

# Load examples/.env (same directory as this file). Does not override vars
# already set in the shell.
_ENV_FILE = Path(__file__).resolve().parent / ".env"
if _ENV_FILE.is_file():
    load_dotenv(_ENV_FILE, override=False)

# Per-backend defaults.
# Tool-calling-capable models recommended for agentic workloads (May 2026).
_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "gemini": "gemini-3.5-flash",
    "ollama": "qwen3:8b",
}

_DEFAULT_BASE_URLS: dict[str, str] = {
    "ollama": "http://localhost:11434/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    # OpenAI uses SDK default — no override needed.
}

# Model-name prefixes that belong exclusively to one backend.
# Used to warn when LLM_MODEL looks wrong for the chosen LLM_BACKEND.
_MODEL_PREFIX_HINTS: dict[str, str] = {
    "gpt-": "openai",
    "o1-": "openai",
    "o3-": "openai",
    "o4-": "openai",
    "gemini-": "gemini",
    "models/gemini-": "gemini",
}


def _infer_backend(model: str) -> str | None:
    """Return the backend inferred from the model name prefix, or None."""
    for prefix, backend in _MODEL_PREFIX_HINTS.items():
        if model.startswith(prefix):
            return backend
    return None


def _make_client() -> tuple[OpenAI, str, str]:
    """Build an OpenAI-compatible client for the configured backend.

    Backend resolution order:
      1. LLM_BACKEND env var (explicit)
      2. Inferred from LLM_MODEL prefix (e.g. "gpt-" -> openai, "gemini-" -> gemini)
      3. Default: "ollama"

    Returns
    -------
    tuple[OpenAI, str, str]
        (client, model_name, backend_name)
    """
    explicit_backend = os.getenv("LLM_BACKEND", "").lower() or None
    model_env = os.getenv("LLM_MODEL", "")

    if explicit_backend:
        if explicit_backend not in _DEFAULT_MODELS:
            raise ValueError(
                f"Unknown LLM_BACKEND={explicit_backend!r}. "
                f"Valid options: {sorted(_DEFAULT_MODELS)}"
            )
        backend = explicit_backend
        model = model_env or _DEFAULT_MODELS[backend]
        # Warn on obvious mismatch (e.g. LLM_BACKEND=gemini LLM_MODEL=gpt-4o-mini).
        inferred = _infer_backend(model)
        if inferred and inferred != backend:
            print(
                f"WARNING: LLM_MODEL={model!r} looks like a {inferred!r} model "
                f"but LLM_BACKEND={backend!r}. "
                f"Did you mean LLM_BACKEND={inferred}?",
                file=sys.stderr,
            )
    elif model_env:
        inferred = _infer_backend(model_env)
        backend = inferred or "ollama"
        model = model_env
        if not inferred:
            # Unknown prefix — assume ollama (local custom model).
            print(
                f"NOTE: LLM_MODEL={model!r} prefix not recognised; "
                "assuming LLM_BACKEND=ollama. Set LLM_BACKEND explicitly to override.",
                file=sys.stderr,
            )
    else:
        backend = "ollama"
        model = _DEFAULT_MODELS[backend]

    timeout = float(os.getenv("LLM_TIMEOUT", "120"))

    if backend == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "LLM_BACKEND=openai requires the OPENAI_API_KEY environment "
                "variable. Get one at https://platform.openai.com/api-keys."
            )
        client = OpenAI(api_key=api_key, timeout=timeout)
        return client, model, backend

    if backend == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get(
            "GOOGLE_API_KEY"
        )
        if not api_key:
            raise RuntimeError(
                "LLM_BACKEND=gemini requires the GEMINI_API_KEY (or "
                "GOOGLE_API_KEY) environment variable. Get one (free tier "
                "available) at https://aistudio.google.com/apikey."
            )
        base_url = os.getenv("LLM_BASE_URL", _DEFAULT_BASE_URLS["gemini"])
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        return client, model, backend

    # Default: Ollama via OpenAI-compatible API. Any non-empty string works
    # as the API key — Ollama itself ignores it.
    base_url = os.getenv("LLM_BASE_URL", _DEFAULT_BASE_URLS["ollama"])
    client = OpenAI(base_url=base_url, api_key="ollama-local", timeout=timeout)
    return client, model, backend


_CLIENT, _MODEL, _BACKEND = _make_client()

# Public read-only constants for downstream code that wants to log / branch.
MODEL: str = _MODEL
BACKEND: str = _BACKEND


def chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    temperature: float = 0.2,
    model: str | None = None,
) -> dict[str, Any]:
    """Send a chat request and return a normalized response dict.

    Parameters
    ----------
    messages : list[dict]
        OpenAI-format message list.
    tools : list[dict] | None
        Optional OpenAI-format tool definitions. When provided, tool_choice
        is set to "auto" so the model can decide whether to call a tool.
    temperature : float
        Sampling temperature; lower is more deterministic.
    model : str | None
        Optional per-call model override (useful for switching e.g. judge vs.
        worker model in evaluation scripts).

    Returns
    -------
    dict[str, Any]
        Dict with keys: role, content (optional), tool_calls (optional),
        and _usage (token counts when available).
    """
    kwargs: dict[str, Any] = {
        "model": model or _MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    resp = _CLIENT.chat.completions.create(**kwargs)
    msg = resp.choices[0].message

    # Normalize to a plain dict so downstream code doesn't depend on the SDK model.
    out: dict[str, Any] = {"role": "assistant"}
    if msg.content:
        out["content"] = msg.content
    if getattr(msg, "tool_calls", None):
        out["tool_calls"] = []
        for tc in msg.tool_calls:
            # Start with standard fields.
            fn_dict: dict[str, Any] = {
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            }
            # Preserve any backend-specific extra fields on the function object
            # (e.g. Gemini's thought_signature, which must be echoed back).
            fn_extra = getattr(tc.function, "model_extra", None) or {}
            fn_dict.update(fn_extra)

            tc_dict: dict[str, Any] = {
                "id": tc.id,
                "type": "function",
                "function": fn_dict,
            }
            tc_extra = getattr(tc, "model_extra", None) or {}
            tc_dict.update(tc_extra)

            out["tool_calls"].append(tc_dict)

    if resp.usage:
        out["_usage"] = {
            "prompt_tokens": resp.usage.prompt_tokens,
            "completion_tokens": resp.usage.completion_tokens,
            "total_tokens": resp.usage.total_tokens,
        }
    return out


def _smoke_test() -> int:
    """Print backend info and run a single hello-world call. Returns exit code."""
    print(f"Backend : {_BACKEND}", file=sys.stderr)
    print(f"Model   : {_MODEL}", file=sys.stderr)
    if _BACKEND == "ollama":
        print(
            f"Base URL: {os.getenv('LLM_BASE_URL', _DEFAULT_BASE_URLS['ollama'])}",
            file=sys.stderr,
        )
    print("---", file=sys.stderr)

    try:
        r = chat([{"role": "user", "content": "Say hello in one short sentence."}])
    except Exception as e:  # noqa: BLE001 - smoke test should report any failure
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    print(r.get("content", "<no content>"))
    if "_usage" in r:
        usage = r["_usage"]
        print(
            f"\n[tokens: prompt={usage['prompt_tokens']}, "
            f"completion={usage['completion_tokens']}, "
            f"total={usage['total_tokens']}]",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(_smoke_test())
