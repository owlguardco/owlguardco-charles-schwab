# OwlGuardCo — Charles Schwab Trading System

A personal, AI-agent-assisted intraday equity trading system for a single
Charles Schwab margin account. US equities, same-day swing trades. Connector-first
broker layer, a research → signal → risk → execution agent pipeline, and a
mandate / kill-switch safety model. Trades the operator's own account only.

> Personal project on personal infrastructure. Not investment advice. Markets
> carry risk; the safety limits exist because automated order placement can lose
> money fast. Start with tiny `MANDATE_MAX_POSITION_USD` and watch it.

## Architecture

```
                ┌────────────────────────── TradingPipeline.run(symbols) ──────────────────────────┐
                │  0. kill switch check (ALWAYS first)                                              │
                │  1. account value                                                                 │
   watchlist ─► │  2. ResearchAgent ─► 3. SignalAgent ─► 4. RiskAgent ─► 5. ExecutionAgent          │
                │      (candles+quote)    (LONG/SHORT/    (size vs cap     (pre-flight ► order)      │
                │                          PASS, conf)     + clamp)               │                 │
                └───────────────────────────────────────────────────────────────┼─────────────────┘
                                                                                  ▼
   safety:   Mandate (allowlist, max $, daily loss) ─► KillSwitch (file flag) ─► OrderGuard.pre_flight
   broker:   SchwabClient ─► AccountsClient · MarketDataClient · OrdersClient  (OAuth2, token refresh)
   alerts:   DiscordNotifier (embeds; never raises)
```

Every order passes `OrderGuard.pre_flight()`. Any execution error trips the kill
switch, which then blocks all further orders until cleared deliberately.

## Setup

1. Create a developer app at **developer.schwab.com** (Accounts + Trading and
   Market Data). Callback URL: `https://127.0.0.1`.
2. `cp .env.example .env`, then fill `SCHWAB_APP_KEY`, `SCHWAB_APP_SECRET`,
   `ANTHROPIC_API_KEY`, and the `MANDATE_*` limits.
3. `pip install -r requirements.txt`
4. `python scripts/auth_setup.py` — open the printed URL, authorize, paste the
   `https://127.0.0.1?code=...` URL you land on (the page won't load — that's
   expected). Tokens are written to `.env`. Copy the printed `hashValue` into
   `SCHWAB_ACCOUNT_HASH`.
5. `python scripts/account_status.py` — confirm it reads your balances/positions.

## Running

```bash
python scripts/run_pipeline.py --symbols AAPL TSLA
python scripts/run_pipeline.py            # uses MANDATE_SYMBOL_ALLOWLIST
```

## Safety model

| Layer | What it enforces |
|-------|------------------|
| **Mandate** | Symbol allowlist (outer boundary), max per-position $, daily loss limit. From `.env`. |
| **Kill switch** | File-backed global halt. Checked first in every run and every pre-flight. Corrupt state ⇒ treated as active (fail safe). Execution errors trip it. |
| **Order guard** | `pre_flight()` on every order: kill switch, valid side/qty/price, allowlist, size cap, duplicate detection. |
| **Risk agent** | Independently hard-clamps quantity to the mandate cap. |

Clear the kill switch deliberately:
```bash
python -c "from schwab.safety import KillSwitch; KillSwitch().deactivate()"
```

## Tests

```bash
pip install pytest
pytest -q
```

`test_mandate.py` and `test_order_guard.py` cover the safety logic; `test_oauth.py`
covers URL building and `.env` token write-back (no network).

## Note on Schwab API paths

Endpoints follow the Schwab trader API (`https://api.schwabapi.com/trader/v1`,
market data under `/marketdata/v1`). Confirm them against your live developer app
— Schwab has revised paths before. All calls are your own authenticated requests.
