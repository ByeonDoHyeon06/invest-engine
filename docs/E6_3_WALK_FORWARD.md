# E6.3a — Temporal walk-forward planner (offline)

**Status:** implementation candidate; CI pending. Depends on #45 (E6.2). No E5/G1 or E6/G2 release approval, Shadow or real orders. E5 issue #6 remains open.

## Prior stage

PR #45 initial Core CI failed Ruff B007 for two unused journal-head variables; corrected at f114f34. [Corrected Core CI](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44507038437) 354 tests each (3.12/3.13) plus static type/style and secrets checks passed. [Fee-aware regression](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44507038607) remains under review at the time of writing. This candidate is based on the corrected parent branch; merge parent first after regression verification.

## Contract

`SampleTiming` is timestamp metadata only: stable sample/instrument identity, decision time, latest feature availability, forward label start/end and label availability. All timestamps are timezone-aware and normalized to UTC. Reject future features, backward/empty labels and labels claiming availability before their actual end. A feature availability timestamp is an assertion, not independent PIT attestation.

`WalkForwardSpec` preregisters development and separate final holdout dates, UTC elapsed-duration train/validation/step/embargo, instrument universe, minimum train/validation counts per instrument, and expanding vs rolling mode. No random splits or dates selected from realized performance; validation step must be at least validation duration to avoid double-scored observations. These intervals are UTC elapsed durations, not exchange session counts or market calendar certification.

For each fold:
- Expanding train starts at the fixed development start; rolling train has the fixed duration. Train ends before embargo; validation follows. No incomplete final fold is invented.
- Train decisions are in [train_start, train_end). Purge any row whose label end/availability is not strictly before train_end. This handles variable forward horizons and delayed labels even when decision timestamps are inside the training partition.
- Validation decisions are in [validation_start, validation_end). Purge labels extending beyond or unavailable by validation_end. Later folds may train on past validation observations when their labels are known at fit cutoff; this is walk-forward, not the final unseen test.
- Record actual train/validation IDs, purged IDs, embargo IDs, counts per instrument and blockers. Too few rows block the fold; no adaptive date shifting or silent deletion. All registered instruments must meet both minima. Preserve all development IDs including unscored tail/step-gap rows.
- Sort by UTC decision time, instrument and stable identifier; reject duplicate IDs or duplicate instrument/decision, foreign instruments and any decision outside the declared development range. Digest pins spec, full ordered timestamp metadata, membership and blocked folds.

`prepare_holdout` is a logical guard accepting a separate final timing tape only if every development fold is eligible and a research registry has locked a candidate via validation, has not finalized its test, declares exactly the same final range for all registered instruments, same embargo and no development windows beyond the walk-forward development end. Reject reused development IDs (including rows never used in any fold), extra instruments, out-of-range times and delayed final labels; record insufficient holdout sample counts. The returned value pins plan/registry/candidate/config and final timing digests. No test result is recorded or finalized by this function. Caller must load authoritative registry from its journal and attest the selected candidate actually used the declared folds. It is **not** a data-access boundary or durable linkage of registry selection to exact fold evidence. Repeated metadata partitioning is permitted; existing journal handles one-use economic test only within one database. External data access, changed aliases, fabricated metadata, omitted observations, feature/label contents and independent source validation are not controlled.

## Scope / next

Six fixture tests: expanding/rolling chronology, deterministic ordering, disjoint scored validation, purged overlapping and delayed labels, per-instrument minima, lookahead/duplicate/foreign rows, locked final holdout and late-label/ID reuse. No model or strategy was fitted; no market-data performance claim. Next E6.3b: bind fold digests to durable run manifests, execute candidate training/evaluation exclusively against eligible fold slices and reconcile actual E5 evidence; then E6.4 as-of regime classification and E6.5 candidate search. Independent licensed market data, fees and PIT verification remain prerequisites to E6 release.
