#!/usr/bin/env bash
# Project CI mirror — invoked by the /push command and local pre-push checks.
# Scope: unit tests only (integration excluded via pyproject.toml addopts).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> pytest (unit tests, integration excluded by default)"
uv run --extra dev pytest

echo "All checks passed."
