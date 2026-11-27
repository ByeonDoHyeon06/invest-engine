# Authorized Alpaca US acquisition audit

Operator reports repository Secrets ALPACA_DATA_KEY and ALPACA_DATA_SECRET configured on 2026-11-19. Keep credentials in the secret store. Workflow uses market-data GET requests to data.alpaca.markets only; no order/account endpoint. The credential itself may have paper-order permissions, but this workflow does not exercise them. No live authority.

The workflow is restricted to same-repository PR from the named collection branch or explicit main dispatch. It uses the frozen KRUS-80 US 40-symbol universe for calendar years 2020 (warmup), 2021–23 (research) and 2024–25 (validation); 2026 reserved metadata only. Preflight checks AAPL 2024-01-03 daily and minute historical raw SIP access. If authentication or SIP access fails, neither full collector runs. No fallback to IEX. Daily 240 symbol-year partitions followed by six sequential minute-year shards, each 480 symbol-month partitions, with conservative request spacing below the published Basic historical limit of 200 requests/minute. No paid plan purchase, no actual account or trade request. Runner consumption may count against GitHub Actions quotas.

The collectors temporarily write normalized quotes on the runner filesystem; only aggregate audit JSON (counts, dates of missing observations, SHA-256 fingerprints and statuses) is retained as short-lived artifacts. No raw bars uploaded to GitHub, no raw quotes in logs, no shared data cache. Therefore completion is acquisition/coverage evidence, NOT a persistent licensed market-data archive. For durable private data, run locally with authorized credentials/rights, or obtain explicit storage/usage permission and configure suitable private storage; for cloud simulations, consume the data inside the same job before deletion. The official historical bars reference: https://docs.alpaca.markets/us/reference/stockbars . Free Basic historical restrictions: https://docs.alpaca.markets/us/docs/about-market-data-api .

The output reports source errors separately from structural gaps; does not invent missing observations. Known historical symbol changes/delistings, issuer-action verification, PIT publication history, actual brokerage fees and liquidity remain unresolved. All execution_eligible flags remain false. No profitability claim, no E5 issue #6 closure, E6/G2 NOT ACCEPTED.

Local authorized collection:
```sh
python -m pip install exchange-calendars==4.13.1
python scripts/alpaca_data_preflight.py
python scripts/prepare_market_panel.py alpaca-daily --acknowledge-data-rights
python scripts/prepare_market_panel.py alpaca-minute --acknowledge-data-rights --year 2021
```
Set the two environment variables through a private secret manager before running; never use a command containing secret values in shell history. Repeat minute years 2020 through 2025 or omit --year for all six. Provider usage rights remain the operator's responsibility.

## Verified result
#55 merged `d24b192`; run 44519434207 all 8 jobs successful. 58,593/60,320 daily rows, 230/240 complete, 91 zero-volume rows. 22,393,263/23,438,400 minute rows, 1,416/2,880 complete. Zero source/duplicate/invalid errors; no persistent raw archive or E5 acceptance.
