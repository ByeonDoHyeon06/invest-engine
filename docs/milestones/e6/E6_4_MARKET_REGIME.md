# E6.4a — Causal market regimes and E5 execution attribution

**Status:** implementation candidate; CI pending. Depends on #47. E5 issue #6 remains OPEN; E6/G2 not accepted; no Shadow, broker or LIVE authority.

## Prior stage
PR #47 corrected independent replay ordinal defect and preflights zero-based contiguous ingestion ordinals. [Core CI](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44508558196) 364 tests each Python 3.12/3.13; 12 synthetic fixed-rule replay arms and durable journal test green. Follow-up head f298ec3 adds explicit ordinal regression test: [Core CI](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44508819498) successful, actual historical [session-flat](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44508819451) and [fee-aware](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44508819333) regression workflows still under review at registration. Merge parent first.

## Point-in-time classifier

`RegimePolicy` preregisters interval, number of trailing close-to-close returns, minimum absolute net change and directional efficiency, low/high RMS thresholds, and version. Default fixture hypothesis: minute interval, 20 returns (21 closes), trend absolute net move 0.3%, min efficiency 0.5, low RMS <= 0.05% and high RMS >= 0.3% per bar. These are arbitrary explicit research settings, **not calibrated thresholds**, not annualized volatility, not prediction probabilities. Changing the interval requires a separately chosen policy rather than claiming cross-timeframe equivalence.

`classify_regime` receives a stable instrument identity, explicit session calendar and as-of instant. Uses the exact trailing finalized time-bar grid ending at the most recent completed interval boundary within the SAME regular session. Only events with available_at and received_at <= decision time and bar end <= decision time; future suffix ignored. Exact start/end/event_time and event metadata, no flags, no duplicate IDs or timestamps, single source and positive observed volume. No overnight return, cross-session stitching, interpolation or forward-fill. Invalid, insufficient, stale/missing/late, zero-volume and mixed-source history yield uncertain/unknown and no-trade hypothesis, not invented zero volatility. Opening 20 returns cannot be classified until 21 complete observations under defaults.

Metrics:
- Net move = (last close - first close) / first close.
- Efficiency = abs(last-first) / sum(abs(consecutive close differences)); flat distance maps to zero.
- RMS simple return = sqrt(mean(square(consecutive simple returns))); no annualization or demeaning.
- Trend: RANGE if absolute net move strictly below threshold; otherwise UNCERTAIN if efficiency below minimum; otherwise UP or DOWN. No assumption that RANGE is mean-reverting.
- Volatility: LOW <= low threshold, HIGH >= high threshold, NORMAL otherwise; UNKNOWN when no valid grid. Separate axes; UP+HIGH is possible.
- Conservative long-only research flag: no-trade hypothesis on uncertain trend, downtrend or high volatility. It is an annotation, not an executable signal, no changes to risk policy or the treatment of existing protective exits. No reason code is a prediction of profit.

Output includes source event IDs and digest for complete data, policy hash, numeric metrics, reasons, classification and as-of. Source metadata/availability and calendar are caller supplied historical assertions, not independently witnessed receipt or trust. Corporate actions and cross-feed adjustments need separate E5 controls. Session-local returns are not a broad-market or stock-index macro regime.

## E5 attribution and E6 fold integration

`attribute_regimes` accepts only strict single-instrument E5 report/tape/window with matching dataset hash/event count, single-currency unsupported FX/terminal exclusions, unique event and fill IDs, finite valid fills. Classify each distinct fill bar at its **start**, excluding the fill bar's OHLC and later data. Group by trend/volatility, including unknowns and no-trade-hypothesis fills. Sum entry/exit fill counts, gross turnover, commissions, levies and realized exit PnL against original report totals; mismatch fails closed. Exit PnL is assigned to the exit-bar opening regime, NOT the entry regime, not causal attribution of strategy alpha, and not total mark-to-market PnL. There is no exposure denominator or regime-frequency measurement yet. No-trade baseline has zero fill groups, not missing performance evidence. This diagnostic does not claim optimal actions per regime.

Optional regime_policy on prepare_validation / execute_validation: pin policy digest within preregistered common scenario context, run normal E5 strategies unchanged, reconcile regime analysis before writing arm evidence, return RegimeStudy with run/report/policy hash and buckets. Omitting policy preserves prior context hash formula. The journal records base evidence and bound context only; detailed regime output is caller-retained and not persisted in journal yet. No filtering strategy orders according to these hypotheses. A failed attribution is an explicit failed arm, never zero PnL.

## Verification and next step

Ten new fixture cases incl independent trend/volatility axes, future suffix invariance, late receipt, gaps/invalid/duplicate and mixed source, outside session and zero volume, report total reconciliation and fill-bar exclusion, plus opt-in 12-arm synthetic fold replay. Tests pending; no live market regimes measured here. Next: regime-frequency/exposure denominators and entry-regime lot attribution; compare matched strategies on complete verified data; candidate generation / constrained parameter search (E6.5). E5 data eligibility, independently verified costs, PIT, corporate actions remain release blockers. Do not mark E6 released.
