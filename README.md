# hl-perps-shell

A shell-style CLI for **Hyperliquid perpetuals** — open, close, limit, TP/SL, and research from your terminal.

Run `hl` to trade and inspect perp positions without touching the web UI.

## Quick start

```bash
# Install uv: https://docs.astral.sh/uv/
git clone https://github.com/bytegen-dev/hl-perps-shell.git
cd hl-perps-shell
uv sync
cp .env.example .env
# Edit .env with your testnet credentials

# Read-only market data (no keys required)
uv run hl mids

# Account state (requires HL_ACCOUNT_ADDRESS or HL_SECRET_KEY)
uv run hl status
```

## Commands

| Command | Description |
|---------|-------------|
| `hl status` | Account summary, perp positions, pending orders |
| `hl open` / `hl close` | Market open or close (full or partial) |
| `hl limit` | Place limit orders |
| `hl tp` / `hl sl` | Position take-profit and stop-loss |
| `hl orders` / `hl fills` | Open orders and recent fills |
| `hl find` | Search perp markets across dexes |
| `hl mids` | Perp mid prices |
| `hl leverage` | Set coin leverage |
| `hl historical` | Query candles and funding around a timestamp |

Run `hl --help` for the full list.

## Monorepo layout

```text
packages/
├── hl-client/      # Hyperliquid API wrapper (official SDK)
├── core/           # Config, logging, wallet storage
├── terminal/       # `hl` CLI (`hl-terminal`)
├── historical/     # Candle/funding lookups for research
└── telegram-bot/   # Planned Telegram interface (stub)
```

Local Hyperliquid docs mirror: `docs/hyperliquid/` (refresh with `./scripts/download-hyperliquid-docs.sh`).

## Configuration

Copy `.env.example` to `.env`. Key variables:

- `HL_NETWORK` — `testnet` (default) or `mainnet`
- `HL_ACCOUNT_ADDRESS` — master account (required with agent/API keys)
- `HL_SECRET_KEY` — signing key (prefer an API/agent wallet, not your main wallet)
- `HL_DATABASE_URL` — optional local Postgres for encrypted wallet backup

Start Postgres for wallet storage:

```bash
cp .env.example .env
# Set POSTGRES_PASSWORD and matching HL_DATABASE_URL in .env
docker compose up -d
uv run hl db generate-key   # add HL_WALLET_ENCRYPTION_KEY to .env
```

Credentials live in `.env` only (gitignored), not in `docker-compose.yml`.

## Development

```bash
uv sync --dev
uv run pytest
uv run ruff check .
```

Pre-push hooks: `./scripts/setup-hooks.sh`

CI runs `./scripts/check.sh` on push/PR (see `.github/workflows/ci.yml`).

## Security

- Never commit `.env`, private keys, or files under `wallets/`.
- Test on **testnet** before mainnet. Mainnet commands show a confirmation banner.
- Prefer Hyperliquid **API/agent wallets** over your main wallet private key.

## License

MIT — see [LICENSE](LICENSE).
