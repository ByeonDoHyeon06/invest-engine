# ADR-0035: Explicit-watermark multi-symbol portfolio decision boundary

- Date: 2026-11-21
- Status: Accepted for offline implementation; PR #66 open at `52ce1da`, CI 44894840967 passed; PR-2 candidate [#69](https://github.com/ByeonDoHyeon06/invest-engine/pull/69) through `6241e51`, CI 45970347660 passed 467 tests per Python version at `d583d53`

## Context

The existing E4 `StrategyRunner` deliberately evaluates one market event and requires every returned signal to belong to that event's instrument. That rule is correct for event-scoped strategies, but it cannot make one causal cross-sectional decision over a fixed universe. Running one independent strategy/account per symbol would also hide shared cash, position and risk competition.

The first proposed higher-frequency study needs all required instruments observed at the same checkpoint before a trusted strategy can rank them. A missing member, late observation or mixed session must remain visible instead of silently shrinking the universe.

## Decision

1. Keep the existing `Strategy`, `StrategyRunner` and `HistoricalBacktest` contracts unchanged.
2. Add a separate `UniverseFrameCoordinator` that consumes the existing globally ordered `EventEnvelope` stream and advances only through caller-supplied UTC finalization watermarks.
3. A complete frame contains one exact finalized one-minute trigger bar for every canonically ordered universe member. Missing members return `DATA_UNAVAILABLE`; supported non-decision times return `NO_ACTION`; structural clock, session or input violations halt until reconstruction by trusted replay.
4. Late bars at or before a finalized watermark are rejected. Instrument-history invalidation may remove stale observations and duplicate-bar keys, but it never rewinds seen event IDs, ordinal, known time or watermark.
5. Add a separate trusted-internal `PortfolioStrategy` protocol and `PortfolioStrategyRunner`. It receives an immutable causal context and emits one ordered `StrategySignal` per frame member in a frame-bound `PortfolioSignalBatch`.
6. The runner validates frame/manifest identity, generation time, member order, trigger lineage, signal expiry, LONG count and gross target envelope. It does not sort, repair, allocate, submit or fill plugin output.
7. The strategy boundary remains offline and in-memory. It has no broker, database, network, account mutation or direct order authority.
8. Add a separate, single-use `HistoricalPortfolioBacktest` research coordinator. It owns one existing E3 `TradingRuntime`, one virtual attribution ledger and one mark map for the complete USD universe; the existing single-instrument `HistoricalBacktest` and `BacktestReport` stay unchanged.
9. Schedule session-relative checkpoints explicitly. Finalize one before accepting the first observation whose known clock passes it, or at EOF when equal. Previously accepted orders are evaluated before the current bar updates marks or enters a strategy frame.
10. Require a flat session boundary, a session-opening USD baseline and E3 monitoring. Re-observe before every BUY after state changes. Pending BUYs share portfolio exposure; pending SELL proceeds are unavailable. A latched daily-loss session replaces execution input with a deterministic complete EXIT set while retaining the strategy's original audit output.
11. Preserve the allocation plan expiry for each BUY. Process its final eligible bar before canceling a remainder; reject a bar starting at expiry. Cancel older replaceable BUYs before a later decision, but never cancel an unresolved SELL to manufacture a flat result. Unresolved EXITs, orders or final inventory invalidate the arm.
12. Wrap the unchanged account report with checkpoint lineage, exact executions, flat-to-long-to-flat position cycles, session/symbol summaries and deterministic artifacts. Fill counts remain fills and are not renamed trades.
13. Persist one deterministic proposal outcome per allocation plan. A plan that produces no order intent remains an explicit `NO_ACTION` decision with a machine-readable reason; it is not silently omitted or misreported as a risk rejection.
14. Use an instrument-keyed active-order index for per-bar expiry and fill work, and reconcile it against the E3 ledger at session boundaries. Append-only terminal order history remains audit state, not the replay hot-path queue.

## Consequences

- Partial-universe ranking is impossible in this contract; unavailable data remains an explicit outcome.
- Replay ordering and explicit watermarks, rather than wall-clock timing, determine frame identity and late-data behavior.
- Cross-venue instruments may share a frame only when their session bounds align; venue names need not match.
- The coordinator can retain substantially more bar history than the event-scoped runner, so callers must configure and monitor its bounded in-memory capacity.
- Crash recovery requires replaying the trusted event journal and restoring strategy-owned state. This ADR does not add durable portfolio decisions or atomic order handoff.
- Shared-capital and monitoring behavior can now be tested synthetically without implementing the proposed strategy. Corporate-action/PIT preflight and paired base/stress orchestration remain follow-ups.
- Bar penetration remains an offline approximation. This ADR adds no QuoteTick/TradeTick queue evidence, provider attestation, Paper transport or Live authority.
- Passing contract tests establishes implementation correctness only. It provides no evidence that `xs-slot-momentum@1.0.0` is profitable or executable.

## Alternatives rejected

- Loosen the existing signal-to-triggering-instrument rule: rejected because it would weaken a verified single-instrument safety contract and create compatibility risk.
- Run independent per-symbol accounts and aggregate reports: rejected because this omits shared capital, pending-order and portfolio-risk competition.
- Batch implicitly on process wall-clock arrival: rejected because replay could produce different membership and results under different timing.
- Rank the available subset when a member is missing: rejected because it changes the declared universe and can create survivor/data-availability bias.

## Revisit triggers

Revisit this decision before adding a continuously running streaming/Paper lifecycle, any partial-universe policy, untrusted plugin process isolation, or QuoteTick/TradeTick execution and queue modeling. A changed recovery or persistence model, distributed watermark source, or permission boundary requires a replacement/amending ADR and replay compatibility tests.

The implemented PR-2 boundary is documented in [E6 multi-symbol shared-account historical replay](../E6_MULTISYMBOL_SHARED_ACCOUNT.md). Remaining strategy/research work is specified in [the multi-symbol intraday research design](../superpowers/specs/2026-11-20-multisymbol-intraday-slot-momentum-design.md).
