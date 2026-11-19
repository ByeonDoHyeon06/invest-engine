# E5.13 — Preregistered provisional market study

**Scope:** Historical-data diagnostic, NOT a provider release approval or trading recommendation. No live connectivity, credentials, paid data, or raw-data redistribution.

## Design fixed before execution

- Daily panel: AAPL, MSFT, NVDA, TSLA, GOOG, META; all calendar months of 2025, fresh $100,000 cash per run, 5% maximum target, seven named rules, three cost assumptions, 1,512 planned independent trials. No training/optimization or warm-up outside each month. Nominal daily interval and source-reported dates. Unknown corporate action and adjustment/vintage provenance; returns are diagnostic only, not total returns. No forced close of open positions. Public Pubmarks source pinned to e31dd3817bb2eccaa10d3b01c6f2efdbca5d3abf.
- Minute panel: HistoricalData.net public 2022H2 stock sample (https://historicaldata.net/stocks.html). TSLA, SPY, KO, TWTR × September, October, November 2022 with exactly 20 preceding exchange sessions. Strict complete-minute preflight and daily issuer action check; no missing prices or dates invented. Reject incomplete/action windows. All eligible windows run NoTrade, entry-hold and ORB, plus stressed ORB. Use raw price/share volume, regular session ET, receipt at bar end explicitly assumed. No invented actual PIT evidence; bypass strict CLI only for clearly labeled provisional programmatic study. No raw files in artifacts, logs or repo.
- Cost scenarios: low 0.05% fee/5 bp penetration buffer, base 0.10%/10 bp, stress 0.25%/40 bp; 5% volume participation, tick $0.01, lot one share, tax zero placeholder. Actual costs and exchange ticks not independently verified; sub-cent marks may reject proposed orders. ORB is a long-entry signal hypothesis and not a session-flat round-trip strategy. Full-period return uses marked open holdings and costs; fill count not completed trade count.
- Every failure/blocked window is reported. No success inferred from CI exit status; inspect per-study status/results. External vintage, coverage, legal/license requirements and costs need independent verification. E5 Issue #6 remains open. No E6 promotion based on this study alone.

## First-run finding and correction

The first diagnostic completed 1,445/1,512 daily trials; 67 failed with `intent and allocation plan mismatch`. Root cause: a positive long target may generate a SELL trim after price appreciation, but the attribution ticket previously allowed SELL only for a zero target. E5.13 accepts the valid reduction and attributes it to existing virtual holdings; tests cover account/virtual parity. The same fixed study is rerun without tuning strategy parameters. Correct SPY venue/class metadata (NYSE Arca ETF). The first-run partial strategy rankings are not used as final evidence.
