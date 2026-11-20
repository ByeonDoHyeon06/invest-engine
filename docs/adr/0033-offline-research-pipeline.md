# ADR-0033 — Unified offline development research orchestration

Status: Accepted for offline implementation; #52 merged `914439f`, CI 392 tests each, 42 historical rows unchanged. E6/G2 not accepted.

Compile the walk-forward, fixed parameter grid, matched cost scenarios, initial and reserved final metadata, and economic/stability policies into a deterministic prepared pipeline. Recompute before executing. Reuse existing strict E5 replay, SQLite reservation and evidence journal; reconstruct development-only review and canonical digest. No implicit lock, final holdout execution or promotion. Explicit validation close requires complete outcome matrix and may close with no eligible candidate. Prepared manifest retained by caller; provenance and external data isolation remain unverified. See [E6.6a](../E6_6A_RESEARCH_PIPELINE.md).
