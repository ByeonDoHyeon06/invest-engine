# E5.7 — Importing real historical prices for a non-trading smoke test

**Scope:** historical **backtest** (offline replay), **not** continuous **forward-paper trading**. This is only a CSV connector; no provider credentials or live broker commands.

## Data source and meaning

- Supply a **locally downloaded, use-permitted** CSV with exactly `datetime,open,high,low,close,volume` and timezone-aware **UTC** bar-open timestamps, oldest first. Prices and volumes are converted via Decimal. Every emitted bar is finalized at the specified interval and appears to the engine **1 second after its end**: this is a conservative *research assumption*, **not a verified historical dissemination timestamp**.
- The converter rejects unknown/negative monetary inputs, missing columns, naive timestamps, nonascending/overlapping bars and invalid OHLC values. It outputs canonical E0/E1 `EventEnvelope[Bar]` JSONL and SHA-256 metadata; input CSV is never changed.
- `--volume-unit SHARES` means **you attest that the provider's volume is actual traded share count**. The importer cannot verify this assertion independently. `--volume-unit TICK_COUNT` means the count of price updates/quotes, **not share turnover**. If the backtest config declares `dataset.volume_unit: "TICK_COUNT"`, the experiment CLI allows **only `no-trade`** for testing the data path. ORB and fills would be invalid.
- Input source, price adjustment policy, corporate actions, venue calendar, licensing and historical publication/vintage still require independent checking. Converted data **does not automatically pass the E5.6 PIT provider gate**.

## Import example

```bash
invest-engine import-csv \
  --input ./local/AAPL_1m.csv \
  --output ./local/aapl_events.jsonl \
  --market US --venue XNAS --identifier US0378331005 \
  --symbol AAPL --currency USD --interval-seconds 60 \
  --volume-unit TICK_COUNT \
  --source "local-evaluation-sample"
```

This writes `aapl_events.jsonl` and `aapl_events.import.json`, with the original CSV hash, canonical JSONL hash, row count and `execution_eligible_by_volume_unit=false` for tick counts. The `source` label is user-declared, not an authenticity certificate.

Set `dataset.events_jsonl` in the existing [E5_EXPERIMENT.md](../../docs/milestones/e5/E5_EXPERIMENT.md) backtest request to the new JSONL and pin its SHA-256. For tick count data use the **NoTradeStrategy** and set `dataset.volume_unit` to `"TICK_COUNT"` in the JSON config. Explicit historical trading sessions (UTC, market-appropriate) are still required. Use:

```bash
invest-engine backtest --config ./local/no_trade_aapl.json
```

A genuine **ORB trade-performance test** needs at least the prior 20 complete trading sessions of 1m **share volume**, usable opening-range bars, a validated market calendar, authorized dataset access, a corporate-action policy and explicit fee/slippage assumptions. Daily historical OHLCV cannot test 1m ORB.

## Direct offline smoke test performed (2026-11-17)

Five rows of the publicly displayed AAPL 1m GitHub README preview (March 26, 2026, 13:30–13:34 UTC) were transcribed **only in the local test workspace**, not checked into the GitHub repo. The sample vendor defines `volume` as **broker tick volume**. Conversion to five canonical events and a `NoTradeStrategy` replay succeeded:

- Event count: **5**
- Simulated fills: **0**
- Start/end portfolio: **USD 10,000 / USD 10,000**, P&L **USD 0** (expected for NoTrade)
- Output event JSONL checksum: `36d038e2f391b4203e66108cd6b735ef7c957dac43b755f89008156be5d6a445`
- Reproducibility report run SHA: `ba5c883983f6e6fe5c13390426d0e6805d87c857530dd1eb8cd414aa9337764c`

This **proves only the input parser→event replay→report pipeline**, not ORB profitability, actual exchange volume, historical data completeness, or model execution fidelity.

Reference: https://github.com/getdata-finance/aapl-1m-ohlcv-stocks-historical-data (personal evaluation sample; check the provider's data license before any use or redistribution). No raw market sample CSV is committed.

## Next stage: Forward paper

Real-time forward paper requires licensed quote/aggregate streaming, independent market calendar and symbol master, a persistent running strategy coordinator, simulated order state/reconciliation, monitoring and safety controls. This belongs to E7. It needs **no real broker order**, and historical E5 work can be reused after live feed integration.
