# E3.3 — Mark-to-Market, Daily-Loss Gate & Reference Reconciliation

**Status:** E3.3 simulation implementation · 2026-11-16. **Not approved for live trading.**  
**Code:** `src/invest_engine/trading/monitoring.py`, `trading/runtime.py`, `trading/ledger.py`, `trading/codec.py`.

## 1. Motivation and boundary

E3.1 uses *cost-based* risk and synthetic cash/position ledgers. E3.3 adds an explicit, deterministic, **journaled** observation of a market-price snapshot, optional FX marks, a per-currency beginning-of-session baseline, and a reference account snapshot. This allows a new BUY to be gated on fresh information in an **opt-in simulation monitoring mode**.

No live network connections, remote broker reconciliation, or automated fills were added. Input objects are caller-supplied; the current implementation **cannot authenticate their provenance**. Actual exchange-session baselines, broker trust, cash settlement, regulatory taxes and margin policies are E7/E8 requirements.

## 2. E3.3 Input/Output

Input via `TradingRuntime.observe_market_and_account(MonitorInput)`:

- `checked_at`: UTC-aware instant, matching the risk-check event time.
- `session_id`: caller-supplied stable market/session identifier (e.g. `KR-2026-11-16`). **Not automatically validated against a trading calendar yet.**
- `base_currency`: the reporting currency (e.g. `KRW`), not a licence to exchange cash.
- `marks`: tuple of `MarketMark(instrument, price, available_at, source)`; only required positions and proposed entries are valued/verified; every held long position must have a fresh mark.
- `fx_rates`: explicit currency pair `FxMark(base, quote, rate, available_at, source)`; no inferred or synthetic FX conversion; only direct pair into reporting currency.
- `baselines`: each funded currency's beginning-of-session `SessionBaseline(currency, session_id, equity, started_at)`; no implicit creation from current positions.
- `reference`: optional `ExternalAccountReference(account_id, as_of, cash, positions, open_intent_ids)` for synthetic as-of comparison.

Output `MonitorResult`:

- per-currency equity, unrealized/realized PnL, session-to-date return **only when market marks are complete**;
- `converted_equity`: Decimal in requested reporting currency, or `None` when position marks / FX are missing or stale;
- stable `reasons` codes (e.g. `MARK_MISSING`, `DAILY_LOSS_LIMIT`, `FX_MARK_MISSING`, `CASH_RECONCILIATION_MISMATCH`);
- captured price marks, session ID, state event ordinal; output is recomputed from **journaled input and current trading state** during replay.

`TradingRuntime.review_reconciliation_hold(reviewed_by, at)` requires (a) a verified healthy subsequent reference, (b) operator attribution, and (c) a fresh check after the review before more BUYs.

## 3. Enabling monitored mode (synthetic, not live)

```python
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from invest_engine.trading.policy import RiskLimits
from invest_engine.trading.monitoring import MarketMark, MonitorInput, SessionBaseline

limits = RiskLimits(
    require_monitoring=True,
    max_daily_loss_fraction=D("0.01"),  # new BUY daily stop, NOT guaranteed loss cap
    mark_max_age=timedelta(minutes=2),
    require_account_reference=False,  # true only if an actual trusted reference is injected
)
# In an initialized TradingRuntime(run, limits=limits), before a new BUY:
# run.observe_market_and_account(MonitorInput(
#     checked_at=now, session_id="KR-2026-11-16", base_currency="KRW",
#     marks=(MarketMark(instrument, D("7000"), now, "synthetic"),),
#     baselines=(SessionBaseline("KRW", "KR-2026-11-16", D("1000000"), session_start),),
# ))
# run.submit(synthetic_intent)  # still subject to every existing E3 pretrade risk policy
```

**Compatibility:** `require_monitoring=False` is the default because E3.1/E3.2 fixtures have no market feed. This must **NOT** be mistaken for a safe live default. A future live executor must reject operation unless monitoring + verified data provider + broker/account capabilities are explicitly configured. Existing default E3 journal identity is preserved, while monitored policies are pinned in journal identity to prevent silent policy switches after restart.

## 4. Calculation and risk invariants

- Per currency: `equity = settled_cash + unsettled_cash + SUM(held_qty × fresh_mark_price)`; position unrealized PnL compares mark to fee-inclusive moving average acquisition cost. **Current E3 unsettled cash remains a synthetic placeholder; settlement models come later.**
- `daily_return = (current_equity - session_baseline_equity) / session_baseline_equity`; stops new entries when <= `-max_daily_loss_fraction`. This uses **per-currency** reference equity; FX movements are visible in aggregate reporting but **not yet a consolidated account-level daily stop**.
- A breached session is *latched* in `TradingState.daily_loss_sessions`, persists across restart, and remains blocked even if price rebounds within the same supplied session ID. Changing session ID requires a trusted calendar outside this module.
- An incomplete mark yields `None` for affected equity/unrealized PnL and combined converted equity; **never count missing position prices as zero** and never latch a false daily loss because data is missing.
- All funded currencies need a session baseline. Converting non-base currency valuation to the reporting currency requires an explicit fresh FX mark; currency ledgers are **never automatically merged**.
- `require_monitoring=True`: new BUY requires latest healthy observation, fresh mark for the proposed instrument, observed-check age within `mark_max_age`, no session loss latch and no account reconciliation hold. Any ledger event after the risk check invalidates that check until a new one is recorded.
- Existing position-reducing SELL intents, partial fills, cancellation and reconciliation remain possible when marks are missing. **No automatic liquidation is promised**.
- For monitored BUYs, exposure uses fresh marked value of existing holdings (plus unfilled buy order limits), not stale historical cost; older `SYMBOL_COST_LIMIT`/`TOTAL_COST_LIMIT` error codes remain stable for compatibility.

## 5. Reference account comparison (not a live broker connector)

- The reference must match account ID, have a timestamp no earlier than the most recent ledger event, and fall within `mark_max_age` of the check.
- Compare settled cash by currency, positive held quantities by global instrument key; optionally externally acknowledged open order intent IDs (excluding internally reserved but not acknowledged orders).
- If `require_account_reference=True`, missing reference blocks new BUYs.
- Mismatch is latched in `TradingState.reconciliation_hold` and **cannot be cleared by supplying a healthy snapshot alone**. A clean subsequent observation plus explicit `review_reconciliation_hold` event is required; the review itself invalidates the last assessment, forcing re-check.
- Broker data can arrive out-of-order, contain unsettled cash, use its own order IDs and price/corporate-action conventions. The current synthetic as-of comparison is a safety contract, **not production reconciliation**; broker mappings and external reads are E8 tasks.

## 6. Crash safety and backwards compatibility

- `RiskObserved` is an E3 v1 tagged trading event; it records immutable monitor inputs and recomputes outputs in pure reducer when replayed.
- `AccountReconciliationReviewed` is likewise an audited event; no direct state mutation is allowed.
- SQLite persists event, checksum, periodic checkpoint and outbox atomically. E2 market event journal remains untouched.
- Original E3.1/E3.2 trading-event codec and journal identity remain valid under unchanged default synthetic policies. A new monitored policy produces a different identity; opening it with incompatible limits raises an error.
- Broken/forged persisted input must fail to decode or fail checksum, not silently produce a healthy risk status.

## 7. Verification and remaining work

`PYTHONPATH=src python -m pytest -q` checks existing E0/E1/E2/E3 tests and `tests/test_monitoring_e3.py` (new marked risk, latches, missing data, FX, account mismatch, restart and codec). CI runs Python 3.12/3.13 + Ruff + mypy + secrets check.

**Still excluded:** real market streaming, actual calendar-derived session baseline, broker-signed snapshot verification, consolidated FX daily-loss limit, taxes, settlement lag, corporate actions, auto order execution and strategy/ML integration. These belong to E4–E8, not proof that E3 simulation is safe to use with real funds.
