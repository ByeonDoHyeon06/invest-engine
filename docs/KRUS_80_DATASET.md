# KRUS-80 market panel v1 — data acquisition plan

**Status:** #54 merged `8f5a42b`; public probe 96/96 partitions and 24,128 rows, Core CI 393 tests each. #55 authenticated US audit completed; full licensed KR/US panel NOT acquired, raw runner files not retained. E5 #6 remains OPEN. No strategy certification/order authorization. Registered 2026-11-19.

## Scope
- 40 US-listed securities, 30 KOSPI and 10 KOSDAQ; exact complete manifest [market_panel_v1.json](../research/market_panel_v1.json). Convenience cohort chosen retrospectively, **not** point-in-time index membership; includes historical removals TWTR, ATVI and 091990. No replacement of failed/delisted symbols; identity/listing intervals must be independently reconciled (incl. market transfers and ticker changes). Benchmarks SPY, QQQ, KOSPI and KOSDAQ are metadata only, not collected by v1.
- 2020 warmup; 2021–2023 development training, 2024–2025 validation, 2026 Jan–Oct reserved metadata only (not fetched by utility). Previous 2025 experiments already examined several tickers; this validation is not blind. No holdout-access certificate.
- Using exchange-calendars 4.13.1 XNYS/XKRX as provisional calendar: 2021–25 expected max 99,200 symbol-days (US 50,200; KR 49,000); including 2020 119,240. Counts assume every instrument listed and trading in all sessions; absent observations remain blocked, not invented. Regular one-minute target order of 38–39 million bars across both markets excluding warmup; actual session lengths and listing gaps reduce coverage. US minute collector ready for authorized data; KR minute ingest/provider not yet implemented.

## Authorized sources
| Source | Data | Prerequisite |
|---|---|---|
| [Alpaca historical bars](https://docs.alpaca.markets/us/reference/stockbars) | Explicit SIP raw daily / minute, not IEX substitution | Operator-owned market-data access and permission. [FAQ](https://docs.alpaca.markets/us/docs/market-data-faq) states historical SIP older than 15m may be accessed without subscription; [API](https://docs.alpaca.markets/us/docs/about-market-data-api) requires authentication. Actual account entitlements and coverage not checked. Symbol mapping disabled (asof=-); missing renamed/delisted segments need identity review. |
| [KRX OPEN API](https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd) | KOSPI/KOSDAQ raw daily, 2010 onward | [Service approval](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp), key; [terms](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO002.jsp) noncommercial only, 10,000 calls/day/key. Confirm private research use and rights; not for commercial service. |
| [Pubmarks pinned snapshot](https://github.com/Pubmarks/datasets/tree/e31dd3817bb2eccaa10d3b01c6f2efdbca5d3abf) | 16 US symbols × 2020–2025 individual yearly OHLCV CSVs | Public read-only aggregate coverage probe; no raw upload or claim of data redistribution permission, price basis or PIT verification. |

Independent corporate actions/splits/dividends/delistings, instrument master and listing intervals, exchange calendars, source receipt/adjustment provenance, historical exchange and retail fees, and FX source remain required. No normalized dataset is regarded as E5 execution-eligible merely because all rows exist. Daily bars cannot substitute for ORB minute execution. Even raw SIP minute bars do not reproduce historical order/quote liquidity or receipt timing. KRX 1-minute coverage requires a separate authorized vendor or broker historical data product, not the daily endpoint.

## Local collection
```shell
python -m pip install exchange-calendars==4.13.1
python scripts/prepare_market_panel.py public-probe
# In private local environment, set operator-owned ALPACA_DATA_KEY /
# ALPACA_DATA_SECRET and KRX_DATA_KEY without exposing them in chat or git.
# Confirm data rights and applicable terms before running:
python scripts/prepare_market_panel.py alpaca-daily --acknowledge-data-rights
python scripts/prepare_market_panel.py krx-daily --acknowledge-data-rights
python scripts/prepare_market_panel.py alpaca-minute --acknowledge-data-rights
```
Only public-probe runs in CI; never upload authorized vendor OHLCV as CI artifact. Private output under ignored datasets/krus-80-2021-2025-v1-v1/daily/{US,KR}/symbol/year.csv and minute/US/symbol/year-month.csv. Per-provider audit JSON includes response hashes and normalized file SHA256, session counts, duplicates, invalid OHLC/volume, extra/missing and unavailable rows; source payloads are not archived. No overwrite of changed normalized files: use a new explicit version and compare source revisions. Only aggregate results printed. No passwords/API keys in repo, logs, URLs or output. Public probe is intentionally diagnostic-only, aggregate artifact contains counts/date gaps/hashes, not raw prices.

Tests validate fixed universe, reserved date range, malformed or duplicate/zero-volume rows, absent observations, and version collision. Provider adapters not tested against authenticated endpoints without authorization. A failed source/coverage is not a zero-return observation. Separate data acceptance and E5 report ingestion required after acquisition. Public probe and PR #53 strategy sensitivity do not certify profitability.
