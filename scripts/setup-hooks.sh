#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

git config core.hooksPath .githooks
chmod +x .githooks/pre-push scripts/check.sh

echo "Git hooks enabled (.githooks/pre-push -> scripts/check.sh)"
echo "Pre-push runs: uv sync --dev, ruff check, pytest"
