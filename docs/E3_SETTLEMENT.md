# E3.4 — Explicit Synthetic Settlement, Cost Audit, and E3 Release Gate

**Status:** implemented on E3.4 development branch, subject to CI. **Simulated-only; no real broker, statutory-tax, exchange calendar, or LIVE functionality.**

## Scope & purpose

E3.1–E3.3 established deterministic order/portfolio accounting, reservations, operator safety, monitoring and reference-account comparison. E3.4 closes the **simulation accounting contract** by separating synthetic sell proceeds from spendable cash, recording per-fill synthetic taxes, and auditing cross-ledger invariants after every event transition.

### API changes

`TradingConfig` now includes optional:

- `sell_tax_rate: Decimal = 0`: an **illustrative rate**, applied to **SELL gross notional only**; this is not an estimate of Korean or US legally applicable taxes or a Toss tariff.
- `sell_settlement_mode: SellSettlementMode = IMMEDIATE`: preserves all earlier E3 behavior and previously saved journal identities under default settings.
- `EXPLICIT_CONFIRMATION`: SELL net proceeds are first recorded as `CashLedger.unsettled` with a `PendingSettlement(execution_id, currency, amount, occurred_at)`.
- `TradingRuntime.confirm_cash_settlement(execution_id, at) -> bool`: **manual simulated confirmation**. On success it emits `CashSettlementConfirmed`, moves net cash from `unsettled` to `settled`, and returns `True`. Repeated confirmation of an already confirmed ID returns `False` without another event. An unknown or premature confirmation fail-closes the simulation.
- `TradingState.charges: tuple[TransactionCharge,...]`: immutable fee/tax/cash-delta summary derived from the pinned configuration and each original `SimulatedFill` on replay. Original `SimulatedFill` wire representation is unchanged, preserving older event hashes.
- `audit_trading_state(state)`: verifies order fill quantities, held positions vs fills, cash and share reservations, pending settlements, charge trace and no negative buying power. It runs after each reducer transition and thus during journal replay.

### Cash accounting example (purely synthetic)

| Event | Settled KRW | Unsettled KRW | Remarks |
| --- | ---: | ---: | --- |
| Open | 100,000 | 0 | opening cash |
| Buy 10 × 7,000 | 29,930 | 0 | 70 fee (0.1% synthetic) |
| Sell 4 × 8,000 | 29,930 | 31,888 | 32 fee + 80 synthetic sell levy (0.25%) |
| Confirm sale settlement | 61,818 | 0 | proceeds become spendable only now |

- `CashLedger.available = settled - reserved`, **not** `settled + unsettled - reserved`.
- Mark-to-market equity counts `settled + unsettled` as assets, provided market marks and FX are complete. Equity is different from buying power.
- Pending cash is **not automatically released after T+1/T+2**. The confirmation input is explicit, and a real exchange/business-day settlement calendar, corporate actions, broker evidence, legally accurate taxes, FX and unsettled buyer-power policies remain later E7/E8 work.
- Tax changes realized P&L and net cash, not an imagined security price. Buy acquisition fee remains included in cost basis under ADR-0006.
- New policy values are pinned into the SQLite trading-journal identity. Existing default-mode E3.3 journal identity and `FillRecorded` encoding are preserved; older journals can be restored without rewriting historical event bytes. Any nondefault policy change rejects opening the journal.

## E3 Gate — verified scope and deferred dependencies

| Gate | Verifiable evidence | Status after CI |
| --- | --- | --- |
| Market events / deterministic core | E0-E2 tests, E2 journal | existing verified |
| Synthetic risk, order, partial fill, cancel, idempotency | E3.1 tests | existing verified |
| Operator pause/cancel/flatten plan | E3.2 tests | existing verified |
| Optional marked equity / stale data / daily-loss latch / account snapshot comparison | E3.3 tests | existing verified |
| Synthetic configurable sell levy / unsettled proceeds / manual settlement / ledger audit | E3.4 tests | verify CI before E3 closure |
| Legacy journal compatibility | pre-E3.4 saved journal restored, same hash | manual integration check and CI regression |

**Deliberate exclusions (not an E3 failure):** automatic real-time fill matching (E5); Strategy SDK/Portfolio Allocator (E4); data→trade combined dispatch (E4/E5); actual tax/fee schedule, market calendar settlement and live broker cash availability (E7/E8); broker-backed reconciliation and actual account credentials (E8); model training (E6).

**Important limitations:** E3 simulates an account's orders and cash changes from explicitly supplied test events; it is not a complete executable trading strategy/backtester and should not be advertised as production-ready. Code paths for real orders remain absent.

### Required CI & release evidence

1. `python -m pytest -q`, `ruff check .`, `mypy src`, `python scripts/check_secrets.py` on Python 3.12 and 3.13.
2. Synthetic scenarios: exact fee/levy, KRW/USD rounding, non-spendable pending sale, repeated settlement idempotency, premature/unknown settlement fail-closed, policy identity mismatch, checkpoint/replay, corruption audit, prior journal replay unchanged.
3. Update `docs/STATUS.md` with PR/CI/merge evidence and link the next E4 epic. Only after successful merge and CI, close E3 Issue #4.
