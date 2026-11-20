# Multi-Symbol Universe Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first offline-only multi-symbol decision boundary: synchronized universe frames plus a trusted portfolio-strategy protocol and fail-closed runner, without submitting or simulating orders.

**Architecture:** Preserve the existing per-instrument `StrategyRunner` unchanged. Add immutable portfolio contracts, a pure in-memory `UniverseFrameCoordinator` driven by explicit event ingestion and checkpoint watermarks, and a `PortfolioStrategyRunner` that supplies read-only causal history and validates complete target batches. Shared-account backtesting, fills, the slot-momentum rule and real-data workflows remain later PRs.

**Tech Stack:** Python 3.12+, frozen dataclasses, `Decimal`, aware UTC `datetime`, existing `EventEnvelope`/`BarObservation`/`SessionCalendar`/`StrategySignal`, pytest, Ruff, mypy strict.

**Spec:** `docs/superpowers/specs/2026-11-20-multisymbol-intraday-slot-momentum-design.md`

## Global Constraints

- Implement only rollout PR 1 from the spec: contracts, universe synchronization, runner validation, ADR and status documentation.
- Do not implement shared cash/risk/order/fill coordination, `xs-slot-momentum@1.0.0`, provider downloads, research workflows or E6.7 SDK changes in this plan.
- Existing `Strategy`, `StrategyRunner`, `HistoricalBacktest`, report hashes and E6.7 normative examples must remain unchanged.
- Domain/strategy code must not import broker SDKs, databases, network clients or `invest_engine.research`.
- All times are aware UTC; all fractions are `Decimal`; no float conversion.
- Input retains E2 semantics: contiguous global `ingest_ordinal`, unique event IDs and nondecreasing `max(available_at, received_at)`.
- Frames require exact finalized one-minute trigger bars for every declared instrument; partial frames never reach a strategy.
- `DataUnavailable`, `NoAction` and invalid/halted output remain distinct.
- No source event is reordered, interpolated or fabricated.
- At execution time, inspect open PRs/CI again and create an isolated worktree from the latest compatible main plus the accepted design commit.

## Review Focus

- Different listing venues with the same US session times must form one frame; genuinely different session start/end times must fail. Task 2 tests both.
- A bar arriving after a finalized checkpoint watermark must halt rather than retroactively repair an incomplete frame. Task 2 tests this.
- One missing universe member must yield `DATA_UNAVAILABLE`, never a smaller complete frame. Task 2 tests this.
- A strategy batch with a missing member, foreign trigger ID, excess LONG count or excess gross target must halt the runner. Task 3 tests each mutation.
- Split-history invalidation must remove only the selected instrument's observations and must not reset journal ordinal or watermark identity. Task 2 tests this.

---

## File Structure

- Create `src/invest_engine/strategies/portfolio_contracts.py`: immutable frame, outcome, manifest, context, signal-batch and protocol types.
- Create `src/invest_engine/strategies/universe.py`: deterministic event ingestion, explicit watermark finalization and bounded observation history.
- Create `src/invest_engine/strategies/portfolio_runtime.py`: portfolio strategy dispatch and output validation; no allocation or order submission.
- Create `tests/test_portfolio_contracts_e6.py`: value-object validation and read-only context behavior.
- Create `tests/test_universe_frame_e6.py`: barrier, clock, session, missing-data and invalidation behavior.
- Create `tests/test_portfolio_runtime_e6.py`: trusted fixture strategy dispatch and adversarial batch validation.
- Create `docs/adr/0035-multisymbol-portfolio-decision-boundary.md`: additive portfolio strategy boundary decision.
- Modify `docs/adr/README.md`: index ADR-0035.
- Modify `docs/E4_STRATEGY.md`: document the candidate portfolio extension and its non-execution boundary.
- Modify `docs/STATUS.md`, `docs/ROADMAP.md`, `AGENTS.md`: record actual PR-1 evidence and remaining PR-2/PR-3 work only after verification.
- Modify `docs/superpowers/specs/2026-11-20-multisymbol-intraday-slot-momentum-design.md`: change status from proposed to accepted and link ADR-0035 after implementation.

### Task 1: Immutable portfolio contracts

**Files:**
- Create: `tests/test_portfolio_contracts_e6.py`
- Create: `src/invest_engine/strategies/portfolio_contracts.py`

**Interfaces:**
- Consumes: `BarObservation`, `StrategySignal`, `InstrumentId`, `Market`, `EventEnvelope`, `MarketPayload`.
- Produces:
  - `UniverseCheckpointKind(REBALANCE, FLATTEN)`
  - `UniverseFrameStatus(COMPLETE, DATA_UNAVAILABLE, NO_ACTION)`
  - `UniverseDecisionFrame(frame_id: str, as_of: datetime, session_start: datetime, session_end: datetime, slot_index: int, kind: UniverseCheckpointKind, instruments: tuple[InstrumentId, ...], trigger_bars: tuple[BarObservation, ...])`
  - `UniverseFrameOutcome(status: UniverseFrameStatus, as_of: datetime, frame: UniverseDecisionFrame | None = None, missing_instrument_keys: tuple[str, ...] = (), reason_codes: tuple[str, ...] = ())`
  - `PortfolioStrategyManifest(strategy_id: str, version: str, markets: frozenset[Market], bar_interval: timedelta, checkpoint_interval: timedelta, max_long_positions: int, max_gross_target_fraction: Decimal)`
  - `PortfolioStrategyContext(as_of: datetime, frame: UniverseDecisionFrame, bars: tuple[BarObservation, ...])` with `bars_for(instrument: InstrumentId, interval: timedelta) -> tuple[BarObservation, ...]`
  - `PortfolioSignalBatch(frame_id: str, strategy_id: str, strategy_version: str, generated_at: datetime, signals: tuple[StrategySignal, ...], reason_codes: tuple[str, ...] = ())`
  - `PortfolioStrategy` protocol with `manifest`, `on_frame(frame, context)`, `snapshot()` and `restore(data)`.

- [ ] **Step 1: Write failing contract tests**

Add literal fixtures and these tests:

```python
def test_universe_frame_requires_sorted_exact_one_to_one_trigger_bars(): ...
def test_frame_outcome_keeps_complete_unavailable_and_no_action_distinct(): ...
def test_portfolio_manifest_rejects_invalid_intervals_and_limits(): ...
def test_portfolio_context_rejects_future_history_and_filters_bars(): ...
def test_signal_batch_requires_identity_and_immutable_unique_signals(): ...
```

Assertions must cover:

- instruments are a nonempty tuple sorted by `instrument.key`, with unique keys;
- trigger bars have the same length/order/instrument identity, exact one-minute interval ending at `as_of`, and `known_at <= as_of`;
- `session_start < as_of < session_end`, `slot_index >= 1`, and FLATTEN/REBALANCE are typed enum values;
- COMPLETE has a frame and no missing keys, DATA_UNAVAILABLE has no frame and nonempty sorted missing keys, and NO_ACTION has no frame plus a reason;
- manifest intervals are positive, checkpoint is an exact multiple of bar interval, `max_long_positions >= 1`, and gross cap is within `(0, 1]`;
- a context refuses any observation known after `as_of`;
- a signal batch has nonblank identity fields, UTC generation time, an immutable tuple and unique signal IDs.

- [ ] **Step 2: Run the contract tests and verify RED**

Run: `python3 -m pytest tests/test_portfolio_contracts_e6.py -q`

Expected: collection fails with `ModuleNotFoundError: invest_engine.strategies.portfolio_contracts`.

- [ ] **Step 3: Implement the contract types**

Use exact frozen/slotted dataclasses and these signatures:

```python
class PortfolioStrategy(Protocol):
    @property
    def manifest(self) -> PortfolioStrategyManifest: ...
    def on_frame(
        self, frame: UniverseDecisionFrame, context: PortfolioStrategyContext,
    ) -> PortfolioSignalBatch: ...
    def snapshot(self) -> bytes: ...
    def restore(self, data: bytes) -> None: ...
```

Normalize times with `utc_datetime`. Reuse `BarObservation`; do not introduce a duplicate bar wrapper. Keep only structural batch checks in `PortfolioSignalBatch`; frame/manifest-dependent output checks belong to Task 3.

- [ ] **Step 4: Run targeted tests and verify GREEN**

Run: `python3 -m pytest tests/test_portfolio_contracts_e6.py -q`

Expected: all tests in the new file pass.

- [ ] **Step 5: Run the full test suite before committing**

Run: `python3 -m pytest -q`

Expected: exit 0 with no existing regression.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/invest_engine/strategies/portfolio_contracts.py tests/test_portfolio_contracts_e6.py
git commit -m "feat(strategy): add portfolio decision contracts"
```

### Task 2: Deterministic universe frame coordinator

**Files:**
- Create: `tests/test_universe_frame_e6.py`
- Create: `src/invest_engine/strategies/universe.py`

**Interfaces:**
- Consumes: Task 1 `UniverseDecisionFrame`, `UniverseFrameOutcome`, status/kind enums; existing `SessionCalendar`, `BarObservation`, `EventEnvelope`.
- Produces:
  - `UniverseFrameCoordinator(calendar, instruments, *, bar_interval=timedelta(minutes=1), checkpoint_interval=timedelta(minutes=30), full_session_duration=timedelta(minutes=390), max_bars=500_000)`
  - `accept(event: EventEnvelope[MarketPayload]) -> None`
  - `finalize(as_of: datetime) -> UniverseFrameOutcome`
  - `invalidate_instrument_history(instrument: InstrumentId) -> None`
  - read-only `observations: tuple[BarObservation, ...]`
  - read-only `halt_reason: str | None`.

- [ ] **Step 1: Write the failing complete-frame test**

Create two US instruments on different venues with venue-specific `TradingSession` values sharing the same start/end. Feed the exact 09:59–10:00 UTC-equivalent one-minute bar for both in contiguous journal order, then finalize 10:00.

```python
def test_complete_frame_is_cross_venue_sorted_and_deterministic():
    first = build_coordinator_and_finalize(events_in_ingest_order)
    second = build_coordinator_and_finalize(events_in_ingest_order)
    assert first.status is UniverseFrameStatus.COMPLETE
    assert first.frame == second.frame
    assert tuple(x.key for x in first.frame.instruments) == tuple(sorted(expected_keys))
    assert first.frame.kind is UniverseCheckpointKind.REBALANCE
```

Also assert a 15:30 normal-session checkpoint is FLATTEN and frame IDs change when a trigger event ID changes.

- [ ] **Step 2: Run the complete-frame test and verify RED**

Run: `python3 -m pytest tests/test_universe_frame_e6.py::test_complete_frame_is_cross_venue_sorted_and_deterministic -q`

Expected: import failure because `strategies.universe` does not exist.

- [ ] **Step 3: Implement minimal ingestion and complete-frame finalization**

Implementation rules:

- sort the constructor's immutable universe by key and reject duplicates, mixed markets/currencies or fewer than two members;
- accept only finalized, unflagged TIME bars at exactly `bar_interval` with an instrument in the universe;
- enforce unique ID, contiguous ordinal, monotonic known time and causal event time;
- resolve each observation through its venue calendar and retain at most `max_bars` in journal order;
- require aligned session start/end across all trigger observations, not equal venue strings;
- valid checkpoints are `session.start + N * checkpoint_interval`; N=1 through the point one hour before close are REBALANCE, and `session.end - checkpoint_interval` is FLATTEN;
- create `frame_id` as `"universe-frame:" + sha256(canonical UTF-8 JSON)` over session bounds, checkpoint, kind, ordered instrument keys and ordered trigger event IDs. Do not import `research.report`.

- [ ] **Step 4: Run the complete-frame test and verify GREEN**

Run: `python3 -m pytest tests/test_universe_frame_e6.py::test_complete_frame_is_cross_venue_sorted_and_deterministic -q`

Expected: PASS.

- [ ] **Step 5: Write failing incomplete/no-action tests**

```python
def test_missing_member_is_data_unavailable_not_partial_frame(): ...
def test_misaligned_sessions_fail_and_early_close_is_no_action(): ...
def test_checkpoint_outside_schedule_is_no_action(): ...
```

Assert missing keys are sorted and exact and the strategy-facing frame is `None`. Misaligned session bounds raise `InvalidEvent("UNIVERSE_SESSION_MISMATCH")` and latch the coordinator; early close and outside-schedule checkpoints return NO_ACTION with `NO_ACTION_EARLY_CLOSE` and `NO_ACTION_OUTSIDE_CHECKPOINT_SCHEDULE` respectively.

- [ ] **Step 6: Run those tests and verify RED**

Run: `python3 -m pytest tests/test_universe_frame_e6.py -k "missing_member or misaligned_sessions or outside_schedule" -q`

Expected: assertions fail because the outcomes are not implemented.

- [ ] **Step 7: Implement fail-closed frame outcomes**

Finalizing always advances an explicit watermark. It may return DATA_UNAVAILABLE or NO_ACTION, but it must never shrink the configured universe or call downstream strategy code.

- [ ] **Step 8: Run outcome tests and verify GREEN**

Run: `python3 -m pytest tests/test_universe_frame_e6.py -k "missing_member or misaligned_sessions or outside_schedule" -q`

Expected: PASS.

- [ ] **Step 9: Write failing clock and malformed-input tests**

```python
def test_late_bar_after_finalized_watermark_halts_coordinator(): ...
def test_duplicate_noncontiguous_flagged_unfinalized_and_wrong_interval_fail(): ...
def test_finalization_cannot_move_behind_observed_stream_or_previous_watermark(): ...
```

For each invalid input, assert `InvalidEvent` and a nonempty `halt_reason`; a second `accept`/`finalize` call must refuse recovery without reconstruction by replay.

- [ ] **Step 10: Run malformed-input tests and verify RED**

Run: `python3 -m pytest tests/test_universe_frame_e6.py -k "late_bar or duplicate_noncontiguous or finalization_cannot" -q`

Expected: assertions fail until clock/halt handling exists.

- [ ] **Step 11: Implement watermark, late-data and halt behavior**

`accept` must reject a bar whose `bar.end <= finalized_watermark`. `finalize` must reject a time earlier than either the last observed known time or the prior watermark. On any validation exception, freeze `halt_reason` exactly as `StrategyRunner` does; recovery is a fresh coordinator plus event replay.

- [ ] **Step 12: Run clock/input tests and verify GREEN**

Run: `python3 -m pytest tests/test_universe_frame_e6.py -k "late_bar or duplicate_noncontiguous or finalization_cannot" -q`

Expected: PASS.

- [ ] **Step 13: Write the failing split-history invalidation test**

```python
def test_invalidate_history_removes_only_one_instrument_without_rewinding_stream():
    coordinator = populated_coordinator()
    before_ordinal_and_watermark = coordinator audit properties
    coordinator.invalidate_instrument_history(first_instrument)
    assert all(x.instrument != first_instrument for x in coordinator.observations)
    assert any(x.instrument == second_instrument for x in coordinator.observations)
    assert coordinator audit properties == before_ordinal_and_watermark
```

- [ ] **Step 14: Run the invalidation test and verify RED**

Run: `python3 -m pytest tests/test_universe_frame_e6.py::test_invalidate_history_removes_only_one_instrument_without_rewinding_stream -q`

Expected: FAIL because invalidation is absent.

- [ ] **Step 15: Implement instrument-history invalidation**

Remove only matching `BarObservation` and its duplicate-bar key. Do not alter seen event IDs, last ordinal, last known time, watermark or frame hashes already returned.

- [ ] **Step 16: Run Task 2 tests and the full suite**

Run:

```bash
python3 -m pytest tests/test_universe_frame_e6.py -q
python3 -m pytest -q
```

Expected: both commands exit 0.

- [ ] **Step 17: Commit Task 2**

```bash
git add src/invest_engine/strategies/universe.py tests/test_universe_frame_e6.py
git commit -m "feat(strategy): synchronize multi-symbol decision frames"
```

### Task 3: Portfolio strategy runner and adversarial output validation

**Files:**
- Create: `tests/test_portfolio_runtime_e6.py`
- Create: `src/invest_engine/strategies/portfolio_runtime.py`

**Interfaces:**
- Consumes: Tasks 1–2 contracts/coordinator and existing `StrategySignal`.
- Produces:
  - `PortfolioEvaluation(frame_outcome: UniverseFrameOutcome, batch: PortfolioSignalBatch | None = None, reason_codes: tuple[str, ...] = ())`
  - `PortfolioStrategyRunner(strategy: PortfolioStrategy, coordinator: UniverseFrameCoordinator)`
  - `accept(event: EventEnvelope[MarketPayload]) -> None`
  - `evaluate(as_of: datetime) -> PortfolioEvaluation`
  - `invalidate_instrument_history(instrument: InstrumentId) -> None`
  - read-only `halt_reason: str | None`.

- [ ] **Step 1: Write the failing valid-dispatch test**

Create a trusted fixture strategy whose manifest permits US, one-minute bars, 30-minute checkpoints, two LONGs and 20% gross. It returns exactly one signal per frame instrument in sorted order, using each matching trigger event ID.

```python
def test_complete_frame_dispatches_once_with_read_only_causal_context():
    result = runner.evaluate(checkpoint)
    assert result.frame_outcome.status is UniverseFrameStatus.COMPLETE
    assert result.batch is not None
    assert fixture_strategy.calls == 1
    assert all(bar.known_at <= checkpoint for bar in fixture_strategy.last_context.bars)
```

Assert `snapshot`/`restore` remain strategy-owned and the runner does not import or expose allocation, trading state, account or broker objects.

- [ ] **Step 2: Run the dispatch test and verify RED**

Run: `python3 -m pytest tests/test_portfolio_runtime_e6.py::test_complete_frame_dispatches_once_with_read_only_causal_context -q`

Expected: import failure because `portfolio_runtime` does not exist.

- [ ] **Step 3: Implement minimal runner dispatch**

`accept` delegates to the coordinator. `evaluate` finalizes one frame, returns without calling the strategy for DATA_UNAVAILABLE/NO_ACTION, otherwise constructs `PortfolioStrategyContext(as_of, frame, coordinator.observations)` and calls `on_frame` exactly once.

- [ ] **Step 4: Run the dispatch test and verify GREEN**

Run: `python3 -m pytest tests/test_portfolio_runtime_e6.py::test_complete_frame_dispatches_once_with_read_only_causal_context -q`

Expected: PASS.

- [ ] **Step 5: Write failing no-dispatch and identity tests**

```python
def test_incomplete_and_no_action_frames_do_not_call_strategy(): ...
def test_batch_must_match_frame_manifest_time_members_and_triggers(): ...
```

Mutate one field at a time: frame ID, strategy ID/version, generated time, signal order, missing/extra instrument, child trigger ID, child strategy identity, generated time and expiry. Each mutation must raise `InvalidEvent`, latch runner `halt_reason`, and never return a partial batch.

- [ ] **Step 6: Run identity tests and verify RED**

Run: `python3 -m pytest tests/test_portfolio_runtime_e6.py -k "incomplete_and_no_action or batch_must_match" -q`

Expected: invalid batches are accepted until validation is implemented.

- [ ] **Step 7: Implement frame/manifest/batch identity validation**

Require signals to cover the ordered universe exactly once. Each signal's trigger must equal the corresponding trigger bar event ID, and every signal must share the frame time and manifest identity. Do not sort or repair plugin output.

- [ ] **Step 8: Run identity tests and verify GREEN**

Run: `python3 -m pytest tests/test_portfolio_runtime_e6.py -k "incomplete_and_no_action or batch_must_match" -q`

Expected: PASS.

- [ ] **Step 9: Write failing exposure-envelope tests**

```python
def test_batch_rejects_excess_long_count_and_gross_target(): ...
def test_exit_targets_and_valid_two_long_batch_pass(): ...
```

Hand-calculate Decimal totals. EXIT must have zero target under the existing `StrategySignal` contract. LONG count must not exceed `manifest.max_long_positions`; sum of LONG targets must not exceed `manifest.max_gross_target_fraction`.

- [ ] **Step 10: Run exposure tests and verify RED**

Run: `python3 -m pytest tests/test_portfolio_runtime_e6.py -k "excess_long or exit_targets" -q`

Expected: the deliberately excessive batch is not yet rejected.

- [ ] **Step 11: Implement exposure-envelope validation**

Use Decimal summation starting from `Decimal(0)`. This is a strategy-output envelope only; do not import or duplicate E3 pre-trade risk.

- [ ] **Step 12: Write the failing history-invalidation delegation test**

Write `test_runner_invalidation_delegates_without_resetting_strategy_or_stream` and assert only the selected instrument history disappears while the fixture strategy state and coordinator audit properties remain unchanged.

- [ ] **Step 13: Run the delegation test and verify RED**

Run: `python3 -m pytest tests/test_portfolio_runtime_e6.py::test_runner_invalidation_delegates_without_resetting_strategy_or_stream -q`

Expected: FAIL because runner delegation is absent.

- [ ] **Step 14: Implement history-invalidation delegation**

Delegate to `UniverseFrameCoordinator.invalidate_instrument_history` without calling strategy `snapshot`, `restore` or any account/runtime path.

- [ ] **Step 15: Run the delegation test and verify GREEN**

Run: `python3 -m pytest tests/test_portfolio_runtime_e6.py::test_runner_invalidation_delegates_without_resetting_strategy_or_stream -q`

Expected: PASS.

- [ ] **Step 16: Run Task 3 tests and the full suite**

Run:

```bash
python3 -m pytest tests/test_portfolio_runtime_e6.py -q
python3 -m pytest -q
```

Expected: both commands exit 0.

- [ ] **Step 17: Commit Task 3**

```bash
git add src/invest_engine/strategies/portfolio_runtime.py tests/test_portfolio_runtime_e6.py
git commit -m "feat(strategy): validate portfolio strategy batches"
```

### Task 4: ADR, project state and full verification

**Files:**
- Create: `docs/adr/0035-multisymbol-portfolio-decision-boundary.md`
- Modify: `docs/adr/README.md`
- Modify: `docs/E4_STRATEGY.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/ROADMAP.md`
- Modify: `AGENTS.md`
- Modify: `docs/superpowers/specs/2026-11-20-multisymbol-intraday-slot-momentum-design.md`

**Interfaces:**
- Consumes: verified behavior and exact test output from Tasks 1–3.
- Produces: an accepted offline-only ADR, authoritative current-state handoff and explicit PR-2/PR-3 remaining conditions.

- [ ] **Step 1: Write ADR-0035**

Record:

- context: current event-scoped runner cannot make synchronized cross-sectional decisions;
- decision: additive explicit-watermark universe barrier plus separate trusted portfolio protocol; existing single-instrument API unchanged;
- consequences: no partial universe, replay-dependent in-memory state, no order authority, larger history capacity;
- alternatives rejected: loosen current signal-instrument rule, independent per-symbol accounts, implicit wall-clock batching;
- revisit triggers: streaming/paper lifecycle, partial-universe policy, process isolation, Quote/Trade execution.

- [ ] **Step 2: Update design and architecture-facing docs**

Set the design status to accepted, link ADR-0035, add its index row, and describe only the implemented contract path in `E4_STRATEGY.md`. Keep PR-2 shared account and PR-3 strategy/research explicitly pending.

- [ ] **Step 3: Run complete local verification**

Run in this order:

```bash
python3 -m pytest -q
ruff check .
mypy src
python3 scripts/check_secrets.py
git diff --check
```

Expected: every command exits 0. Record the fresh pytest count and source-file count from mypy output; do not copy an earlier count.

- [ ] **Step 4: Reconcile STATUS/ROADMAP/AGENTS with actual evidence**

Add the branch/commit/PR state truthfully. If no PR/CI exists yet, label local verification as local and leave CI pending. State next work as PR 2 shared-account historical coordination; do not claim the slot-momentum strategy or profitability study exists.

- [ ] **Step 5: Re-run documentation-sensitive checks after reconciliation**

Run:

```bash
ruff check .
mypy src
python3 -m pytest -q
python3 scripts/check_secrets.py
git diff --check
```

Expected: every command exits 0 with the same test count as Step 3.

- [ ] **Step 6: Commit Task 4**

```bash
git add AGENTS.md docs/adr/0035-multisymbol-portfolio-decision-boundary.md \
  docs/adr/README.md docs/E4_STRATEGY.md docs/STATUS.md docs/ROADMAP.md \
  docs/superpowers/specs/2026-11-20-multisymbol-intraday-slot-momentum-design.md
git commit -m "docs: record multi-symbol portfolio boundary"
```

- [ ] **Step 7: Inspect final branch delta**

Run:

```bash
git status --short --branch
git log --oneline --decorate -5
git diff --stat origin/main...HEAD
```

Expected: clean feature branch containing only the accepted design plus PR-1 contracts/tests/docs. Do not create or merge a PR until current open PR overlap and CI requirements have been rechecked.
