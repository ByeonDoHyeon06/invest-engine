# Multi-Symbol Shared-Account Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an offline-only multi-symbol historical coordinator that executes complete portfolio targets through one monitored USD account and reports completed position cycles without implementing or evaluating the slot-momentum strategy.

**Architecture:** Keep `HistoricalBacktest` and `BacktestReport` unchanged. Build an additive `HistoricalPortfolioBacktest` around one `EventRuntime`, one `PortfolioStrategyRunner`, one `TradingRuntime`, one `VirtualLedger` and one causal mark map; reuse the existing allocator, E3 risk/order ledger and E5 later-bar fill policy. A separate portfolio report wraps the unchanged account report and distinguishes fills from zero-to-positive-to-zero position cycles.

**Tech Stack:** Python 3.12+, frozen dataclasses, `Decimal`, aware UTC `datetime`, existing E0–E5 event/strategy/risk/fill contracts, pytest 9, Hypothesis, Ruff, mypy strict.

**Spec:** `docs/superpowers/specs/2026-11-20-multisymbol-intraday-slot-momentum-design.md`

## Global Constraints

- Implement only rollout PR 2: shared-account historical coordination, position-cycle reporting and legacy single-instrument hash compatibility.
- Do not implement `xs-slot-momentum@1.0.0`, score/rank calculation, controls, provider downloads, a real-data study, a profitability report, Paper/Live transport or E6.7 API changes.
- Preserve `HistoricalBacktest`, `BacktestReport`, their default behavior and the frozen single-instrument `run_sha256` exactly.
- Use one USD `TradingRuntime`, one cash ledger, one E3 `RiskLimits`, one `VirtualLedger`, one mark map and one E2 observation digest for the whole declared universe.
- Require `RiskLimits(require_monitoring=True, require_account_reference=False)`; no implicit FX, margin, shorting, non-USD funding or settlement-calendar claim.
- Every target delta passes `allocate_targets` once, `propose_simulated_intents` once and `TradingRuntime.submit`; strategy code never receives account mutation or order authority.
- Monitoring uses a session-opening USD equity baseline and complete causal marks; repeat it immediately before each BUY after any prior state change.
- A signal-generating checkpoint cannot fill from its trigger bars. Reuse strict later-bar penetration, shared per-bar participation, E3 fees/taxes and deterministic order ordering.
- New LONG remainders expire only after processing the five eligible bars ending through `generated_at + 5 minutes`; EXIT remainders are never silently canceled or treated as filled.
- Completed position cycles are zero quantity → positive quantity → zero quantity; entry/exit fill counts remain labeled as fills.
- Missing members, stale held-symbol marks, late bars, unresolved EXIT orders and final inventory remain explicit failures or unavailable outcomes; no subset ranking, invented price or invented liquidation.
- Domain values use finite `Decimal`, aware UTC timestamps and canonical instrument keys; identical input/config/strategy state must produce identical reports.
- The existing PR-1 worktree remains available for review; this stacked worktree is based exactly on commit `52ce1da` and the eventual PR targets `feat/multisymbol-portfolio-contracts` until PR #66 merges.

## Review Focus

- A delayed bar whose interval is already behind an explicit checkpoint watermark must fail replay, not repair a prior incomplete frame. Task 4 tests it.
- A held symbol with a missing or stale mark must suppress complete equity and block new BUYs; it must never be valued at zero or cost. Task 5 tests it.
- A partially filled BUY must process the bar ending exactly at its five-minute expiry before canceling only the remainder, and all partial fills must remain one position cycle. Tasks 2 and 4 test it.
- An unresolved SELL or positive position at the next replacement/final session boundary must invalidate the arm rather than fabricate a close. Task 4 tests both boundaries.
- Multiple BUYs and a simultaneous rotation must share reservations and marked exposure; expected SELL proceeds cannot fund a BUY before the SELL fills. Task 5 tests both cases.

---

## File Structure

- Modify `src/invest_engine/strategies/allocation.py`: optional marked-equity sizing input; default cost-basis behavior remains byte-for-byte compatible in output.
- Modify `tests/test_allocation_e4.py`: marked-equity sizing and validation cases.
- Modify `tests/test_backtest_e5.py`: freeze the current simple-run `run_sha256` as a legacy compatibility sentinel.
- Create `src/invest_engine/research/portfolio_report.py`: immutable portfolio execution, checkpoint, cycle, session, symbol and wrapper-report values plus deterministic summarization/export.
- Create `tests/test_portfolio_report_e6.py`: fill-versus-cycle, partial-fill, overlapping-exposure and concentration tests.
- Create `src/invest_engine/research/portfolio_backtest.py`: single-use historical scheduler, monitoring, shared order lifecycle, fills, attribution and final validation.
- Create `tests/test_portfolio_backtest_e6.py`: synthetic two-/three-symbol end-to-end and fail-closed cases.
- Create `docs/E6_MULTISYMBOL_SHARED_ACCOUNT.md`: implemented PR-2 boundary, lifecycle and limitations.
- Modify `docs/STATUS.md`, `docs/ROADMAP.md`, `AGENTS.md`, `docs/adr/0035-multisymbol-portfolio-decision-boundary.md` and the accepted design spec after verification; keep PR 3 and all evidence gates open.

### Task 1: Marked-equity target sizing and legacy hash sentinel

**Files:**
- Modify: `src/invest_engine/strategies/allocation.py`
- Modify: `tests/test_allocation_e4.py`
- Modify: `tests/test_backtest_e5.py`

**Interfaces:**
- Consumes: existing `AllocationPlan`, `TradingState`, `TradingConfig`, `MarketMark` and single-instrument `HistoricalBacktest` fixtures.
- Produces: additive parameter `target_equity_by_currency: tuple[tuple[str, Decimal], ...] | None = None` on `propose_simulated_intents(...)`; `None` preserves the existing cost-basis sizing path exactly.

- [ ] **Step 1: Add the frozen legacy hash assertion**

In `test_deterministic_and_same_instance_refused`, assert the existing five-bar fixture remains:

```python
assert a.run_sha256 == "a672226e12320db5baa11b48bf408c3296fcd9df07fa89e9e15b2e23c69b3642"
```

- [ ] **Step 2: Run the legacy test and verify GREEN before production changes**

Run: `.venv/bin/python -m pytest tests/test_backtest_e5.py::test_deterministic_and_same_instance_refused -q`

Expected: PASS with the frozen hash.

- [ ] **Step 3: Write failing marked-equity allocation tests**

Add:

```python
def test_proposal_can_size_against_explicit_marked_currency_equity(): ...
def test_marked_equity_requires_unique_supported_positive_currency_rows(): ...
def test_omitted_marked_equity_preserves_legacy_proposal(): ...
```

The first case must prove a USD equity value different from settled-cash-plus-cost-basis changes the target quantity. The validation case covers duplicate currency, missing instrument currency, non-`Decimal`, non-finite and non-positive equity.

- [ ] **Step 4: Run the new allocation tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_allocation_e4.py -k "marked_currency_equity or marked_equity or legacy_proposal" -q`

Expected: FAIL because `target_equity_by_currency` is not accepted.

- [ ] **Step 5: Implement the additive sizing parameter**

Update the exact signature:

```python
def propose_simulated_intents(
    plans: tuple[AllocationPlan, ...], *,
    state: TradingState, config: TradingConfig,
    marks: tuple[MarketMark, ...], as_of: datetime,
    max_mark_age: timedelta = timedelta(minutes=1),
    target_equity_by_currency: tuple[tuple[str, Decimal], ...] | None = None,
) -> tuple[OrderIntent, ...]: ...
```

When supplied, validate one finite positive `Decimal` per referenced currency and use it as the target-fraction denominator. Do not alter risk approval, cash reservation or the `None` branch.

- [ ] **Step 6: Run allocation and legacy tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_allocation_e4.py tests/test_backtest_e5.py -q`

Expected: PASS, including the frozen legacy hash.

- [ ] **Step 7: Commit Task 1**

```bash
git add src/invest_engine/strategies/allocation.py tests/test_allocation_e4.py tests/test_backtest_e5.py
git commit -m "feat(strategy): support marked portfolio target sizing"
```

### Task 2: Portfolio execution and position-cycle report model

**Files:**
- Create: `src/invest_engine/research/portfolio_report.py`
- Create: `tests/test_portfolio_report_e6.py`

**Interfaces:**
- Consumes: `BacktestReport`, `UniverseFrameStatus`, `InstrumentId`, `Side`, `Decimal`, aware UTC times and `research.report.sha256/canonical_json`.
- Produces:
  - `PortfolioSessionWindow(session_id: str, start: datetime, end: datetime)`.
  - `PortfolioExecutionRecord(execution_id, intent_id, source_frame_id, market_event_id, instrument, side, quantity, price, fee, tax, realized_pnl, occurred_at, position_before, position_after, session_id)`.
  - `UniverseDecisionRecord(as_of, status, frame_id=None, missing_instrument_keys=(), selected_instrument_keys=(), signal_ids=(), intent_ids=(), canceled_intent_ids=(), decisions=(), fills=(), reason_codes=())`.
  - `PositionCycle(instrument, session_id, opened_at, closed_at, entry_fill_ids, exit_fill_ids, entry_quantity, exit_quantity, turnover, fees, taxes, gross_pnl, net_pnl)`.
  - `PortfolioSessionSummary(session_id, start, end, completed_cycle_count, entry_fill_count, exit_fill_count, turnover, fees, taxes, gross_pnl, net_pnl, time_in_market)`.
  - `PortfolioSymbolSummary(instrument, completed_cycle_count, turnover, gross_pnl, net_pnl)`.
  - `PortfolioExecutionSummary(cycles, sessions, symbols, largest_positive_symbol_pnl_share)`.
  - `summarize_portfolio_executions(executions, session_windows) -> PortfolioExecutionSummary`.
  - `PortfolioBacktestReport(account_report, universe_decisions, executions, cycles, sessions, symbols, largest_positive_symbol_pnl_share, blocked_checkpoint_count, run_sha256, notes)` with deterministic `export(directory)`.

- [ ] **Step 1: Write failing value and one-cycle tests**

Add:

```python
def test_partial_entry_and_exit_fills_form_one_completed_cycle(): ...
def test_execution_transition_mismatch_or_cross_session_cycle_is_rejected(): ...
def test_fill_counts_remain_distinct_from_completed_cycles(): ...
```

Use two BUY partial fills followed by two SELL partial fills. Assert four fills, one cycle, conserved entry/exit quantities, net PnL equal to SELL realized deltas, and gross PnL equal to net plus all fees/taxes.

- [ ] **Step 2: Run the cycle tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_portfolio_report_e6.py -q`

Expected: collection fails because `research.portfolio_report` does not exist.

- [ ] **Step 3: Implement immutable values and exact cycle reconstruction**

Validate sorted deterministic inputs, exact before/after quantity transitions and aware UTC session membership. Keep open-cycle state internal to the summarizer; returned values are frozen/slotted dataclasses.

- [ ] **Step 4: Run the cycle tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_portfolio_report_e6.py -k "partial_entry or transition_mismatch or fill_counts" -q`

Expected: PASS.

- [ ] **Step 5: Write failing session, overlap and concentration tests**

Add:

```python
def test_session_time_in_market_is_union_of_overlapping_symbol_cycles(): ...
def test_zero_fill_session_is_reported_and_positive_symbol_share_is_exact(): ...
def test_no_positive_symbol_pnl_produces_null_concentration(): ...
def test_portfolio_report_export_is_canonical_and_repeatable(tmp_path): ...
```

Time in market is the union of intervals during which account aggregate quantity is positive, not the sum of overlapping symbol durations. Zero-cycle sessions remain present. Concentration is largest positive symbol net PnL divided by total positive symbol net PnL and is `None` when the denominator is zero.

- [ ] **Step 6: Run the new summary/export tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_portfolio_report_e6.py -k "time_in_market or zero_fill or no_positive or export" -q`

Expected: FAIL until aggregate summaries/export exist.

- [ ] **Step 7: Implement summaries and deterministic export**

Export `report.json`, `universe_decisions.jsonl`, `executions.jsonl`, `cycles.jsonl`, `sessions.jsonl` and `symbols.jsonl`; write the wrapped unchanged account artifacts under `account/`.

- [ ] **Step 8: Run all report tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_portfolio_report_e6.py -q`

Expected: PASS.

- [ ] **Step 9: Commit Task 2**

```bash
git add src/invest_engine/research/portfolio_report.py tests/test_portfolio_report_e6.py
git commit -m "feat(research): report portfolio position cycles"
```

### Task 3: Shared-account historical coordinator happy path

**Files:**
- Create: `src/invest_engine/research/portfolio_backtest.py`
- Create: `tests/test_portfolio_backtest_e6.py`

**Interfaces:**
- Consumes: Tasks 1–2, `UniverseFrameCoordinator`, `PortfolioStrategyRunner`, `EventRuntime`, `TradingRuntime`, `VirtualLedger`, `allocate_targets`, `eligible_fill`, `BarFillPolicy` and `SessionCalendar`.
- Produces:
  - `PortfolioBacktestSettings(run_version="e6-portfolio-shared-account-v1", max_history_bars=500_000, code_sha="UNPINNED", dataset_source="caller-supplied", data_license="caller-responsible")`.
  - `HistoricalPortfolioBacktest(*, calendar, instruments, strategy, config, opening_cash, risk, fill_policy=None, allocation_policy=None, settings=None)`.
  - `config_digest() -> str`.
  - `run(events: tuple[EventEnvelope[MarketPayload], ...]) -> PortfolioBacktestReport`.

- [ ] **Step 1: Write the failing two-symbol end-to-end test**

Create a 390-minute US session fixture whose portfolio strategy emits two 10% LONG targets at the first complete checkpoint and all EXIT targets at FLATTEN. Feed complete checkpoint trigger bars, later penetrating fill bars and session-end bars.

```python
def test_two_symbols_share_one_monitored_account_and_fill_only_later(): ...
```

Assert one strategy call per complete frame, no trigger-bar fills, two later entry fills, two later exit fills, two completed cycles, one USD account report, exact 20% peak target, one virtual/account quantity audit and zero final inventory.

- [ ] **Step 2: Run the happy-path test and verify RED**

Run: `.venv/bin/python -m pytest tests/test_portfolio_backtest_e6.py::test_two_symbols_share_one_monitored_account_and_fill_only_later -q`

Expected: collection fails because `research.portfolio_backtest` does not exist.

- [ ] **Step 3: Implement constructor validation and deterministic scheduling**

Reject non-USD/mixed universe, incomplete instrument rules, non-immediate settlement, monitoring disabled, account-reference requirements, duplicate opening currencies and reused instances. Register calendar session windows from the first observed bar; schedule the regular `checkpoint_interval` grid and always include the independent flatten watermark at `session.end - checkpoint_interval`, even when it is off-grid; finalize a watermark only after the known clock advances beyond it or at EOF.

- [ ] **Step 4: Implement the minimal checkpoint-to-order path**

At a complete checkpoint: observe marks/baseline, run the strategy once, allocate the complete batch once, size deltas from monitored USD equity once, submit every intent through E3, create attribution tickets only for approved intents and call `accept_simulated`. Record unavailable/no-action/approved/rejected outcomes distinctly.

- [ ] **Step 5: Implement later-bar fills and the wrapped report**

Before updating the bar mark, evaluate only previously accepted orders with `eligible_fill`; apply E3 fill, virtual attribution and exact `PortfolioExecutionRecord`. At session end require terminal orders and zero inventory, audit the virtual ledger, calculate the unchanged-style account metrics, then call Task 2 summarization.

- [ ] **Step 6: Run the happy-path and deterministic rerun tests and verify GREEN**

Add `test_portfolio_replay_is_deterministic_and_single_use`, then run:

`.venv/bin/python -m pytest tests/test_portfolio_backtest_e6.py -k "two_symbols or deterministic" -q`

Expected: PASS and identical `config_digest`, account `run_sha256` and portfolio `run_sha256` across fresh instances.

- [ ] **Step 7: Run related regressions**

Run: `.venv/bin/python -m pytest tests/test_portfolio_contracts_e6.py tests/test_universe_frame_e6.py tests/test_portfolio_runtime_e6.py tests/test_backtest_e5.py -q`

Expected: PASS including the legacy hash sentinel.

- [ ] **Step 8: Commit Task 3**

```bash
git add src/invest_engine/research/portfolio_backtest.py tests/test_portfolio_backtest_e6.py
git commit -m "feat(research): coordinate shared-account portfolio replay"
```

### Task 4: Entry lifetime, replacement and fail-closed finalization

**Files:**
- Modify: `src/invest_engine/research/portfolio_backtest.py`
- Modify: `tests/test_portfolio_backtest_e6.py`

**Interfaces:**
- Consumes: Task 3 coordinator and each allocation plan's `expires_at`.
- Produces: exact BUY expiration/cancellation, older-frame replacement cancellation, unresolved EXIT/final inventory validation and decision-record fill/cancel linkage.

- [ ] **Step 1: Write failing five-minute lifetime tests**

Add:

```python
def test_entry_expiry_processes_last_eligible_bar_then_cancels_remainder(): ...
def test_bar_starting_at_expiry_cannot_fill_canceled_entry(): ...
def test_later_checkpoint_cancels_replaceable_buy_before_new_targets(): ...
```

The first test uses partial volume across bars starting 10:00 through 10:04, verifies cancellation at the observation ending 10:05, and later completes one—not multiple—position cycle. The second proves a bar starting at 10:05 is ineligible.

- [ ] **Step 2: Run lifetime tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_portfolio_backtest_e6.py -k "entry_expiry or starting_at_expiry or replaceable_buy" -q`

Expected: FAIL because BUY expiration/cancel linkage is absent.

- [ ] **Step 3: Implement BUY expiration and replacement cancellation**

Store approved BUY intent expiry and source frame. Process eligible fills first; after a bar whose end reaches expiry, request and confirm cancellation of only ACCEPTED/PARTIALLY_FILLED BUY remainder. Before every later checkpoint, cancel any older replaceable BUY in deterministic intent-ID order. Append cancellations and expiry reason codes to their source `UniverseDecisionRecord`.

- [ ] **Step 4: Run lifetime tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_portfolio_backtest_e6.py -k "entry_expiry or starting_at_expiry or replaceable_buy" -q`

Expected: PASS.

- [ ] **Step 5: Write failing unavailable/late/exit/final-inventory tests**

Add:

```python
def test_incomplete_checkpoint_records_data_unavailable_without_strategy_or_order(): ...
def test_delayed_bar_behind_finalized_watermark_fails_replay(): ...
def test_unresolved_exit_at_replacement_checkpoint_invalidates_arm(): ...
def test_unresolved_final_inventory_invalidates_session(): ...
```

- [ ] **Step 6: Run failure tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_portfolio_backtest_e6.py -k "incomplete_checkpoint or delayed_bar or unresolved_exit or final_inventory" -q`

Expected: FAIL until explicit finalization guards exist.

- [ ] **Step 7: Implement fail-closed session/order boundaries**

Never cancel an EXIT to make a report look flat. An unresolved SELL at the next checkpoint, any nonterminal order at session close, or positive quantity at session close raises `InvalidEvent`. Preserve incomplete checkpoint records and let the PR-1 coordinator reject a later bar at/before its watermark.

- [ ] **Step 8: Run all lifecycle tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_portfolio_backtest_e6.py -k "expiry or replaceable or incomplete or delayed or unresolved or final_inventory" -q`

Expected: PASS.

- [ ] **Step 9: Commit Task 4**

```bash
git add src/invest_engine/research/portfolio_backtest.py tests/test_portfolio_backtest_e6.py
git commit -m "feat(research): enforce portfolio order lifetimes"
```

### Task 5: Monitoring, shared exposure and daily-loss exit overlay

**Files:**
- Modify: `src/invest_engine/research/portfolio_backtest.py`
- Modify: `tests/test_portfolio_backtest_e6.py`

**Interfaces:**
- Consumes: session windows, current causal marks, E3 `MonitorInput`/`SessionBaseline`, Task 3 checkpoint path.
- Produces: fresh per-BUY monitoring, shared reservation/exposure decisions and risk-owned all-EXIT override after daily-loss latch.

- [ ] **Step 1: Write failing shared-capital tests**

Add:

```python
def test_multiple_buys_reobserve_after_state_change_and_share_total_cap(): ...
def test_rotation_cannot_spend_pending_sale_proceeds(): ...
```

Use a strategy manifest broad enough to propose more exposure than E3 permits. Assert deterministic approvals/rejections from the one runtime, the second BUY is assessed after the first reservation, and a pending SELL does not increase settled buying power or remove held marked exposure.

- [ ] **Step 2: Run shared-capital tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_portfolio_backtest_e6.py -k "multiple_buys or pending_sale" -q`

Expected: FAIL until per-BUY re-observation and shared exposure handling are complete.

- [ ] **Step 3: Implement session baseline and per-BUY re-observation**

At each new session require a flat prior account and capture settled-plus-unsettled USD as the immutable opening baseline. Before every BUY submission, journal `MonitorInput` with all current universe marks sorted by instrument key and the session baseline, even when a prior SELL/BUY reservation changed state. Submit anyway when monitoring is unhealthy so E3 records the explicit rejection; never bypass `_monitor_buy_reasons`.

- [ ] **Step 4: Run shared-capital tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_portfolio_backtest_e6.py -k "multiple_buys or pending_sale" -q`

Expected: PASS.

- [ ] **Step 5: Write failing stale-mark and daily-loss tests**

Add:

```python
def test_stale_held_symbol_mark_blocks_new_exposure_without_zero_valuation(): ...
def test_daily_loss_latch_replaces_longs_with_complete_exit_targets(): ...
def test_daily_loss_latch_survives_later_rebound_within_session(): ...
```

The loss fixture first fills a position, then marks it low enough to reach exactly the configured 1% account loss. Assert no later BUY is approved, every held symbol receives an EXIT proposal, the audit record includes `DAILY_LOSS_LIMIT`/`DAILY_LOSS_EXIT_OVERRIDE`, and a rebound does not clear the session latch.

- [ ] **Step 6: Run risk-monitoring tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_portfolio_backtest_e6.py -k "stale_held or daily_loss" -q`

Expected: FAIL until the risk overlay exists.

- [ ] **Step 7: Implement the all-EXIT risk overlay**

Observe the account before strategy execution at each complete checkpoint. Still run and audit the trusted strategy once, but when the session is latched replace the execution input—not the recorded strategy batch—with one synthetic EXIT signal per universe member and call `allocate_targets` exactly once. Keep risk signal IDs/reasons deterministic and frame-bound.

- [ ] **Step 8: Run all monitoring tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_portfolio_backtest_e6.py -k "multiple_buys or pending_sale or stale_held or daily_loss" -q`

Expected: PASS.

- [ ] **Step 9: Commit Task 5**

```bash
git add src/invest_engine/research/portfolio_backtest.py tests/test_portfolio_backtest_e6.py
git commit -m "feat(research): enforce monitored shared portfolio risk"
```

### Task 6: Documentation, full verification and PR evidence

**Files:**
- Create: `docs/E6_MULTISYMBOL_SHARED_ACCOUNT.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/ROADMAP.md`
- Modify: `AGENTS.md`
- Modify: `docs/adr/0035-multisymbol-portfolio-decision-boundary.md`
- Modify: `docs/superpowers/specs/2026-11-20-multisymbol-intraday-slot-momentum-design.md`

**Interfaces:**
- Consumes: verified Tasks 1–5 and actual local/CI results.
- Produces: authoritative PR-2 scope, limitations, replay instructions and exact remaining PR-3/evidence gates.

- [ ] **Step 1: Write the implementation-boundary document**

Document the public constructor, one-account data flow, explicit watermark scheduling, monitoring/baseline behavior, five-minute BUY lifetime, unresolved EXIT/final inventory failures, fill-versus-cycle definitions and export artifacts. State prominently that no strategy profitability, Quote/Trade executability, provider/PIT evidence, Paper or Live authority was added.

- [ ] **Step 2: Update durable project state without closing gates**

Record PR 2 as candidate/verified only according to actual evidence. Keep E5 #6, E6 #7, G1/G2, PR 3, independent data/cost/identity/holdout and all Paper/Live gates open. Do not produce a profitability report in this PR.

- [ ] **Step 3: Run targeted tests**

Run: `.venv/bin/python -m pytest -q tests/test_allocation_e4.py tests/test_backtest_e5.py tests/test_portfolio_contracts_e6.py tests/test_universe_frame_e6.py tests/test_portfolio_runtime_e6.py tests/test_portfolio_report_e6.py tests/test_portfolio_backtest_e6.py`

Expected: PASS.

- [ ] **Step 4: Run complete local verification**

Run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/python scripts/check_secrets.py
```

Expected: every command exits 0; the final pytest count is greater than the 433-test baseline.

- [ ] **Step 5: Review the diff and compatibility boundary**

Run:

```bash
git diff --check
git diff --stat 52ce1da...HEAD
git status --short
```

Confirm `src/invest_engine/research/backtest.py`, `research/report.py`, E6.7 SDK examples/contracts and all broker/network modules are untouched.

- [ ] **Step 6: Commit verified documentation**

```bash
git add docs/E6_MULTISYMBOL_SHARED_ACCOUNT.md docs/STATUS.md docs/ROADMAP.md AGENTS.md docs/adr/0035-multisymbol-portfolio-decision-boundary.md docs/superpowers/specs/2026-11-20-multisymbol-intraday-slot-momentum-design.md
git commit -m "docs: record shared-account portfolio replay"
```

- [ ] **Step 7: Push the stacked branch and create/update the PR**

Push `feat/multisymbol-shared-account-backtest`, open the PR against `feat/multisymbol-portfolio-contracts`, link Issue #65/E5 #6/E6 #7, list the design/ADR/verification commands and state that PR #66 must merge first.

- [ ] **Step 8: Wait for CI and record exact evidence**

Require Python 3.12/3.13 pytest, Ruff, mypy and credential guard success. Update PR body, Issue #65 and authoritative docs with the actual run URL/counts; do not mark PR 2 merged or PR 3 started while checks are pending.
