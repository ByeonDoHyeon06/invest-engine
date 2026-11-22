# ADR-0029 — Causal session-local regime baseline

Status: Proposed; CI pending.

Use explicit trend and volatility axes over an exact single-session trailing grid of finalized bars received by the decision instant. Return uncertain/unknown on incomplete or conflicting inputs; do not infer zero returns. Thresholds are research hypotheses, not probabilities or automatic execution policy. Attribute E5 fills at the start of execution bars, reconcile costs and realized exits, keep unknown groups. Pin optional regime policy in fold preregistration; never replace orders or skip existing risk checks. No ML, verified market alpha, exposure denominators, or release approval. See [E6.4a](../milestones/e6/E6_4_MARKET_REGIME.md).
