# E5.9 — Point-in-time declared dividend replay (offline research only)

**Scope:** E5.8 split replay remains unchanged. E5.9 adds an *optional*, SHA-256-pinned, synthetic cash-dividend entitlement/payment schedule to the existing `HistoricalBacktest`. No real broker, issuer connection, tax authority lookup or live trading is added. **E5 Issue #6 remains open.**

## Motivation and causal model

- A cash dividend has at least two independent dates: **entitlement boundary** and **actual pay date**. The entitlement is determined from shares held *before* the first finalized bar of the declared ex-date session, using E3 `DividendEntitled`. A share bought during that bar is **not** entitled.
- An entitlement creates a **net cash receivable**, not settled/available cash. Backtest research equity adds the receivable to avoid mistaking an ex-dividend price drop for a realized loss. It does not count as brokerage buying power or as cash in the E3 risk gate. Withholding is a **synthetic caller-declared fraction**, not a real legal rate.
- At a separately declared witnessed payment boundary, E3 `DividendPaymentConfirmed` moves the receivable to settled cash exactly once. If the user held no shares at entitlement, payment is skipped rather than creating cash.
- If the payment is beyond the dataset horizon, the net receivable remains in equity and **not** in spendable cash. Missing in-horizon payment bars are rejected instead of guessed.
- Events are applied when the corresponding **bar is observed**, never backdated to its open. The action terms must have `available_at <= effective_at` and payment evidence must be available by its pay boundary. Only **session-open** entitlements are supported. Underlying prices must be explicitly declared `RAW_UNADJUSTED`; already adjusted bars could double-count income.

## Opt-in research CLI

Add the following alongside the E5.6 `pit_evidence` section of `e5-research-v1`:

```json
"dividend_replay": {
  "records_jsonl": "dividends.jsonl",
  "sha256": "<lowercase SHA-256 of exact file bytes>",
  "source": "caller-declared-issuer-records",
  "license": "caller-responsible",
  "price_basis": "RAW_UNADJUSTED"
}
```

Two exact JSONL rows for a synthetic action, sorted by event time:

```json
{"kind":"entitlement","action_id":"div:1","instrument_key":"KR:KRX:SYN","gross_per_share":"2.00","withholding_fraction":"0.10","effective_at":"2026-11-17T01:00:00Z","available_at":"2026-11-16T01:00:00Z","source":"synthetic-issuer"}
{"kind":"payment","action_id":"div:1","instrument_key":"KR:KRX:SYN","paid_at":"2026-11-19T01:00:00Z","available_at":"2026-11-17T01:00:00Z","source":"synthetic-issuer"}
```

In PIT evidence, add a `corporate_action` with `action_type="CASH_DIVIDEND"`, matching the `action_id`, `instrument_key`, entitlement `effective_at`, `received_at` equal to entitlement `available_at`, and `source`. Keep `vintage`, `membership`, and `action_coverage` records. Both JSONL files are hashed *independently*; CLI validates both before running.

`manifest.json` records `dividend_replay_file_sha256`, `dividend_replay_count`, and `dividend_replay_data_verified=false`. `report.json` and per-bar decision records retain action reasons: `DIVIDEND_ENTITLED`, `DIVIDEND_PAID`, `DIVIDEND_NO_HOLDINGS`. The E5 run/config digests bind the complete action schedule. Existing no-dividend experiments remain compatible.

## Fail-closed cases / limitations

- Delisting, mergers, symbol changes and **unmodeled** dividends remain blocked by the PIT gate. Delisted positions are **not** silently valued at zero, marked sold or removed from the historical universe.
- This model does not independently validate issuer record dates, ex-date calendars, pay-date historical revisions, dividend currency conversion, withholding jurisdictions or actual provider provenance. Real dividend withholding may have other rules.
- Applying splits and dividends on the **same session-open boundary** is rejected until the exact action ordering is specified. Protective-lot and split restrictions from E5.8 remain.
- If any open order for a dividend instrument conflicts with an entitlement, E3 deliberately halts instead of inventing its historic fill ordering.
- A receivable is an **economic research estimate**; true broker cash accounting, settlement, rights transfers and corporate-action adjustments require separate audited inputs. Price history must not already be total-return-adjusted.
- Tick/quote-based execution and one-month **actual share-volume** ORB testing are still pending. Historic daily bars are not sufficient for an intraday ORB strategy; 20 prior fully observed sessions must be provided.

## Verification

`tests/test_dividend_replay_e5.py`: ex-date price step/receivable conservation; later payment, postponed payment, zero holdings, missing witness/future-known terms, schedule collisions, PIT action mismatch/delisting rejection, strict schema/file SHA, compatible CLI/manifest and deterministic rerun. Run full tests and Python 3.12/3.13 CI with Ruff/mypy/secrets before merge.
