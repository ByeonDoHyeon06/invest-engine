# E5.5 — Point-in-Time FX Research Reporting

**Scope:** Off-line historical research only; **not** a broker currency conversion, buying power, or production FX/fee model. Live trading **NOT AUTHORIZED**. E5 real-data validation gates remain open.

## Motivation

A multicurrency (KRW + USD) account cannot report one meaningful total equity, net P&L or drawdown by simply summing cash/positions in different currencies. A single present-day FX rate retroactively applied to every historic bar is look-ahead. E5.5 introduces an **opt-in**, point-in-time currency conversion for research **reporting only**. It does not modify E3 risk, order sizes, fills, settlement, or currency-separated books.

## Inputs (Python SDK)

- `FxObservation`: `observation_id`, `base`, `quote` (e.g. USD/KRW is KRW **per one USD**), finite positive `Decimal rate`, UTC `event_time`, `available_at`, `received_at`, nonblank `source`.
- `FxSeries`: immutable ordered observations with unique IDs, SHA-256 digest of the full content. Observations are chronological by received time/ID; ambiguous out-of-order or duplicate input is rejected.
- `FxReportingPolicy`: explicit `base_currency` (e.g. KRW) and maximum allowed quote age. Rate must be **available and received** by the valuation instant and its **market event time** must also be within maximum age.
- `HistoricalBacktest(..., fx_series=..., fx_policy=...)`: both parameters required together. Without them the preexisting per-currency metrics and behavior are unchanged.

**No implicit FX:** USD→KRW requires a direct USD/KRW observation; only KRW/USD provided is insufficient. There is no interpolation, triangular conversion or rounding to a fictitious broker fill. Missing, untrusted or stale marks yield `FX_MISSING_OR_STALE:<currency>` and `FxEquityPoint.value=null`.

## CLI extension (opt-in)

Existing `e5-research-v1` JSON remains backwards compatible. Add a top-level:

```json
"fx_reporting": {
  "base_currency": "KRW",
  "max_age_seconds": 300,
  "observations_jsonl": "fx.jsonl",
  "sha256": "<real SHA-256 of file bytes>",
  "source": "declared-data-origin",
  "license": "declared-license-reference"
}
```

`fx.jsonl` contains one **JSON object per line** with exact keys:

```json
{"observation_id":"fx-1","base":"USD","quote":"KRW","rate":"1300","event_time":"2026-11-17T00:00:00+00:00","available_at":"2026-11-17T00:00:00+00:00","received_at":"2026-11-17T00:00:00+00:00","source":"synthetic-example"}
```

Rates and money use strings, not JSON floats. Data files must match the declared SHA-256; provenance fields do **not** independently certify license or PIT correctness.

## Outputs

- `report.fx_base_currency`, `fx_data_sha256`, `fx_equity[]`, `fx_net_pnl`, `fx_max_drawdown`.
- `fx_equity.jsonl` with point time, value or `null`, completeness, source observation IDs and reason codes.
- Manifest: `fx_dataset_file_sha256`, `fx_event_sha256`, `fx_reporting_currency`, `fx_source`, `fx_license`, `fx_data_release_verified=false` and an additional SHA-256 for `fx_equity.jsonl`. The artifact verifier checks the additional file when enabled.
- Opening cash is valued at the **first event's observable timestamp**. Its base equivalent is subtracted from final converted equity for base `fx_net_pnl`. This is an FX-sensitive research metric, not a cash-flow-adjusted return series.
- Incomplete **any** timestamp on a research FX curve means `fx_net_pnl=null` and `fx_max_drawdown=null`, rather than computing an optimistic partial history. Per-currency report remains available.

## Tests and limitations

Synthetic tests cover same-data deterministic hashes, delayed FX release (no future leak), stale `event_time`, inverse-pair refusal, duplicate ID rejection, incomplete valuation, bad file checksums and tampered output files; full E0–E5 regression/CI expected.

**Still unverified/not implemented:** independent historical FX market data provenance, bid/ask rates and FX execution costs, provider-specific/market-specific taxes or fees, corporate-action adjusted prices (dividends/splits), as-of constituent universe incl. delisted equities, a quote/tick assisted historical execution model, survivorship bias assessment. These are **not** implied by synthetic FX testing. Real research promotion / E6 gating requires explicit resolution or enforced data eligibility restrictions and separate validation evidence.
