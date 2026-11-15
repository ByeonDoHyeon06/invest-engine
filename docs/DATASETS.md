# E1.3 — Immutable Market Dataset Packages

**Status:** PR #14 verified and merged; [CI run 43714655109](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43714655109) passes Python 3.12/3.13 tests. Not live-broker functionality.

## Goals
E1 normalized market observations must be replayable and auditable. Every dataset package records provenance and preserves original/normalized information as two independent Parquet artifacts.

## Dataset layout

    <dataset-root>/
      synthetic_kr_2026_11_v1/
        manifest.json
        manifest.sha256
        raw.parquet
        normalized.parquet

Dataset root must be stored outside the Git repository for proprietary or account-specific market data. The repository's gitignore already excludes data/, datasets/, and artifacts/.

## Contract

`DatasetSpec`:
- immutable, path-safe dataset_id
- provider and license_id (human-reviewed; not an authorization check)
- market, event kind, coverage_start/end, calendar_version
- adjustment mode: RAW, SPLIT_ADJUSTED, TOTAL_RETURN, UNKNOWN
- completeness: UNVERIFIED (default), GAPS_PRESENT, PROVIDER_ATTESTED
- revision and previous_dataset_id for lineage

The code does not silently claim completeness. `PROVIDER_ATTESTED` is an external source claim and is **not** independently verified by this program.

`write_dataset(...)`:
- refuses duplicate IDs, wrong provider/market/range or unmatched normalized records
- normalized records must preserve raw ID/instrument/times/order and must not carry quarantined quality flags
- writes raw and normalized records to separate Parquet files, records SHA256 checksums
- writes an integrity-checked manifest and refuses overwriting an existing dataset ID
- uses staging directory and atomic final directory rename on a local filesystem
- preserves full event payload as canonical JSON inside Parquet (initial interoperability format)

`read_dataset(...)`:
- validates path-safe dataset identifier
- verifies manifest SHA256 and both Parquet checksums before reading
- verifies row counts and row/event identity
- reconstructs typed domain events with Decimal, UTC timestamps, bar nominal intervals, source sequence, and quality flags

**Limitations:** the manifest checksum detects accidental changes, not hostile tampering by someone able to replace files and recompute all checksums. No signatures or key management. Parquet event JSON is a lossless first format, not yet optimized for analytics/columnar filtering; future schema revisions must be explicitly versioned.

## Install and test

    python -m pip install -e ".[dev,data]"
    ruff check .
    mypy src
    python -m pytest -q

The `data` optional dependency supplies PyArrow. Core E0–E1.2 runs without it. Synthetic market data is used in tests.

## Revision policy
A correction is stored in a **new dataset ID** with revision incremented and previous_dataset_id pointing to the prior artifact. An existing dataset never gets silently replaced. Later research must record which dataset revision and manifest/hash was used. Dataset provenance and adjustment policy are mandatory, but **accurate external market coverage still requires a source-specific validator**.

## E1 release gate
- E1.1: Strict normalization, capability negotiation, quality quarantine, PIT buffer
- E1.2: Tick/Bar session aggregation, DST, gap policy, impossible-resolution refusal
- E1.3: Raw/normalized Parquet + immutable provenance manifest + SHA-256 and roundtrip tests
- Python 3.12/3.13 Ruff, mypy, pytest, basic secret guard CI all pass
- Real exchange calendar feeds, online aggregation/watermark persistence, durable order state are future stages and **not** part of E1 completion.

E1 completion means **data foundations**, not a backtesting or trading engine. The next roadmap stage E2 implements the deterministic event runtime.
