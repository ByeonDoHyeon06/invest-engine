# E1.2 — Trading Sessions & Resolution-Agnostic Resampling

**Status:** Implemented, verified and merged in [PR #13](https://github.com/ByeonDoHyeon06/invest-engine/pull/13), [CI passed](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43713285009) for Python 3.12 and 3.13.

## Scope

- Explicit `TradingSession(market, venue, start, end)` and caller-injected `SessionCalendar` protocol.
- `session_from_local` converts exchange wall times to UTC with IANA zoneinfo and rejects DST non-existent/ambiguous times.
- `StaticSessionCalendar` validates overlap and never invents holidays, early-close dates, market schedules or venues. The source calendar is an explicit dependency and must be licensed/verified for real datasets.
- `resample_time_bars(events, resolution, calendar)` accepts typed, finalized TradeTick or TIME Bar input, and returns deterministic finalized Bar envelopes.
- Time buckets are anchored to session start, not midnight UTC. The final bucket ends at published session close even if nominal interval does not divide total session duration.
- No synthetic empty bars, no fallback to old prices, no automatic descending-resolution reconstruction. Incomplete input Bar sequences, mixed Trade/Bar for same instrument, multiple un-deduplicated providers, quarantined events, unknown sessions all fail explicitly.
- Output event available_at is max of session bucket end and input publication times; received_at is max of output availability and input receipts. Availability is not falsely moved earlier to optimize a backtest.

## Examples

Market session 09:30–16:00 NY local; 30-minute buckets start 09:30, 10:00, ... regardless of UTC offset. DST will change UTC open but **not** NY local open.

Input 1-minute bars 09:30–10:00 inclusive coverage → one complete 30-minute aggregate.
Input 1-minute bars 09:31–10:00 (missing 09:30) → explicit InvalidEvent, **no backfilled bar**.

A short session 09:00–11:45 with 1-hour target interval ends with a 45-minute bucket. Its Bar interval field is the **nominal configured duration**, whereas start/end express the actual truncated time span. Consumers must inspect start/end to calculate actual duration.

## Data assumptions and limitations

- All inputs are from one provider per instrument to prevent duplicated volume.
- This is **offline batch** aggregation and treats the supplied historical dataset as fully delivered. Live watermark-based finalization is for E7; no trading should consume a partial bucket unless the strategy explicitly supports partial features in future.
- For trade data, inactive/no-trade gaps do not produce artificial candles.
- For source time bars, the code requires complete coverage per aggregate bucket; it does not infer missing bars are no-trade minutes.
- No settlement, corporate actions, adjusted price transformation, market-holiday calendar discovery, raw/normalized persistence, or trade execution logic is implemented here.
- Arbitrary positive timedelta is accepted, but session/calendar validation is a necessary prerequisite. Unsupported lower-resolution requests are rejected.
- Deterministic output ID is derived from constituent event IDs, source identity, instrument and aggregate window; the source dataset/provenance still belongs in E1.3 manifest.
- `event_time` is the aggregate bar end. `available_at` and `received_at` are conservatively propagated and only finalized results enter downstream research.

## Validation

    python -m pip install -e ".[dev]"
    ruff check .
    mypy src
    python -m pytest -q

Synthetic tests verify TradeTick→1m, source 1m→30m, no fake missing intervals, DST transition, DST invalid local hour, early close truncation, duplicate/quality rejection, sub-bar loss of information and deterministic replay.

## Next
E1.3: raw/normalized Parquet, data manifest/source-license/checksum, completeness and revision policy, capability/integration tests.
