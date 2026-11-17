# ADR-0017 — Synthetic cash dividend in historical replay

- Date: 2026-11-17
- Status: Accepted for **offline simulated research only**

## Context

E5.7 added a corporate-action ledger, but E5.8 only replayed session-open share splits. Historical raw prices may step down on the ex-date while a held investor acquires a dividend receivable. Ignoring the receivable understates economic equity; immediately spending the dividend overstates cash. OHLCV cannot independently validate the issuer's entitlement or bank payment timestamp.

## Decision

1. Add a **strict, optional, checksum-bound** dividend schedule, with one entitlement and one payment directive per immutable action ID. A PIT `CASH_DIVIDEND` record must match the entitlement identity, timing and provenance. Unmodeled actions remain fail-closed.
2. Recognize entitlement at a witnessed **session-open** bar boundary before any bar fill; book the event at the bar's observation timestamp. Do not infer entitlement using the trade sequence inside a bar.
3. Model unpaid *net* cash as a receivable in research equity **without** increasing E3 cash or buying power. On a later separately witnessed payment boundary, move the receivable to E3 settled cash; replay remains deterministic.
4. Restrict this feature to **raw unadjusted** price history; reject simultaneous split/dividend boundaries and unknown/late-available issuer terms. Delisting and unsupported actions continue to stop the run rather than manufacture proceeds.
5. Treat all records and tax fractions as **caller-declared synthetic metadata**; a valid hash/PIT check cannot prove the actual issuer or provider was truthful. Preserve the existing no-action backtest contracts.

## Alternatives rejected

- Add dividend to free cash on ex-date: creates premature buying power.
- Ignore unpaid dividend receivables: reports false equity drawdown after a raw ex-date price step.
- Automatically apply inferred cash dividends from adjusted prices: double-counting and look-ahead risk.
- Assume delisted shares have a liquidation value of zero or market value from stale quotes: creates invented portfolio outcomes.

## Consequences / revisit

The E5 economic equity series includes a separately modeled net receivable, while reported `realized_exit_pnl` remains a trade-exit metric. Cash receipt and model assumptions are inspectable in event decisions and config hash. Revisit for independently audited issuer ex/pay-date histories, taxes, multi-currency dividends, same-boundary split ordering, reliable delisted position resolution, Tick/Quote fills and broker reconciliation. No Live authorization is implied.
