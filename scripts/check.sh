#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Syncing dependencies"
if [[ "${CI:-}" == "true" ]]; then
  uv sync --dev --frozen
else
  uv sync --dev
fi

echo "==> Ruff"
uv run ruff check .

echo "==> Pytest"
uv run pytest -q

echo "All checks passed."
