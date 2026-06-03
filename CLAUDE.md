# OwlGuardCo Charles Schwab Trading System — Operating Manual

A personal, AI-agent-assisted intraday equity trading system for a single
retail Charles Schwab margin account. Greenfield, US equities, same-day swing
trades. Modeled architecturally on connector-first broker layers and multi-agent
research → signal → risk → execution pipelines, with a mandate/kill-switch
safety model and a Discord notification layer.

This is a personal project on personal infrastructure. It trades the operator's
own account only.

---

## Architecture

```
schwab/
  auth/        OAuth2 (authorize-code flow + token refresh, tokens persisted to .env)
  client/      SchwabClient base + accounts / market_data / orders
  agents/      research → signal → risk → execution (anthropic SDK directly)
  safety/      mandate → kill_switch → order_guard   (EVERY order passes the guard)
  pipeline/    runner.py orchestrates the agents + safety
  discord/     notifier.py (embeds; never raises)
  data/        kill_switch_state.json, trade_log.csv  (runtime, gitignored)
scripts/       auth_setup.py, account_status.py, run_pipeline.py
tests/         mandate, order_guard, oauth
```

API base: `https://api.schwabapi.com/trader/v1` (market data under
`/marketdata/v1`). Validate endpoints against your live developer app at
developer.schwab.com — Schwab has revised paths before.

LLM model: `ANTHROPIC_MODEL` env var, default `claude-sonnet-4-6`. (The original
bootstrap named `claude-sonnet-4-20250514`, an older snapshot; pin it via the
env var if you want that exact version.)

---

## Setup

1. Create a developer app at developer.schwab.com (Accounts + Trading and
   Market Data products). Note the app key/secret; set the callback to
   `https://127.0.0.1`.
2. `cp .env.example .env` and fill `SCHWAB_APP_KEY`, `SCHWAB_APP_SECRET`,
   `ANTHROPIC_API_KEY`.
3. `pip install -r requirements.txt`
4. `python scripts/auth_setup.py` — authorize, paste the redirected URL, tokens
   are written to `.env`. Copy the printed `hashValue` into `SCHWAB_ACCOUNT_HASH`.
5. `python scripts/account_status.py` — confirm balances + positions read.

## Running

```bash
python scripts/run_pipeline.py --symbols AAPL TSLA NVDA
python scripts/run_pipeline.py            # uses MANDATE_SYMBOL_ALLOWLIST
```

## Safety model (mandate → kill switch → order_guard → execution)

- **Mandate** (`.env`): `MANDATE_SYMBOL_ALLOWLIST`, `MANDATE_MAX_POSITION_USD`,
  `MANDATE_DAILY_LOSS_LIMIT_USD`. The allowlist is the OUTER boundary — off-list
  symbols are never even researched.
- **Kill switch** (`schwab/data/kill_switch_state.json`): file-backed global
  halt. Checked FIRST in every `run()` and again in every pre-flight. A corrupt
  state file is treated as ACTIVE (fail safe). Any execution exception trips it.
  Clear deliberately: `python -c "from schwab.safety import KillSwitch; KillSwitch().deactivate()"`.
- **Order guard**: `pre_flight()` gates EVERY order — kill switch, valid
  side/qty/price, allowlist, size cap, duplicate detection. No order bypasses it.
- **Risk agent** also hard-clamps qty to the mandate cap independently of the LLM.

## Conventions

- Conventional commits. **No co-author trailers** (plain `git commit -m`).
- All env reads via `os.environ.get()` with clear errors when required keys are missing.
- `loguru` for logging; `print()` only in interactive `scripts/`.
- Never hardcode credentials, tokens, or account hashes. `.env` is gitignored.
- Every order MUST pass `order_guard.pre_flight()`. No exceptions.
- The kill-switch check is the first thing `run()` does. Always.

## Critical data boundary

No employer / Wolters Kluwer / work data EVER enters this system. It uses only
the operator's personal Schwab account and public market data. This boundary is
absolute.
