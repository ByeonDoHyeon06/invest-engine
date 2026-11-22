# E5.10 — Terminal delisting boundary, offline research only

**Status:** a narrow E5 extension. This is NOT a delisted-position valuation engine, historical issuer-data certificate, or live-trading component.

## Purpose and conservative scope

A delisted instrument cannot be valued by carrying forward its last traded price, assuming a zero recovery, or silently removing its holdings. OHLCV alone cannot reveal a cash recovery, sale proceeds, merger consideration, bankruptcy distribution, or legal settlement date.

E5.10 allows an *explicitly declared delisting action* only when **no shares remain held** and **no unresolved order exists** at the last confirmed historical bar. The action is journaled using E3 `TradingRuntime.flag_delisting` and blocks subsequent simulated entries. A strategy signal emitted by the last bar is discarded, not submitted. This is a narrow research capability, NOT a way to exclude loser stocks or a permission to claim a bias-free universe.

The experiment is aborted, with no fabricated P&L, if shares are still held or an order remains active at the boundary. A later separately specified terminal-cash treatment, independently evidenced and tested, is required for held delistings.

## Input and reproducibility

New optional top-level field alongside the existing `pit_evidence` (required when enabled):

```json
"delisting_replay": {
  "records_jsonl": "delistings.jsonl",
  "sha256": "<64 lowercase hexadecimal characters>",
  "source": "research-provider-or-test-fixture",
  "license": "operator-declared-license"
}
```

Each JSONL line must have exactly this schema:

```json
{
  "kind":"delisting",
  "action_id":"delist-id-1",
  "instrument_key":"US:XNAS:US0378331005",
  "effective_at":"2026-10-30T20:00:00+00:00",
  "available_at":"2026-10-29T20:00:00+00:00",
  "source":"research-provider-or-test-fixture"
}
```

The matching PIT `corporate_action` record must be `action_type: "DELIST"` with identical `action_id`, instrument, effective time and source, and its `received_at` must equal the schedule's `available_at`. Announcement must already be known at the modeled boundary; future information cannot be backfilled. The schedule file is SHA-256 pinned and must have exactly one witness bar ending at `effective_at`. Events from that instrument at or after the delisting boundary are rejected. Data is processed in its given, verified replay order, without a network/broker call.

The previous E5.9 config/run hashes remain unchanged when `delisting_replay` is omitted. When supplied, the deterministic schedule terms become part of the config/run hash. The report decision trace adds `DELISTING_BLOCKED:<action_id>`. The manifest contains `delisting_schedule_sha256`; the PIT gate remains `data_release_verified=false`.

## Fail-closed acceptance rules

- No `pit_evidence` → configuration rejected.
- Missing, changed or noncanonical schedule, duplicate IDs/symbols, future-known action → rejected.
- Missing last confirmed time-bar boundary, later price events, overlapping scheduled corporate actions → rejected.
- Held shares or unresolved order at delisting → `InvalidEvent`, backtest aborted. No recovery value is invented.
- PIT mismatch/unknown unmodeled issuer action → run rejected before results are exported.
- No paid settlement, synthetic disposition or proceeds are produced by this module.

## Remaining E5/E7 gates

Real provider provenance and historical revisions, *all* delisted members of the research universe, actual 1m share volume, validated exchange/corporate action calendar, market-specific fees/FX, tick/quote execution and **delisted holdings resolution** are still open. E5 Issue #6 stays open and Live remains NOT AUTHORIZED. A user's historical daily-bar AAPL replay is not a 1-minute ORB performance backtest.
