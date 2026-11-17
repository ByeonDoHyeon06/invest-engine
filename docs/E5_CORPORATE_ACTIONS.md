# E5.7 — Synthetic corporate-action ledger (research-only)

**Implementation status:** E3 TradingRuntime/SQLite journal accepts explicit **synthetic** share split, cash-dividend entitlement/payment and delisting events. There is **no** real broker/issuer feed, auto price adjustment, automatic event scheduling, or E5 HistoricalBacktest/PIT bridge yet.

## Contract

- `SplitApplied(action_id, instrument, numerator, denominator, effective_at, available_at, source)` adjusts a long position's `quantity *= numerator / denominator` and `average_cost *= denominator / numerator`; total acquisition basis remains unchanged, no cash created. **Fractional lot results are rejected** until a separate cash-in-lieu rule is implemented. No open orders on the instrument are allowed, so a split never silently reprices an order or changes a reservation.
- `DividendEntitled(... gross_per_share, withholding_fraction, effective_at, available_at, source)` captures quantity held when the explicitly supplied entitlement event is processed, and records a receivable. It **does not immediately increase buying power**. `DividendPaymentConfirmed(action_id)` moves the net receivable to settled cash once; no inferred payment date. The synthetic withholding fraction is caller-supplied, **not a legally verified tax rule**. Exact rounding follows the configured currency policy.
- `DelistingObserved(... effective_at, available_at, source)` blocks new buy **and** sell proposals for the instrument; preserves existing position/cost, with no invented final market price, write-off, cash-in-lieu or merger consideration. Any position remaining requires a separately verified resolution policy.
- Events cannot precede the action's effective time or its availability time. Missing/future identity, duplicate IDs with altered terms, open orders, inconsistent arithmetic and unrepresentable shares cause a fail-closed error. Identical repeated events are idempotent.
- The event codec, state SHA chain, replay journal, checkpointing and account audit include the new payloads and the split quantity delta. The changes are append-only: existing E3 v1 event byte formats remain unchanged. Existing pre-E5.7 journal files remain readable.

## Limitations and production boundary

- **The E5.6 PIT evidence loader still aborts the whole backtest on any in-window corporate action.** This accounting contract does **not** authorize bypassing that guard. A later integration must bind a provider's PIT action terms, date semantics and split-adjusted raw quotes to these E3 actions, and update E4 strategy attribution positions consistently before lifting the guard.
- Dividends may require record-date/settlement-date, ex-dividend price adjustment and independently verified entitlement/corporate action data. The current synthetic entitlement event **does not prove actual eligibility**.
- No merger, symbol change, liquidation, delisting settlement, withholding tax validation or cash-in-lieu computation. These cases remain unsupported, not inferred.
- The simulated account's order/position state must not be reused as an actual broker position. LIVE remains **NOT AUTHORIZED**.

## Test evidence

`tests/test_actions_e5.py`: split cost conservation, post-split sale, gross/withholding/net dividend, payment idempotency, delisting entry blocks, future action rejection, open-order conflict, fractional shares, conflicting replay ID, canonical codec and SQLite restart. Synthetic scenarios only.
