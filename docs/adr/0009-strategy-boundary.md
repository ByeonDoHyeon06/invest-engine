# ADR-0009: Trust-limited strategy plugin boundary and initial ORB baseline

- Date: 2026-11-16
- Status: Accepted (E4.1/2 CI, E4.3 attributable ledger pending CI)

## Context
E0–E3 contain immutable market/portfolio event contracts and a simulated execution ledger. Putting indicator logic or market-dependent strategy rules into the core would reintroduce 1m-bar coupling and allow model output to evade the risk gate.

## Decision
1. Strategy plugins receive immutable `StrategyContext` and emit `StrategySignal`. Strategy registration and manifest specify market/event/timeframe/warmup/feature dependencies. No broker or account mutators are passed.
2. `StrategyRunner` is a deterministic, fail-closed, replay-dependent shell. Source events are provided in journal order; an E2 journal is the durable source of truth. Future/unfinalized/quality-flagged inputs are rejected.
3. Feature computations are reference pure functions (EMA, Wilder ATR, median volume) with as-of and provenance; no fabricated 1m bars. FeatureGraph schedules requested definitions.
4. ORB is only a research baseline: prior 20 same-minute sessions volume, KR 5m/US 15m opening range defaults, no-trade on incomplete data. No performance or execution guarantees.
5. Multiple signals per instrument go through a separate allocation policy, generating **proposal-only** simulated OrderIntents. E3 continues to enforce all cash/position/risk limits.
6. The strategy/allocator only exposes per-strategy target **plans**, not a trade/fill-based virtual P&L ledger; this remains explicit technical debt before multi-strategy accounting claims.
7. Python Protocol alone does not sandbox untrusted plugins. Strategy code remains trusted internal code; external plugin isolation is a separate future decision.

## Alternatives
- Hard-coded ORB inside Trading Core: rejected (not extensible).
- LLM directly submits broker orders: rejected (unsafe authority inversion).
- Automatically backfill 30m bars into 1m: rejected (nonexistent information).
- Premature research microservices and online distributed feature cache: rejected (correctness first).

## Consequences and revisiting
Better separation and testability, but replay orchestration, fill attribution, and data vendor entitlements remain required before E5 and any production deployment. Revisit after E5 integrated historical replay or if untrusted third-party plugins become in-scope.

## E4.3 follow-up — attribution without broker access

A separate pure `VirtualLedger` uses immutable `AttributionTicket` and E3 `SimulatedFill` to allocate shared fills to strategy-level virtual positions. It conserves quantity and costs, computes realized P&L, rejects duplicate conflicts/overfills, and can audit aggregate quantity against E3's simulated account. **No transactionally durable ticket journal or live strategy ledger yet**; E5 will connect the replay orchestrator and persistence boundary. This follow-up does not relax the trust boundary or risk gate.
