# E4 Strategy SDK & ORB baseline

**Status:** implemented candidate; verify GitHub CI and integration before marking E4 complete. **No actual brokerage or autonomous fill execution.**

## 1. Purpose

E0–E2 handle typed market observations and deterministic journal/replay; E3 handles manual synthetic order/risk/accounting. E4 supplies a plugin boundary between validated market events and **optional simulated OrderIntent proposals**. The strategy does not call an external broker or mutate account state.

```
E1 validated (market.*) events → E2 journal (caller responsibility)
           ↓
E4 StrategyRunner (causal as_of, session, warmup)
           ↓
feature registry (EMA, Wilder ATR, same-window median)
           ↓
Strategy.on_event → StrategySignal/NoAction
           ↓
AllocationPolicy (per symbol/currency caps + EXIT precedence)
           ↓
propose_simulated_intents() → E3 TradingRuntime.submit() [separate explicit call]
           ↓
E3 RiskDecision → virtual outbox (no broker)
```

## 2. Public Python contracts

- `DataRequirement(event_type, interval?, warmup, max_age?)`: strategy data capabilities. Bar interval has no engine-wide default. Unsupported/missing/warmup → no trade.
- `StrategyManifest(strategy_id, version, markets, requirements, features?)`: immutable plugin descriptor.
- `StrategyContext(as_of, event, bars, session, features)`: immutable **read-only observation view**; explicitly contains no account mutator/BrokerAdapter. Historical BarObservation includes known_at and session.
- `StrategySignal`: LONG/EXIT target fraction; planned stop; event lineage; expiration; deterministic ID.
- `StrategyRegistry`: unique `(strategy_id, version)` plugin registration.
- `StrategyRunner`: contiguous market-event ingestion, rejects duplicate/quality-flagged/unfinalized/future observations; performs required warmup and feature resolution and dispatches on matching subscriptions. Invalid plugin output halts runner for replay/recovery.
- `NoTradeStrategy`: baseline, valid output is always no signal.
- `FeatureRegistry`: pure, versioned EMA, Wilder ATR, median volume computed from finalized TimeBars, as-of filtering and source event trace; uses E2 FeatureGraph scheduler. This is a first **batch reference implementation**, not yet optimized online incremental caching.
- `ORBLongStrategy`: first *unvalidated* research hypothesis. Default KR opening 5 minutes / US 15 minutes, 1m finalized bars, ATR warmup, first confirmed close cross above opening high, same-session range contiguous, historical prior 20 sessions' same-relative-minute median volume ×1.5, stop proposal, one signal per session. `snapshot`/`restore` for session entry state. All parameters can be changed without editing Trading Core; no unsupported lower-resolution interpolation.
- `AllocationPolicy`: per-symbol and per-currency caps; multiple strategy targets for same instrument are combined with EXIT precedence. Capped allocations distribute the cap proportionally among strategies.
- `propose_simulated_intents`: using explicitly passed fresh MarketMark + E3 simulated account **snapshot** and instrument lot/tick rules, creates target-delta OrderIntent suggestions; does not submit or fill and refuses stale/missing data or existing pending orders. E3 PreTradeRisk can still reject.

## 3. Determinism, as-of, limitations

- `as_of = max(available_at, received_at)`, event time not later than as-of. E0/E1 quality gate must run first, or E2 journal accept prior to E4 dispatch. E4 also validates duplicate events and incomplete bars.
- Historical data cannot be replayed as if public earlier than available_at. Missing session calendar or incomplete ORB window produces no signal.
- ORB volume comparison assumes provider data coverage for 20 prior distinct sessions. If data coverage is incomplete, no signal; event count alone does not imply profitable trades.
- `StrategyRunner` is **in-memory**. Crash recovery in this stage requires replaying E2 persisted events to rebuild runner history and plugin state. E4 itself does not yet atomically journal signals to E3 order intents; E5 will implement integrated replay/transaction semantics. **Do not deploy E4 as autonomous production executor.**
- Python Protocols are not a security sandbox: third-party strategies can import arbitrary Python libraries if executed in the same process. Only trusted bundled strategies are supported until plugin process isolation/permissions exist.
- `virtual strategy_targets` are **planned exposure attribution**, **not a fill-based virtual position/P&L ledger**. Fill attribution and persistent allocation decisions need a separate E4 follow-up (or E5); do not claim this meets complete multi-strategy performance accounting.
- Portfolio allocation fraction is computed **per currency without implicit FX**. Global cross-currency optimization remains future research; E3 hard risk limits remain authoritative.
- No auto-generated market fills, no exchange order matching, no actual Tax/FX/broker live API, no ML, no overfitted performance claim.

## 4. Verification

Test files: `tests/test_strategy_e4.py`, `test_features_e4.py`, `test_orb_e4.py`, `test_allocation_e4.py`.

Acceptance scenarios:
- two runs with the same market event stream produce identical outcomes;
- insufficient warmup, no calendar, missing opening bars, missing 20 prior sessions, low volume, no breakout → no signal;
- quote/timeframe requirements do not force 1-minute OHLCV on the core;
- if market data appears late/invalid/unfinalized, no strategy execution;
- duplicated signal IDs/conflicting instrument metadata are refused;
- multiple strategy signals combine to one exposure target, stale market marks result in no intent;
- E3 rejects unsafe synthetic intents, and trade submissions remain manual;
- Python 3.12/3.13 full test suite + Ruff/mypy/secret scan must pass in CI.

## 5. E4 outstanding items

- [ ] Decide fill-attributed virtual strategy ledger and persistent strategy decision journaling (separate PR before declaring E4 wholly complete).
- [ ] Optimize incremental feature calculations and test batch-vs-stream parity (can be E5 performance hardening).
- [ ] Explicit E2→E4→E3 replay orchestrator with idempotent signal-to-order handoff (E5 integration).
- [ ] Measure ORB strategies with realistic spread, slippage, data availability and trade execution model (E5); **no profitability assertion before that**.
