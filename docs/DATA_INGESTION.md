# E1.1 — Provider contracts, normalization, quality and as-of visibility

**Status:** Implemented and merged in [PR #12](https://github.com/ByeonDoHyeon06/invest-engine/pull/12); Python 3.12/3.13 CI [passed](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43712325371).

## Scope

E1 is intentionally broken into smaller independently testable PRs:
1. **E1.1 (this PR):** historical DataProvider Protocol; explicit provider capabilities; strict raw→typed event normalization; stateful feed quality and quarantining; as-of visibility.
2. **E1.2:** exchange/session-anchored aggregation for tick→bar and lower→higher resolution, early closing, DST/calendar boundaries.
3. **E1.3:** raw/normalized dataset storage, manifest/license/checksum, gap and revision policy, provider integration tests.

## Interfaces

- `RawMarketRecord` is an adapter boundary with immutable payload and explicit `event_time`, `available_at`, `received_at`, source identity, ordinal and optional provider sequence.
- `normalize_record(record)` supports `trade`, `quote`, `book`, `bar` and `status`. It rejects floats, nonfinite values, naive timestamps, unexpected fields, invalid OHLCV and mismatched time bar durations. **It does not guess missing prices.**
- `DataCapability` and `DataRequest` support a market/event kind and optional native bar resolution; `require_capability` fails instead of silently inventing detail. **This first PR does not implement resampling.**
- `QualityGate.inspect(event)` yields `QualityDecision(ACCEPT|QUARANTINE)`. Repeated IDs, lateness outside policy, late receipt, sequence gaps, rewind and unfinished bars are quarantined.
- A sequence gap marks that source/instrument/event-kind stream unsynced. A caller may use `reset_stream` **only after external resynchronization**; this API does not perform reconciliation.
- `ObservationBuffer` accepts only approved observations, and `visible_at(t)` returns events with **both** `available_at <= t` and `received_at <= t`. It is only an early-stage in-memory read fence, not the E2 durable journal.

## Decision rules

- Internal instants are UTC-aware; market time zones belong to E1.2 calendar adapters.
- Strict Decimal creation from strings/integer/Decimal only, never binary floats.
- Data quality flags never imply price reconstruction; quarantined observations must not reach strategies.
- Even accepted data is an observation, not a trade or order authorization.
- Market-data sequence IDs are only comparable within the same source/instrument/kind; a detected gap is not automatically healed by receiving the next number.
- The system does **not** persist confidential broker market data or perform live trading.

## Tests and known limitations

Synthetic tests cover normalization across all five payload types, unsupported resolutions, timezone, strict fields and floats, duplicate/late/stale/sequence gap/partial-bar quarantine, and point-in-time admission. The original E0 replay tests remain intact.

Known gaps for E1.2/E1.3:
- No session calendar or resampler yet.
- No Parquet persistence, data manifest, corporate action revisions or full provider history coverage checks.
- Quarantine/unsynced state is in memory; restart-safe recovery and durable journal are E2.
- `ObservationBuffer` as-of query is linear scan; will be replaced as data volume grows.
- Original provider adapters must record real publication/arrival times accurately; normalization cannot infer historical latency.

## How to test

    python -m pip install -e ".[dev]"
    ruff check .
    mypy src
    python -m pytest -q

No token, API key, or external credentials are required.
