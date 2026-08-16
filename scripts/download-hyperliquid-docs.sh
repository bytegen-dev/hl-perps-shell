#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCS_DIR="$ROOT/docs/hyperliquid"
INDEX_URL="https://hyperliquid.gitbook.io/hyperliquid-docs/llms.txt"
BASE_URL="https://hyperliquid.gitbook.io/hyperliquid-docs"

mkdir -p "$DOCS_DIR"

echo "==> Fetching doc index"
curl -fsSL "$INDEX_URL" -o "$DOCS_DIR/llms.txt"

count=0
while IFS= read -r url; do
  rel="${url#"$BASE_URL"/}"
  dest="$DOCS_DIR/$rel"
  mkdir -p "$(dirname "$dest")"
  curl -fsSL "$url" -o "$dest"
  count=$((count + 1))
done < <(rg -o 'https://[^)[:space:]]+\.md' "$DOCS_DIR/llms.txt" | sort -u)

date -u +"%Y-%m-%dT%H:%M:%SZ" > "$DOCS_DIR/SYNCED_AT"
echo "Synced $count pages to docs/hyperliquid/"
