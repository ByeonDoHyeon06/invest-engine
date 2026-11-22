# ADR-0024 — Independent-provider raw sample diagnostics

**Status:** Accepted for offline diagnostics (#43 verified; source eligibility blocked).

Use provider-specific parsing at the research boundary, preserve raw Decimal OHLCV, and explicitly declare price basis, coverage, timestamp start/receipt assumptions, rights and source file hash. Retain all scheduled-window missing/extra counts; only expose complete minute event streams to the existing strict evaluator. Never assume sparse minutes are zero volume or forward fill. Public workflow publishes aggregate results only; a source/strategy failure is distinct from a data preflight block. Use a separately declared fee scenario when dated retail/regulatory evidence does not cover source dates. See [E5.15b](../../evidence/reports/E5_15B_INDEPENDENT_PROVIDER.md). No live or E6 release approval.
