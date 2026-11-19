# ADR-0027 — Offline timestamp-based walk-forward partitions

Status: Proposed; CI pending.

Predeclare elapsed UTC fold boundaries, expanding/rolling history, disjoint validation spans, embargo, final holdout date range and per-instrument minima. Partition timing metadata without features/labels or performance selection. Require feature availability at decision; purge train labels not available strictly before fit cutoff and evaluation labels unavailable by their partition end. Record all purges, gaps, blocked folds and canonical digests. Final metadata partition requires a locked research candidate and matching final windows, not evidence of privileged access isolation or fold-trained strategy performance. No fit or backtest runner yet; fold evidence linkage, licensed PIT data and G1/G2 remain pending. See [E6.3a](../E6_3_WALK_FORWARD.md).
