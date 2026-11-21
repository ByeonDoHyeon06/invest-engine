# E4 Strategy SDK & ORB baseline

**Status:** E4.1–E4.3 verified, merged as PR #21/#22; [CI 43857703057](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43857703057) Python 3.12/3.13 each 191 passed. **No actual brokerage or autonomous fill execution.**

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

### 3.1 Additive multi-symbol portfolio boundary (local candidate)

[ADR-0035](adr/0035-multisymbol-portfolio-decision-boundary.md) adds a separate offline-only path without changing `StrategyRunner`:

- immutable `UniverseDecisionFrame`/`UniverseFrameOutcome` contracts distinguish `COMPLETE`, `DATA_UNAVAILABLE` and `NO_ACTION`;
- `UniverseFrameCoordinator` consumes contiguous causal bar events, finalizes only at explicit watermarks, rejects late/duplicate/mixed-session input and never ranks a partial universe;
- `PortfolioStrategyRunner` supplies an immutable causal history to a trusted `PortfolioStrategy`, then validates the complete ordered signal batch, trigger lineage, manifest identity and LONG/gross exposure envelope; and
- pre-split history invalidation removes only the affected instrument's observations without rewinding stream audit state or resetting strategy state.

This implementation is in-memory and proposed in [PR #66](https://github.com/ByeonDoHyeon06/invest-engine/pull/66); [PR CI 44894640980](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44894640980) passed Python 3.12/3.13 with 433 tests each and all static/secret checks, while latest PR checks remain the merge gate. It does **not** implement the shared-account historical coordinator, target allocation/order lifecycle, portfolio report, `xs-slot-momentum@1.0.0`, controls, real-data workflow or profitability study. Those remain staged PR 2/PR 3 work under [Issue #65](https://github.com/ByeonDoHyeon06/invest-engine/issues/65). No path submits an order or changes Paper/Live authority.

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

- [x] Add pure fill-attributed virtual strategy ledger (E4.3; CI verified, PR #22).
- [ ] Persist attribution tickets and transactionally journal strategy decisions with order commands (E5 integrated runtime).
- [ ] Optimize incremental feature calculations and test batch-vs-stream parity (can be E5 performance hardening).
- [ ] Explicit E2→E4→E3 replay orchestrator with idempotent signal-to-order handoff (E5 integration).
- [ ] Measure ORB strategies with realistic spread, slippage, data availability and trade execution model (E5); **no profitability assertion before that**.

## 6. E4.3 — deterministic virtual fill attribution (research only)

**New files:** `src/invest_engine/strategies/attribution.py`, `tests/test_attribution_e4.py`.

- A `ticket_for_plan(allocation_plan, simulated_order_intent)` links an approved simulation order to its source strategy weight allocation; do not infer strategy provenance from a broker order alone.
- `record_simulated_fill(VirtualLedger, AttributionTicket, SimulatedFill)` is a **pure reducer**: shares and acquisition fees split proportionally among strategy targets; a SELL is allocated pro rata across actual outstanding virtual strategy positions; realized P&L tracks fees and cost basis.
- Splits may use **fractional virtual shares for accounting** even if the actual trade uses whole lots. These are research attribution units, never tradeable physical shares. A deterministic final-strategy remainder ensures sum(split_quantity) equals the original Fill quantity exactly.
- The virtual ledger refuses unknown/mismatched intents, overfilling an order, duplicate execution IDs with different contents, or selling unallocated shares. Identical repeated fills are idempotent.
- `audit_virtual_against_account(virtual, trading_state)` checks instrument-level virtual total quantities against E3 actual synthetic positions. It requires full coverage; if the E3 account has external/manual holdings, matching cannot be asserted and the auditor rejects it.
- Replay of the same tickets+fills deterministically regenerates virtual holdings and realized P&L. **Persistence/transactional recording of tickets and cross-module E2→E4→E3 state commits is E5 work**; no atomic production research ledger claim here.

E4 quality gates: interface/ORB/Feature tests plus synthetic fill-attribution and account-audit tests. Python 3.12/3.13 CI must pass before closing the E4 Epic.
