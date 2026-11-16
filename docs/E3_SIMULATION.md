# E3 — Simulated Risk, Execution & Portfolio

**Status:** Implementation for simulation and deterministic accounting; **NO LIVE ORDER CAPABILITY**.

## Explicit boundaries

The E0/E2 `core.runtime.EventRuntime` continues to operate on market-only `EventEnvelope[MarketPayload]` and its `events` table. E3 adds an **isolated versioned trading-event namespace** (`trading_events`, `trading_checkpoints`, `trading_outbox`, `trading_metadata`) in the same SQLite file if desired, without migrating or altering older market events. `TradingRuntime` works as a pure, deterministic portfolio/order reducer with a simulated shell. Market→Strategy→Order handoff is not connected until E4/E5. There is no claim of a unified production event bus yet.

### External I/O

- `decode_order_intent(json)` accepts only `schema_version: "e3-sim-v1"` and `kind: "PROPOSE_ORDER_INTENT"`, with strict field checking. Source code: `src/invest_engine/trading/wire.py`.
- Python SDK: `TradingRuntime.submit(OrderIntent)` → `SubmitOutcome(decision, simulated_commands)`.
- Runtime accepts explicit **simulated** `accept_simulated`, `fill_simulated`, `request_cancel`, `confirm_cancel`, `mark_unknown`, `reconcile` events. No market fill inference in E3.
- Output state: `TradingState.cash` (settled/reserved/unsettled), `positions`, `orders`, `fills`, `digest`, plus `RiskDecision.reason_codes` and `SQLiteTradingJournal.outbox()`.
- For E5 a RunRequest/RunResult and historical backtest report will be added; for E6 an ML PredictionResult. Neither is implemented in E3.

## Simulated financial policy

- Only long positions; one account; cash books for KRW/USD are **separate**. No FX/margin/short/market orders.
- Prices and lot sizes are explicitly given per instrument (`InstrumentRules`); invalid increments are rejected.
- Every currency has an explicit `MonetaryRules(cash_step, rounding)`. Fixture policy: KRW quantum 1, USD 0.01, ROUND_HALF_UP; **not a claim about any brokerage settlement/tax convention**.
- Fee rate fixture is `0.001` = 0.1% *per Fill*, not a real Toss tariff. Fill's fee must match configured synthetic fee.
- `RiskLimits` controls maximum cost-basis symbol/total exposure, max distinct long symbols, planned stop-loss budget and mandatory stop plan.
- The E3 exposure denominator is **cost-basis equity in that currency** (`settled_cash + current position costs`), not mark-to-market equity. This is not sufficient for any live risk assessment: E4/E5 must add fresh market/FX marks and E8 broker buying-power reconciliation.
- Buy approval reserves `quantize(limit_price * qty * (1 + fee_rate))`. A fill consumes actual cost+fee and recomputes remaining reservation. Cancel only releases the remainder after confirmation.
- Sell approval reserves existing shares (prevents double-selling), and fills update moving average cost basis realized PnL. Real brokers and tax regimes may require FIFO or other rules: postpone until explicit market/broker contract verification.

## Order lifecycle

`RESERVED → ACCEPTED → PARTIALLY_FILLED → FILLED` or `CANCEL_PENDING → CANCELED`; `UNKNOWN → manual RECONCILE (accepted/canceled/rejected)`. A Fill is never inferred from acceptance. Existing open reservations protect cash/shares even after restart.

- Duplicate **same intent + same contents** → no second event/command.
- Duplicate **same Fill ID + same contents** → no second event/position mutation.
- Same ID + **different contents** → HALT & error, requiring review.
- Unknown order admission → new risky intents blocked (`HALTED` decision); resolve explicitly first.
- Failed event/journal commit → fail closed. E3 journal contains an append-only SHA-256 verified event stream, state-chain hash, periodic digest checkpoints, and a transactional outbox.
- `outbox()` exposes unresolved PENDING/UNKNOWN commands for **manual reconciliation**; it never automatically resends. Actual broker integration requires a separate E8 review.

## Synthetic example (E3, not backtest)

```python
from datetime import datetime, timezone, timedelta
from decimal import Decimal as D
from invest_engine.domain.primitives import InstrumentId, Market, Money
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.models import OrderIntent, Side, TradingConfig
from invest_engine.trading.runtime import TradingRuntime

kr = InstrumentId(Market.KR, "KRX", "KR7005930003", "005930", "KRW")
conf = TradingConfig(
    "sim-account", (MonetaryRules("KRW", D("1")),),
    ((kr.key, InstrumentRules(D("1"), D("1"))),),
)
engine = TradingRuntime(conf, (Money(D("1000000"), "KRW"),))
t = datetime(2026, 11, 16, tzinfo=timezone.utc)
intent = OrderIntent("test-1", "sim-account", "fixture", kr, Side.BUY,
                     D("10"), D("7000"), t, D("6800"))
assert engine.submit(intent).decision.reservation == D("70070")
engine.accept_simulated("test-1", t + timedelta(seconds=1))
engine.fill_simulated("test-1", price=D("7000"), quantity=D("4"),
                      execution_id="fill-1", at=t + timedelta(seconds=2))
engine.request_cancel("test-1", t + timedelta(seconds=3))
engine.confirm_cancel("test-1", t + timedelta(seconds=4))
assert engine.state.account("KRW").settled == D("971972")
assert engine.state.account("KRW").reserved == 0
assert engine.state.position(kr).quantity == D("4")
```

This is an example of **deterministic manual virtual fills**, not a trading strategy, historical fill model, or broker market simulator.

## Quality gates (E3)

- Synthetic scenario arithmetic and fills/fees (buy, partial-fill, cancel, sell PnL)
- Duplicate intent and Fill and conflicting ID handling
- Cash/shares reservations and currency separation, no implicit FX
- Order unknown, rejection, HALT/review, invalid price/qty input
- SQLite event/outbox atomicity and restart replay, checkpoint/hash corruption
- E2 market journal coexistence, existing E0/E1/E2 regression suite
- Python 3.12/3.13 pytest, mypy, Ruff, secrets guard in GitHub Actions

## Remaining before real trading

- E4 strategy output + market mark-based risk exposure from current quote/Bar
- E5 event-driven bar/tick simulator with fees/slippage/time-based fill eligibility and Run API
- E7 broker paper stream reconciliation, session calendar, FX, and operational monitoring
- E8 explicit live authorization, exchange/broker trading rules, actual settlement/tax policy, idempotent broker submission, account and buying-power reconciliation
