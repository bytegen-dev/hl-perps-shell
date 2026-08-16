# Hyperliquid documentation (local mirror)

Offline copy of the official [Hyperliquid GitBook docs](https://hyperliquid.gitbook.io/hyperliquid-docs).

## Refresh

```bash
./scripts/download-hyperliquid-docs.sh
```

Source index: [llms.txt](https://hyperliquid.gitbook.io/hyperliquid-docs/llms.txt)  
Markdown pages: append `.md` to any GitBook page URL.

## Key pages for hl-xfgen

| Topic | Local path |
|-------|------------|
| Info API (perps + spot) | `for-developers/api/info-endpoint.md` |
| Spot balances / tradable USDC | `for-developers/api/info-endpoint/spot.md` |
| Perp clearinghouse | `for-developers/api/info-endpoint/perpetuals.md` |
| Exchange / trading | `for-developers/api/exchange-endpoint.md` |
| API wallets (agent keys) | `for-developers/api/nonces-and-api-wallets.md` |
| Unified account modes | `trading/account-abstraction-modes.md` |
| Portfolio margin | `trading/portfolio-margin.md` |
| HIP-3 perps | `hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals.md` |
| Testnet faucet | `onboarding/testnet-faucet.md` |

## Notes

- **Tradable balance (unified account):** `spotClearinghouseState` USDC is the source of truth — see spot API doc.
- **Perp margin:** `clearinghouseState` / `marginSummary` — separate from spot USDC until used by positions.
- Do not edit mirrored files by hand; refresh from upstream instead.
