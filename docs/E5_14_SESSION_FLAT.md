# E5.14 — Executable entry comparator and protected session-flat research

**Status:** implementation candidate; CI and market study not yet verified. E5 Issue #6 remains OPEN; E6 release acceptance blocked. LIVE NOT AUTHORIZED.

## Fixed policies (research only)

- Legacy `BuyHoldBaseline` v1 and default `HistoricalBacktest` remain unchanged. V2 opts into one initial-entry proposal per session until any BUY fill is observed; `first_entry_only=True` is mandatory with a fixed, single-instrument evaluation window and one strategy. DAY order expiry/cancellation and strict penetration/volume/fee constraints remain; partial fill stays invested, and later LONG signals cannot rebalance or top up the position. No-fill leaves actual synthetic account cash unchanged but is not a comparable invested benchmark. It must be reported with null comparison return.
- `session_flat=True` is a separate versioned, opt-in policy for a single strategy, strict fixed minute window and enabled E5.3 protection. No new orders can be submitted at/after the last minute begins. The schedule is determined by the supplied calendar before any last-bar prices are known (including short sessions). No provider calendar certification is implied.
- Existing stops/targets arm only after observed BUY fill and cannot trigger in the same entry bar. If a pending BUY could also match a protective exit in the same OHLCV bar, fail closed (unknown path); otherwise cancel the outstanding BUY remainder when protection triggers. Existing SELL conflicts remain fail-closed.
- At the final bar, the model records the precommitted cancellation of outstanding DAY orders **before** matching that bar; the cancellation/fill journal time is the bar observation time, not a claimed historical venue execution timestamp. Late entry observation (after the final bar starts) fails closed.
- Standing final-bar open liquidation uses the final bar open reduced by the configured adverse basis points and rounded down to a valid tick. It uses the shared participation cap, actual modeled inventory, and E3 Risk, fees and virtual attribution. It does not use the bar close as a decision signal or assume an actual market-on-close fill. The minute's volume is only a bound, not proof of opening liquidity.
- Any remaining inventory at the end of the final bar makes the arm invalid rather than reporting an apparently flat profitable run. This model cannot guarantee actual liquidation in a halt, gap or illiquid market. The final bar scheduled open takes precedence over protection after it starts; this is a modeling convention, not an observed sequence.
- Programmatic only. No new CLI JSON schema or broker transport. The options contribute separately to config/run hashes; legacy defaults keep existing hashing and notes. E3 remains authoritative only for synthetic accounts.

## Preregistered diagnostic

Repeat exactly the E5.13 minute panel (TSLA, SPY, KO, TWTR × Sep–Nov 2022; 20 prior sessions; no action intervals; full 1m coverage). Rejected windows remain visible. No tuning using previously observed returns. This is a diagnostic retest, not an untouched holdout. For each eligible window run seven independent arms:

| Arm | Costs | Policy |
| --- | --- | --- |
| no-trade | base | cash reference |
| hold-retry | base/stress | v2, retry until observed first BUY; no stop/order at end |
| orb-entry | base/stress | legacy entry-only |
| orb-session-flat | base/stress | standing stop (no target) + scheduled final-minute liquidation |

Keep the existing USD 100,000, 5% target, 5% participation, 0.01 tick, 1 share lot; existing E5.13 base and stress fee/spread/impact assumptions. For the protected arms adverse exit haircut equals the assumed entry penetration buffer (10/40 bp). These are predeclared modeling values, not independently verified broker fees or actual market spreads.

Run `python -u scripts/e513_market_study.py minute-e514 TSLA 10` or the E5.14 Actions matrix. Each row includes account PnL/MDD, fees, BUY/SELL quantities, ending quantity, stop and session-close counts, config/run hashes, and explicit entry coverage. `NO_ENTRY_FILL` => comparison return null; partial buys may still count as entry filled and their actual quantity is reported. Never infer outperformance when the hold comparator is unfilled. A failed arm remains in errors and cannot be counted as a completed run. The legacy E5.13 modes remain available, with separate artifacts and schema.

## Acceptance checks

- Retry after a missed day; no target trim or top-up after first confirmed purchase; legacy one-shot behavior remains.
- Warmup does not trade. No same-entry-bar protection. Stop gap, final open adverse tick, cancel pending on final minute, no last-minute new entry, partial and zero liquidity fail closed, late observations and ambiguous pending BUY/stop conflict fail closed; repeatable run hash.
- Full Python 3.12/3.13 CI, lint/mypy/secret checks; inspect actual study artifact status and compare matching historical data hashes and fees. No success inferred from workflow exit code alone.
- E5.14 remaining: independently verify supplier rights, source coverage, price/share units, actual historical receipt/vintages, issuer actions, complete calendar and historical fee/tax/FX schedules; broader preregistered instruments/regimes. The old panel alone cannot certify E5 acceptance or profitability.
