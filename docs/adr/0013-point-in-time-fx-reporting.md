# ADR-0013: FX valuation as an explicit, point-in-time research boundary

- Date: 2026-11-17
- Status: Accepted for **offline research only**

## Decision

Retain per-currency E3 cash/positions/risk and E5 per-currency results unchanged. Optionally ingest a separately versioned, hashed FX observation series for `HistoricalBacktest` report conversions. Require direct FX pairs and distinguish market event, publication, and receipt times. Every FX observation must be known at `as_of` and age must not exceed the configured threshold. Never backfill a newly received historical correction into previous points. Missing any base-currency valuation point suppresses aggregate P&L/drawdown instead of producing a partial optimistic curve. All observation IDs are included in the research audit output, with source/license *declared*, not independently verified.

## Rejected alternatives

- Assume a universal current FX value for all historical periods (look-ahead).
- Silently invert / triangulate rates or auto-fill missing days (execution and spread assumptions not supported).
- Insert synthetic currency buying power in E3 (breaks account risk invariants).
- Treat a data source label as verified license or market history (false confidence).

## Consequences

More fixture/data preparation; honest fail-closed report results. FX trading, broker rates, settlements, and true cost calibration remain separate deliverables. The E5 synthetic runner does **not** become production-ready via this ADR.
