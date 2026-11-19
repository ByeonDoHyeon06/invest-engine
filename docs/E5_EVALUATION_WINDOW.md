# E5.12 — Fixed evaluation windows (research infrastructure)

Predeclare a single instrument, exact first/last evaluation session boundaries in UTC, and at least 20 preceding complete sessions. NoTrade, initial-entry-and-hold, ORB are independently runnable under the same explicit capital, risk, fee and fill assumptions. New optional RunRequest:

```json
"evaluation_window": {
  "start": "2026-10-01T13:30:00Z",
  "end": "2026-10-30T20:00:00Z",
  "warmup_sessions": 20,
  "price_basis": "RAW_UNADJUSTED",
  "market_coverage": "CONSOLIDATED"
}
```

Dates are illustrative; verify venue sessions/holidays and provider records. Configured sessions must be precisely the warm-up and evaluation sessions. Each minute must be present once and in chronological order, with finalized raw price, integral share volume, no flags, availability no earlier than close and receipt less than one minute after close. A zero-volume bar is not proof of a trade; do not fabricate it to fill gaps. A sparse single-exchange series may fail this strict contract.

The CLI requires dataset.volume_unit SHARES and SHA-pinned PIT evidence for every event and action coverage. The initial fixed-window mode deliberately accepts **no-action intervals only**, with no modeled issuer actions; do not select windows after observing performance. The simulator declares all provider release flags false. Metadata and timestamps are caller declarations, not external verification.

Warm-up events enter E2 replay and strategy history/counts but do not call the strategy, place orders, or enter the equity series. Decisions contain WARMUP_ONLY rows. report.event_count counts all input events; manifest.evaluation_coverage gives separate bar/session counts. Configuration hash pins the window. Missing history capacity fails closed. Legacy runs without the option are unchanged.

The buy-hold-baseline 1.0.0 parameters are interval (PT1M), target_fraction and stop_fraction (decimal strings). It proposes one entry per instrument during evaluation, then holds. No guarantee of fill; stop is a sizing plan, not an active exit; protection must be disabled for this comparator. ORB 1.0.0 remains the original long-entry hypothesis, not automatically a session-flat day trading system. Results may differ due to risk checks and unfilled orders. Use separate output directories for each baseline/cost run.

Real-data acceptance remains OPEN: no real minute dataset has been downloaded or independently validated in this change. Provider license, completeness, corrections, venue coverage, issuer actions and actual trading cost rules still need verification. No real order or broker connection.
