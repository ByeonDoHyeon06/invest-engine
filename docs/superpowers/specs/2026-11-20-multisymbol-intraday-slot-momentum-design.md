# Multi-Symbol Intraday Slot-Momentum Research Design

**Status:** Accepted for staged offline implementation. PR 1 [#66](https://github.com/ByeonDoHyeon06/invest-engine/pull/66) is open at `52ce1da`; CI 44894840967 passed and latest merge review remains required. PR 2 shared-account execution/reporting is candidate [#69](https://github.com/ByeonDoHyeon06/invest-engine/pull/69) through `289980e` with 463 local tests; stacked CI pending. PR 3 strategy/controls/data research remains pending.

**Date:** 2026-11-20

**Tracking:** [Issue #65](https://github.com/ByeonDoHyeon06/invest-engine/issues/65), E5 #6 and E6 #7; decision boundary: [ADR-0035](../../adr/0035-multisymbol-portfolio-decision-boundary.md)

**Authority:** Offline research only. This design does not authorize Paper or Live trading and does not change the accepted E6.7 `Engine()` contract.

## Intent

The first strategy-development target is not another long-horizon rule. It is a long-only, multi-symbol US-equity intraday research path capable of producing tens of completed position cycles per normal session when the hypothesis emits enough valid signals.

The aim is to answer a narrower question than “find a profitable strategy”: can a causal cross-sectional time-of-day signal survive shared-capital portfolio constraints and conservative transaction-cost assumptions? Trade count is an observed strategy output and a capacity metric, never a quota. `NoAction` remains correct when no candidate clears the frozen rule.

Existing `NoTrade` and entered buy/hold arms remain the long-horizon controls. The current ORB family is not extended: repeated daily and raw-minute studies have not produced a candidate that beats the matched controls robustly, and the 2023 reduced-turnover replication rejects all frozen variants.

## Goals

- Add a deterministic, offline-only decision boundary that evaluates a fixed point-in-time universe at one synchronized instant.
- Run all selected symbols through one USD account, one cash balance, one E3 risk policy and one allocation decision.
- Preserve the existing single-instrument `Strategy`, `StrategyRunner` and `HistoricalBacktest` behavior without compatibility changes.
- Implement one frozen research hypothesis, `xs-slot-momentum@1.0.0`, rather than another parameter grid.
- Report completed position cycles separately from entry/exit fill counts, including daily trade-count distribution and cost drag.
- Reuse the existing E3 order/risk/ledger, E4 target allocation and E5 conservative later-bar fill path.
- Keep every result provisional until data provenance, point-in-time membership, costs and Quote/Trade execution evidence pass the existing gates.

## Non-goals

- No broker connection, credential request, real order or E7 Paper/Live route.
- No short selling, leverage, options, margin, overnight inventory or cross-currency funding.
- No promise or optimization target of a fixed number of daily trades.
- No ML fitting, automatic parameter search, adaptive threshold, strategy promotion or code mutation.
- No fabricated missing bar, quote, spread, corporate action, universe membership or historical receipt time.
- No claim that OHLCV fills certify executable prices.
- No E6.7 SDK API rename or change to its approved examples.

## Constraints and fixed calls

These are design calls made after the user chose “US first, KR later.” They are intentionally conservative and versioned; changing one after observing results creates a new strategy version and research plan.

- Initial market: US-listed common equities, USD, regular session only.
- Input: raw one-minute share-volume bars with aware UTC timestamps and exchange-session metadata.
- Research universe: one immutable, preregistered manifest containing 20–40 instruments. Membership, identity and corporate-action evidence must be evaluated for the entire run; missing evidence cannot be replaced by a survivor-only subset.
- Decision cadence: 30-minute session-relative checkpoints. Skip the opening 30 minutes and the final 30 minutes. A normal 09:30–16:00 ET session therefore permits new target decisions from 10:00 through 15:00 and a final flatten target at 15:30. Early-close sessions produce `NO_ACTION_EARLY_CLOSE` in v1.
- Warmup: 40 complete prior sessions per instrument and slot.
- Portfolio: at most two simultaneous long targets, 10% account target per selected symbol, at most 20% gross target exposure, no FX.
- Risk proposal: each LONG signal carries a stop exactly 1% below the last finalized one-minute close at the checkpoint for E3 pre-trade loss checks. It is not a broker stop. E5 protective execution remains disabled for this first hypothesis; checkpoint and final-flatten targets own exits.
- Entry hypothesis: rank a causal same-time-slot residual score; select at most two strictly positive scores. No minimum trade count and no cost-dependent signal threshold.
- Rebalance: each checkpoint emits a complete target set—LONG for selected instruments and EXIT for every other universe member. A retained selection stays at its target rather than being force-closed and reopened.
- Signal lifetime: five minutes for new LONG targets. For a 10:00 signal, the five bars starting 10:00 through 10:04 are eligible; the bar ending exactly 10:05 is processed first and any remainder is then canceled at 10:05. A bar starting at 10:05 is not eligible. Unresolved orders are canceled deterministically before a later checkpoint can replace their target. EXIT intent handling remains fail-closed if liquidity cannot complete it.
- Opening capital and risk: USD 100,000; `per_trade_planned_loss=0.0025`, `max_symbol_cost_fraction=0.10`, `max_total_cost_fraction=0.20`, `max_open_positions=2`, `max_daily_loss_fraction=0.01`, two-minute mark age, stop required and monitoring required. Held plus approved/pending BUY notional shares the 20% ceiling. A rotation cannot spend expected sale proceeds before its SELL fills.
- Cost arms: preserve the repository's existing 2022 fee-aware profiles. Base uses 10 bps commission per side plus 5 bps spread and 5 bps impact; stress uses 25 bps commission per side plus 20 bps spread and 20 bps impact. Both use 5% bar-volume participation, USD 0.01 tick/cash step, one-share lots, zero synthetic sell tax and the existing modeled SEC/TAF schedule. All flags continue to say that broker costs and charge dates are unverified.

The fixed 40-session, half-hour premise is motivated by Heston, Korajczyk and Sadka, “Intraday Patterns in the Cross-Section of Stock Returns” (2010), which reports continuation at equal half-hour positions across trading days and distinguishes it from sub-hour reversal associated with liquidity imbalance and bid-ask bounce. The paper motivates a hypothesis; it does not validate this implementation or guarantee persistence in the selected sample.

For a slot to have warmup, each of the immediately preceding 40 scheduled full sessions must contain all 30 one-minute bars for that slot for every required universe member. Incomplete sessions are not skipped in favor of older data. Missing minutes make that slot `WARMUP_INCOMPLETE` until the missing session falls outside the immediate 40-session window. Full-session completeness outside the relevant slot is reported but is not required by the score.

## Approaches considered

### 1. Expand ORB across more symbols

This would require the least engine work, but it repeats a family already negative in the repository’s daily, raw-minute and temporal sensitivity studies. It also still evaluates instrument accounts independently rather than testing capital competition. Rejected as the primary direction; retain its results as negative evidence.

### 2. Per-symbol VWAP or short-horizon reversal

This naturally creates frequent trades and is simpler than a synchronized portfolio. However, the relevant return reversal can be driven by temporary liquidity imbalance and bid-ask bounce. A bar-only fill model is particularly likely to convert those effects into simulated alpha. Deferred until QuoteTick/TradeTick spread and execution modeling exists.

### 3. Synchronized cross-sectional same-slot momentum

This requires a new universe barrier and shared-account coordinator, but it directly tests a multi-symbol hypothesis, naturally supports repeated decisions, and creates infrastructure that later portfolio strategies can reuse. Selected.

## Architecture

The new path is additive. Existing per-event strategies continue through `HistoricalBacktest` unchanged.

```text
ordered one-minute EventEnvelope stream
                 |
                 v
      UniverseFrameCoordinator
  (calendar + universe + explicit watermark)
                 |
       complete UniverseDecisionFrame
                 |
                 v
        PortfolioStrategyRunner
     (readonly history, no account writes)
                 |
       PortfolioSignalBatch
                 |
       existing allocate_targets
                 |
       existing E3 risk + order ledger
                 |
       existing later-bar fill policy
                 |
                 v
 PortfolioBacktestReport + decision audit
```

### Universe frame

`UniverseDecisionFrame` is an immutable offline research value with:

- deterministic `frame_id`;
- checkpoint `as_of`, session identity and slot index;
- exact ordered required-universe instrument keys;
- one finalized trigger observation per instrument for the exact interval `[as_of - 1 minute, as_of]`, whose `available_at` and `received_at` are not later than `as_of`;
- immutable causal history sufficient for the strategy; and
- explicit reason codes when a frame cannot be produced.

The coordinator consumes canonically ordered market events and advances only through an explicit watermark. Historical replay advances a checkpoint watermark after all source events known no later than that checkpoint have been consumed. Future streaming may reuse the contract, but this phase does not implement a running service.

No partial ranking is allowed in v1. If any required member lacks the finalized one-minute observation needed at a checkpoint, the whole checkpoint produces `DataUnavailable`/`UNIVERSE_FRAME_INCOMPLETE`; it does not silently remove the symbol. A missing mark for a held symbol also blocks new exposure and leaves the unresolved position visible rather than inventing a liquidation.

Input keeps the existing E0/E2 journal contract: contiguous global `ingest_ordinal` and nondecreasing `max(available_at, received_at)`, with the ordinal as the tie-break. The coordinator never invents a second ordering rule. Duplicate event IDs, duplicate instrument/interval bars, mixed sessions, late observations crossing a finalized watermark and non-USD instruments fail explicitly.

### Portfolio strategy boundary

Introduce a separate trusted-internal `PortfolioStrategy` protocol and runner instead of loosening the current `StrategyRunner` rule that a signal belongs to the triggering instrument.

The runner receives only an immutable `PortfolioStrategyContext`: current frame, prior complete frames, declared universe and deterministic feature values. It receives no `TradingRuntime`, mutable account, broker, database or network handle.

A successful evaluation returns one `PortfolioSignalBatch`. The batch is bound to the `frame_id`, strategy ID/version and generation time. It contains exactly one existing `StrategySignal` per required instrument:

- child `trigger_event_id` is that instrument’s causal trigger bar event ID;
- LONG for each selected instrument with a 10% target and 1% reference stop;
- EXIT with zero target for every non-selected instrument; and
- identical `generated_at` across the batch.

This shape lets the existing multi-instrument allocator and E3 risk path remain authoritative. The batch contract rejects duplicate/missing instruments, foreign trigger IDs, mixed timestamps, total LONG target above 20%, more than two LONG instruments and signals not sorted by instrument key.

### Strategy calculation

For instrument `i`, session `d` and 30-minute slot `s`:

1. Build the raw slot return from finalized one-minute bars: `close(i,d,s) / open(i,d,s) - 1`.
2. For each prior session, subtract the cross-sectional median of the same slot over the complete declared universe. This produces a market-relative residual without using a future benchmark constituent or FX series.
3. At checkpoint `s` on session `d`, take the median of instrument `i`’s residuals for exactly the prior 40 complete sessions at slot `s`.
4. Rank scores descending, with instrument key as the deterministic tie-breaker.
5. Select the first two instruments whose scores are strictly greater than zero. If fewer qualify, select fewer; if none qualify, every signal is EXIT.

Only prior-session returns enter the score. No bar from the slot being predicted, no current-day future suffix and no later-released membership or corporate-action observation may enter. Opening and closing slots are excluded rather than assigning them special parameters.

### Shared account and order lifecycle

`HistoricalPortfolioBacktest` is a single-use coordinator with one `TradingRuntime`, one virtual attribution ledger, one mark map and one deterministic E2 observation digest for the full universe. PR 2 is in-memory; it does not claim durable atomic order handoff or recovery.

At a decision checkpoint it:

1. cancels and confirms cancellation of unresolved replaceable entry orders from older frames;
2. runs the portfolio strategy once;
3. passes the complete child-signal tuple to `allocate_targets` once;
4. proposes deltas against the single current account state;
5. submits every proposal through existing E3 risk; and
6. records rejected, approved, no-action and unavailable outcomes distinctly.

Monitoring is not bypassed in the offline path. The coordinator supplies the session-opening USD equity baseline and complete causal marks to the existing E3 monitor before each new BUY decision, repeating the observation after any intervening state change. If the 1% daily-loss latch fires, no later BUY is eligible that session and the coordinator issues a complete EXIT target set. Missing marks suppress the loss calculation and block new exposure; they do not imply zero loss.

Fills remain eligible only on a later one-minute bar. Existing strict limit penetration, volume participation, fee, tax and adverse-fill policies are reused. Conflicting pending exits, stale marks, incomplete currency valuation, unsupported issuer actions and unresolved final inventory make the arm invalid rather than profitable-looking.

The final 15:30 target is all EXIT. Any position not liquidated by the modeled end-of-session policy makes that session/arm invalid; it is never marked as a successful flat day using an invented close.

### Corporate actions and identity (PR 3 preflight; not implemented by PR 2)

The PR-2 coordinator accepts market bars only and does not integrate a corporate-action schedule. Before a PR-3 market-data arm can run, multi-symbol windows cannot simply pretend dividend-paying names do not exist. The required preflight remains manifest-bound and caller-evidenced, and must distinguish actions that affect an overnight holding from those observed while the account is already flat:

- A cash-dividend ex-date may continue only when the account, virtual attribution and open-order state for that instrument are all zero at the session open. Record an explicit non-entitlement audit decision; create no receivable or cash. Raw unadjusted bars remain required.
- A witnessed session-open split uses the existing split contract. Because there is no overnight inventory, it creates no fill or cash, but it resets that instrument's slot-history cache and therefore makes the full universe warmup-incomplete until 40 new scheduled sessions exist.
- A dividend with pre-open holdings/orders, an intraday or incompletely specified split, merger, delisting, symbol change, ambiguous identity or missing action coverage blocks the whole arm.

This proposed narrow no-overnight dividend observation is not blanket corporate-action support and does not weaken the existing E5 PIT/provenance flags. It requires implementation and synthetic tests in PR 3 before any provider arm; absent that work, block the arm.

### Reporting and audit

Keep `BacktestReport` intact for compatibility and wrap it in a portfolio-specific report containing:

- `UniverseDecisionRecord` per attempted checkpoint: PR 2 records frame ID, completeness, selected keys, child signal IDs, intent/risk decisions, cancellations, fills and reason codes; PR 3 must add the frozen strategy's score/rank evidence for every member;
- completed position cycles, defined as an instrument transitioning from zero quantity to positive quantity and later back to zero; partial fills within one lifecycle are one cycle;
- per-session completed-cycle count, entries, exits, gross turnover, fees/taxes, gross and net PnL, and time in market;
- cross-sectional concentration: PnL and turnover by symbol, plus largest-symbol share;
- sessions/checkpoints blocked by missing data or unresolved inventory; and
- separate base/stress results using identical signals and input events; PR 3 owns the paired-arm orchestration.

The report must continue to label entry/exit fill counts as fills. It must not rename them “trades.” Currency remains separated; v1 accepts only USD.

## Research protocol

### Controls

Each declared window runs matched arms through the same shared-capital coordinator:

- `NoTrade` cash control;
- opening-rank hold control: at 10:00 use the same frozen score and choose up to the same two strictly positive names at 10% each, allow only the same five-minute entry window, never replace or rebalance them, and issue all EXIT at 15:30; it never holds overnight;
- deterministic placebo-rank control with the same two-position target ceiling and checkpoint schedule; and
- `xs-slot-momentum@1.0.0` under base and stress cost policies.

The placebo order is fixed by a manifest-bound hash of `(plan_id, session, slot, instrument_key)` and never by realized returns. It measures turnover/cost drag; it is not a claim of statistical significance.

### Data partitions

- Synthetic fixtures prove contracts first.
- The first concrete PR-3 development study is frozen to October and November 2022 with 40 prior scheduled sessions, using Alpaca raw SIP minute bars and the provider's corporate-action/asset metadata under the existing operator-owned secret workflow. It is explicitly provisional and reuses observed periods.
- Its frozen `US20-SLOT-V1` ranking universe is the first 20 US entries registered in `research/market_panel_v1.json`: AAPL, ACN, ADBE, CRM, DELL, GOOG, INTU, LRCX, META, MSFT, NFLX, NVDA, RMD, SAP, TSLA, TSM, AMZN, JPM, BAC and WFC. This ordering rule was fixed before this strategy's returns were observed; it is still a retrospective convenience cohort, not PIT index membership.
- Listing venue and identity are frozen from the provider asset response plus caller-declared mapping and retain `identity_verified=false`; ambiguous or absent mappings block the arm. The study does not infer venue from ticker spelling.
- Existing 2021–2023 US minute data outside that pilot may be used only as later development/provisional evidence after a new preregistration.
- Existing 2024–2025 partitions may be preregistered as temporal validation, but they are not called independent or blind because the broader panel and some prices/results have already been accessed.
- A final economic acceptance test requires a separately registered, access-controlled provider/instrument/time partition that was not inspected while designing or tuning this strategy.
- Current KRUS-80 membership is retrospective convenience metadata, not sufficient PIT membership evidence by itself.

Raw authorized provider data stays outside git and CI artifacts. Aggregate manifests, hashes, coverage, failures and reports may be persisted according to current repository policy.

### Acceptance and rejection

Implementation correctness and economic acceptance are separate.

The implementation is acceptable when deterministic synthetic and historical-compatibility tests pass, all signals are causal, shared-capital/risk invariants reconcile, blocked frames remain explicit and old single-instrument report hashes are unchanged.

The strategy is only an economic candidate when a preregistered validation matrix is complete and it:

- has positive aggregate net PnL under both base and stress costs;
- exceeds cash and the entered-hold control under both cost policies;
- exceeds the matched placebo after costs;
- does not depend on one symbol for more than 25% of positive net PnL;
- reports positive median session expectancy and no hidden final inventory; and
- preserves all failed/blocked windows in the denominator.

These are descriptive gates, not proof of future profitability. Failure rejects `xs-slot-momentum@1.0.0`; thresholds are not tuned on the failed sample.

For those gates, a session's expectancy is its net realized PnL—including modeled fees and taxes—divided by position cycles completed in that session. Zero-cycle sessions are excluded from the median but counted and reported separately; the median must be strictly positive. Symbol concentration is `largest positive symbol net PnL / sum of all positive symbol net PnL`; it is null and fails the gate when no symbol has positive net PnL. Aggregate net PnL must independently remain positive, so losses cannot be hidden by this concentration denominator.

Even a passing bar-based candidate cannot advance to Paper. QuoteTick/TradeTick spread, queue/marketability assumptions, actual dated broker/exchange charges, source rights, corporate-action completeness and point-in-time universe provenance remain mandatory gates.

## Failure behavior

- Incomplete universe checkpoint: no new targets, explicit `DataUnavailable` record.
- Late or duplicate observation: fail the replay; never reorder it silently after watermark finalization.
- Insufficient 40-session same-slot history: complete EXIT target set with `WARMUP_INCOMPLETE`.
- Unsupported early close: complete EXIT target set with `NO_ACTION_EARLY_CLOSE`.
- Corporate action without the existing modeled/PIT evidence: block the whole experiment.
- Unresolved entry order at replacement: cancel first; if cancellation cannot be represented deterministically, halt the arm.
- Unresolved exit or held position at finalization: invalidate the arm.
- Missing/stale held-symbol mark: equity incomplete and no new exposure.
- Currency or venue mismatch: configuration failure before replay.

## Compatibility and rollout

This is planned as three reviewable PRs under one dedicated issue:

1. **PR #66 open at `52ce1da`; CI 44894840967 passed, latest merge review required:** universe-frame and portfolio-strategy contracts with synthetic causal/barrier tests;
2. **Candidate [PR #69](https://github.com/ByeonDoHyeon06/invest-engine/pull/69) through `289980e`; stacked CI pending:** shared-account historical coordinator, monitored risk/order lifecycle, position-cycle reporting and old-hash compatibility tests. [Implementation boundary](../../E6_MULTISYMBOL_SHARED_ACCOUNT.md);
3. **Pending:** frozen strategy, controls, the exact `US20-SLOT-V1` October/November 2022 provisional workflow and result reconciliation.

The first implementation PR must add an ADR for the new portfolio decision boundary. `docs/STATUS.md`, `docs/ROADMAP.md`, E5 #6 and E6 #7 are updated with evidence at each merge. No PR checks an E5/E6 acceptance box merely because code tests pass.

E6.7 remains a separate SDK milestone. A later facade may expose portfolio evaluation through the already accepted typed-spec/capability design, but this project does not alter `Engine()` construction, permissions, examples or Paper/Live authority.

## Decisions left to the builder

- Whether the immutable score/rank value types live beside portfolio contracts or research reporting, provided no strategy module imports broker, database or network code.
- PR-3 strategy/control module split, fixture construction and parametrization style.
- Internal performance optimizations that preserve exact Decimal results, canonical ordering and run/config hashes.

## References

- Steven L. Heston, Robert A. Korajczyk and Ronnie Sadka, [“Intraday Patterns in the Cross-Section of Stock Returns”](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2010.01573.x), *Journal of Finance* 65(4), 2010.
- Lei Gao, Yufeng Han, Sophia Zhengzi Li and Guofu Zhou, [“Market Intraday Momentum”](https://doi.org/10.1016/j.jfineco.2018.05.009), *Journal of Financial Economics* 129(2), 2018. This is contextual evidence for market-level opening-to-close predictability, not the selected cross-sectional rule.
- Repository safety/evidence contracts: `docs/E5_BACKTEST.md`, `docs/E5_ROBUSTNESS.md`, `docs/E6_3_WALK_FORWARD.md`, `docs/E6_5B_SEARCH_LINEAGE.md`, `docs/E6_6_REDUCED_TURNOVER.md`, ADR-0010/0012/0027/0032/0034.
