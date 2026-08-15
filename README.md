# hl-xfgen

**Hyperliquid X-Factor Gen** — personal Hyperliquid trading and research tooling.

## Quick start

```bash
# Install uv: https://docs.astral.sh/uv/
cd hl-xfgen
uv sync
cp .env.example .env
# Edit .env with your testnet credentials

# Read-only market data (no keys required)
uv run hl mids

# Account state (requires HL_ACCOUNT_ADDRESS or HL_SECRET_KEY)
uv run hl status
```

## Monorepo layout

```text
packages/
├── hl-client/      # Shared Hyperliquid API wrapper (foundation)
├── core/           # Config, logging, shared types
├── terminal/       # CLI trading terminal (`hl` command)
├── telegram-bot/   # Personal Telegram interface (stub)
└── historical/     # Signal verification & history (stub)
```

## Development

```bash
uv sync --dev
uv run pytest
uv run ruff check .
```

### Git hooks (pre-push)

Local pushes run the same checks as CI (`ruff` + `pytest`):

```bash
./scripts/setup-hooks.sh
```

One-time manual setup:

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-push scripts/check.sh
```

Skip once if needed: `git push --no-verify`.

### CI

GitHub Actions runs `./scripts/check.sh` on push/PR to `main`/`master` (see `.github/workflows/ci.yml`).

All packages that talk to Hyperliquid depend on `hl-client`.
