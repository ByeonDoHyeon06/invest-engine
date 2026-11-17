# ADR-0014 — Fail-closed Point-in-Time market vintage and issuer metadata gate

- Date: 2026-11-17
- Status: Accepted for **offline research metadata gating only**
- Parent: Issue #6 / E5.6; supersedes no previous data adjustment policy

## Context

E5.5 added as-of FX research reporting. E5 still could not distinguish a vintage-correct original market bar from a future-adjusted revision, or detect corporate events invalidating synthetic inventory. Silently excluding a delisted company would create severe survivorship bias.

## Decision

- Keep the existing market/trading core event schema and synthetic research CLI. Add an optional pinned `pit_evidence` JSONL research boundary (`research/pit.py`) with dated membership, event-specific vintage, action-catalog coverage and dated corporate-action declarations.
- Check a data point's membership and exact vintage against information observable by that market event, not current-day membership/price revisions.
- Reject unknown, overlapping or postdated evidence, unsupported record shapes and any issuer action **effective within the experiment's time window**. Abort the **whole experiment**, not an instrument subset; there is no silently profitable no-action adjustment.
- Never infer a split ratio, dividend payment, delisting liquidation, old symbol mapping or adjusted/raw price factor. These are missing capabilities requiring an explicitly tested ledger model.
- Produce content-hashed `pit_gate.json` with a manifest field `pit_data_release_verified=false` even for synthetically successful examples. Provider declarations and checksum do not establish the truth or completeness of upstream historical data.
- Do not let this gate issue orders or change risk/portfolio allocation. Live remains unauthorized.

## Rejected alternatives

- Use a current constituents list for the entire past (survivorship bias).
- Accept post-event corrections as if known at bar time (look-ahead bias).
- Automatically apply unspecified adjusted-price ratios or dividend cash (invented accounting).
- Quietly remove split/delisted symbols from a successful backtest (selection bias).

## Consequences and future gates

This implementation adds useful, adversarial **input validation** with explicit limits; it is not a historical issuer ledger, provider authentication service or live-capable data feed. Real data ingestion, completeness checks, corporate-action execution, Tick/Quote fill testing, and market-specific fee/tax verification remain E5 OPEN. Do not close Issue #6 based on synthetic evidence alone.
