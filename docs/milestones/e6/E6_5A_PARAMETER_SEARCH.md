# E6.5a — Bounded fixed-rule parameter search

**Status:** implementation candidate; CI pending. E5 #6 remains open, E6/G2 not accepted, no Shadow/Paper/LIVE authorization.

## Previous evidence

#47 merged 9d9ee94 after Core CI and 32 successful historical regression jobs: 21 session-flat and 42 fee-aware eligible rows match prior common metrics, excluding runtime/revision digests. #48 merged 60a9d5d after type-narrowing correction, 374 tests each Python 3.12/3.13. #49 merged b931a70 after 378 tests each, including regime exposure and entry cohort integration. Both latter changes are optional research diagnostics; no separate historical rerun on their stacked heads. No regime profitability claim or independently eligible Kibot strategy window.

## Search contract

`SearchGrid` preregisters named ORB axes: US/KR opening minutes (1–60), previous sessions (1–20), ATR periods (2–100), volume multiplier (0.25–10, up to four decimal places). Fixed minute timeframe and shared allocation target; no risk-limit, investment capital or execution-policy optimization. Each axis must be an immutable, nonempty unique tuple. Canonical sorted axes and normalized Decimal scale yield deterministic full-grid candidate IDs. An absent market's opening parameter cannot vary. These bounds are implementation constraints, not recommendations of financially optimal parameters.

Budget can declare up to 64 candidate configurations and 4,096 distinct validation arms, including **both cash and entered-hold controls** and both base/stress conditions per fold and instrument. Reject any over-budget grid before execution; no silent truncation or performance-based trial expansion. Baselines are shared across all candidates. Trial/arm counts do not cap physical CPU or retries; repeated identical runs are idempotently reconciled by local journal. No external scheduler, parallelism or timeout control in this module.

`build_search_manifest` freezes grid ID, all actual candidates, walk-forward digest, common scenario digest, optional regime/exposure policy and arm count. `prepare_search` recomputes fold/timing coverage, requires a complete strict E5 matrix, and binds search manifest digest in each preregistered validation window context. Caller registers a matching immutable ResearchPlan with all returned windows, fixed candidates and reserved final ranges. `execute_search` re-derives manifest and config hashes before running; mismatched budget, parameters, context or data fail closed. Every declared strategy/control and cost arm runs through existing E5 + E6 report/journal bridge; failed arms remain explicitly failed, never optimized away. Returns all candidate assessments without auto-selection, final holdout access, strategy changes or promotion. Provisional imported evidence remains INCONCLUSIVE regardless of returns.

This is **exhaustive deterministic grid search**, not Bayesian/adaptive optimization, ML training, or real-market tuned parameters. Candidate assessment compares matched baselines, fees, MDD and fills under both scenarios, but no statistical multiple-testing correction or confidence interval yet. Registry gate and independently verified E5 inputs remain mandatory. A new grid against already examined validation periods can bias future research; fresh disjoint reserved holdouts and durable trial lineage rules still require work. Do not treat search budget as proof against data snooping. No new market sample results.

## Test and next

Four fixture tests cover stable enumeration, rejected out-of-budget and inactive/duplicate dimensions, two candidates + two controls × two costs × two folds = 16 actual E5 simulations with journal retry/reopen and no selection, altered manifest or registered budget blocked before execution. CI pending. Next E6.5b durable trial lineage and robustness metrics, then verified candidate pipeline with genuine final holdout and E5 acceptance.
