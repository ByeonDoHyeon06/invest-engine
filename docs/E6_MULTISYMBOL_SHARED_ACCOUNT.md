# E6 multi-symbol shared-account historical replay

**Status:** PR-2 candidate in stacked [PR #69](https://github.com/ByeonDoHyeon06/invest-engine/pull/69), implementation through `6241e51`. Local verification passed 467 tests plus Ruff, mypy 80 files, credential guard and diff check. [CI 45970347660](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/45970347660) at `d583d53` passed the same 467 tests on each of Python 3.12/3.13 plus all static/secret checks. Synthetic contract verification only; PR #66 must merge first.

**Tracking:** Issue #65 · E5 #6 · E6 #7 · [design](superpowers/specs/2026-11-20-multisymbol-intraday-slot-momentum-design.md) · [ADR-0035](adr/0035-multisymbol-portfolio-decision-boundary.md)

**Authority:** offline research only. This module adds no strategy-profitability evidence, provider/PIT attestation, executable Quote/Trade model, Paper route, broker connection or Live permission.

## Scope

`HistoricalPortfolioBacktest` is an additive coordinator for trusted internal `PortfolioStrategy` implementations. Existing `HistoricalBacktest`, `BacktestReport`, single-event `StrategyRunner` and their report hash remain unchanged. The coordinator reuses, rather than replaces:

- E2 `EventRuntime` ordering and deterministic observation digest;
- PR-1 `UniverseFrameCoordinator` and `PortfolioStrategyRunner`;
- E4 `allocate_targets`, marked-equity intent sizing and virtual attribution;
- E3 monitored risk, reservations, simulated order state and cash/position ledger; and
- E5 strict later-bar limit penetration and volume participation.

There is one `TradingRuntime`, one USD cash account, one virtual attribution ledger and one mark map for the whole configured universe. Independent per-symbol accounts cannot be aggregated through this path.

## Constructor

```python
HistoricalPortfolioBacktest(
    *,
    calendar: SessionCalendar,
    instruments: tuple[InstrumentId, ...],
    strategy: PortfolioStrategy,
    config: TradingConfig,
    opening_cash: tuple[Money, ...],
    risk: RiskLimits,
    fill_policy: BarFillPolicy | None = None,
    allocation_policy: AllocationPolicy | None = None,
    settings: PortfolioBacktestSettings | None = None,
)
```

V1 requires at least two unique instruments from one market, exact `TradingConfig` rules for every instrument, USD instruments, one positive USD opening balance, `SellSettlementMode.IMMEDIATE`, monitored risk and no external-account-reference requirement. Input is a nonempty immutable tuple of finalized one-minute `Bar` envelopes. An instance is single-use.

`PortfolioBacktestSettings` pins the run version, history bound and caller-declared code/source/license identifiers. `config_digest()` binds configuration, policies, universe, calendar sessions, opening cash, strategy manifest and initial strategy snapshot.

## Replay and watermark order

For each authoritative full session, the regular checkpoint grid begins at `session.start + checkpoint_interval`; the flatten watermark at `session.end - checkpoint_interval` is always scheduled independently, including when it is off that grid. A checkpoint is finalized before accepting the first observation whose known clock is later than it; at EOF, a checkpoint equal to the last known clock is finalized. This allows all same-time trigger bars to enter a frame while making a delayed bar at or behind a finalized watermark fatal.

At each market event the order is:

1. advance already-due checkpoints without consuming the future observation;
2. apply E2 ordering and quality checks;
3. cancel an entry that is already ineligible for the current bar;
4. evaluate only previously accepted orders for fill;
5. process expiry after the last eligible bar;
6. update the causal mark; and
7. pass the observation to the universe coordinator.

Consequently, a trigger bar never fills an order created from that trigger. Missing universe members produce a persisted `DATA_UNAVAILABLE` checkpoint, not a smaller ranking universe. Every allocation plan produces a deterministic proposal result; plans that cannot create an intent are persisted as `NO_ACTION` decisions with a specific reason such as missing/stale mark, open order, invalid price/stop or sub-lot target. Duplicate, late, mixed-session or non-universe observations fail replay.

## Monitored shared capital

A new session requires a flat account and no unresolved order. Its immutable USD baseline is settled plus unsettled simulated cash at session open. Complete checkpoints are observed through E3 monitoring before strategy execution. Every BUY is re-observed after any preceding reservation or order-state change, so all held positions and pending BUY notional share the same risk ceiling. A pending SELL neither creates buying power nor removes held marked exposure.

When the E3 daily-loss latch is set, the trusted strategy is still called and its original signal IDs/selections remain in the audit. The execution input alone is replaced by a deterministic, frame-bound EXIT signal for every universe member, then allocated exactly once. The latch cannot be cleared by a later price rebound within that session.

Missing or stale held-symbol marks suppress account equity instead of inserting zero or cost. They prevent a complete new-exposure decision.

## Order lifetime and finalization

An approved BUY retains its allocation plan expiry and source frame. Its instrument's bar ending exactly at expiry remains eligible; any remainder is canceled only after that bar. A bar starting at expiry is ineligible and the order is canceled before fill evaluation. A later checkpoint also cancels older replaceable BUYs in deterministic intent-ID order before allocating replacement targets.

The replay keeps an intent-ID and instrument-keyed index of only accepted/partially-filled orders. Per-bar expiry and fill evaluation touches only active orders for that event's instrument; the index is reconciled against the authoritative E3 ledger at session boundaries so terminal order history is never used as the hot-path work queue.

SELLs are never canceled to manufacture a flat result. An unresolved EXIT at a later checkpoint, any nonterminal order at session close, positive final inventory or virtual/account quantity mismatch invalidates the arm with `InvalidEvent`.

## Reports and artifacts

`PortfolioBacktestReport` wraps the unchanged `BacktestReport` and adds:

- one `UniverseDecisionRecord` per attempted checkpoint;
- exact execution lineage from frame → intent → market event → fill;
- flat-to-long-to-flat `PositionCycle` values;
- per-session fill counts, completed-cycle counts, turnover, costs, PnL and union time in market;
- per-symbol turnover/PnL/cycle summaries; and
- largest positive-symbol PnL share, or `null` when no symbol is positive.

Entry and exit counts remain **fill counts**. A completed cycle is the transition from zero quantity to positive quantity and back to zero; multiple partial entry/exit fills remain one cycle. Gross PnL is net realized PnL plus modeled fees and taxes. Overlapping symbol holding intervals are counted once in session time in market.

`export(directory)` writes the unchanged account artifacts under `account/`, plus deterministic `report.json`, `universe_decisions.jsonl`, `executions.jsonl`, `cycles.jsonl`, `sessions.jsonl` and `symbols.jsonl`.

## Compatibility evidence

The legacy single-instrument regression keeps run hash:

```text
a672226e12320db5baa11b48bf408c3296fcd9df07fa89e9e15b2e23c69b3642
```

PR-2 synthetic tests cover later-bar fills, deterministic replay, partial-fill cycles, explicit proposal no-action, active-order-only fill evaluation, entry expiry, replacement, off-grid flatten, incomplete/late data, unresolved exits/final inventory, shared caps, pending sale proceeds, stale marks and daily-loss exit overlay. Local full verification is recorded in `docs/STATUS.md`; stacked PR CI remains the merge gate.

PR #69 adds `feat/multisymbol-portfolio-contracts` to the Core CI `pull_request.branches` allowlist so its stacked comparison runs normally on the exact PR head. Re-evaluate that temporary branch entry when PR #66 merges and PR #69 is retargeted to `main`.

## Explicitly still open

- `xs-slot-momentum@1.0.0`, cash/hold/placebo controls and the paired base/stress study are PR 3.
- Corporate-action/PIT-universe preflight is not integrated here; V1 consumes market bars only.
- Actual provider rights, issuer identity, historical vintages, costs, taxes and calendar completeness remain unverified.
- Bar penetration is a conservative approximation, not QuoteTick/TradeTick queue, spread or marketability evidence.
- No profitability report is produced by this infrastructure PR.
- E5 #6, E6 #7, G1/G2, independent untouched holdout, Forward Paper, E7 and E8 remain open. LIVE NOT AUTHORIZED.
