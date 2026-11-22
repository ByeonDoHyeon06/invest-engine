# E5.14b — Dated regulatory cost sensitivity; E5.15a extension

**Status:** candidate; CI and new study results pending. Issue #6 OPEN; E6 acceptance/LIVE blocked.

## E5.14a verified

[PR #40](https://github.com/ByeonDoHyeon06/invest-engine/pull/40) merged as [1d63a3c](https://github.com/ByeonDoHyeon06/invest-engine/commit/1d63a3cb57d6635288a623ced8a6de4b18a80ad2).
[Core CI](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44497904693) Python 3.12/3.13 each 311 passed, lint/type/secret checks. [Diagnostic](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44497904890): 3 eligible windows, 21 arms, nine blocked windows, retry hold filled in six arms, all six protected ORB arms ended flat. Base session-flat 19 BUY and 19 SELL fills (17 stops, two session closes); stress 18 BUY and SELL (16 stops, two closes). No profitability claim. [Regression](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44497904804) retained daily 1,512 experiments / 3,732 fills; all 21 aggregate group summaries and six data hashes identical to E5.13, all 12 matched minute runs' common non-duration/non-run-hash fields identical (daily row-level parity was not verified).

| Evaluation window | Hold v2 base % | ORB base % | Protected ORB base % | Protected ORB stress % |
|---|---:|---:|---:|---:|
| TSLA Oct 2022 | -0.45080 | +0.25317 | -0.27447 | -0.50400 |
| TSLA Nov 2022 | -0.68410 | -0.48903 | -0.05261 | -0.22912 |
| SPY Nov 2022 | +0.20544 | +0.28974 | -0.12959 | -0.24802 |

Independent account sums -USD 456.67 base and -USD 981.14 stress, not a compounded account. Mean base MDD approximately 0.2263% vs 0.7588% entry-only ORB. The observed 2022 panel is not a new holdout.

## E5.14b.1 scope: fixed-fill audit, not ledger cost replacement

`audit_us_fixed_fills(report, events, FeeAssumption(...))` accepts the same single-instrument US equity/ETF USD event stream that produced an existing BacktestReport (verify dataset hash, event IDs, dates, quantities, charges). No FX, unsupported assets, undated fills, duplicate executions, ambiguous cross-date orders or unknown date windows. Use Decimal. The formula is realized modeled gross quantities, NOT broker order executions.

| Regulatory base | Effective covered date range (inclusive start, exclusive end) | Rate |
|---|---|---|
| SEC Section 31 | 2022-05-14–2023-02-27 | USD 22.90 per USD million covered sales |
| FINRA covered equity TAF | 2022-01-01–2023-01-01 | USD 0.000130/share, cap USD 6.49/trade |

The schedule implements only the **intersection**, 2022-05-14 through 2022-12-31. Outside this interval reject, not extrapolate. [SEC 2022 fee advisory](https://www.sec.gov/newsroom/press-releases/2022-60), [2023 advisory](https://www.sec.gov/newsroom/press-releases/2023-15), [FINRA Federal Register filing](https://www.govinfo.gov/content/pkg/FR-2020-10-20/pdf/2020-23141.pdf). These are SRO/member assessment rates, not the actual retail invoice. SEC charge date may differ from trade date; assume ET trade date only for this sensitivity. TAF cap per simulated execution is a trade proxy, not verified broker aggregation.

Assumptions are explicit and version-hashed: commission per executed order half-up cent with optional once-per-order minimum, SEC ceil cent per sell order, TAF capped then ceil cent per modeled sell execution. The assumptions are not certified retail rounding rules. No waiver assumed. No regulatory charges on buys. The source PnL is adjusted by adding its old fees/taxes and subtracting these repriced charges. Original fills, original ledger, cash reservations, MDD and PnL traces remain unchanged. Output prefix `fixed_fill_`; flags broker_verified, charge_date_verified, replayed_with_cost_policy all false. Output is an aggregate financial sensitivity, not a full fee-aware rerun or guaranteed trade cost. Source run + policy + ordered charge breakdown hashed. Full fee-aware pretrade reserve / execution / partial-fill / journal replay and broker-evidence verification remain E5.14b.2.

## E5.15a fixed window extension preregistration

No changes to ORB parameters, target, fill, risk, fee assumptions or warm-up. Repeat 12 old Sep–Nov 2022 symbol-months for matched controls; include every August and December 2022 symbol-month (TSLA, SPY, KO, TWTR) for eight additional windows, regardless of performance. This exhausts the remaining full evaluation months with 20 prior sessions in the same Jul–Dec sample. Calendar Dec 26 holiday verified from [ICE 2021–2023 schedule](https://ir.theice.com/press/news-details/2020/NYSE-Group-Announces-2021-2022-and-2023-Holiday-and-Early-Closings-Calendar/default.aspx); Nov 25 early close. Strict same E5.12 preflight, reject incomplete/action windows without fabricating prices. Seven predeclared arms per eligible window: NoTrade base, Hold retry base/stress, ORB entry base/stress, ORB flat base/stress; add fixed-fill audit to each. Maximum 140 arms, actual count depends on eligibility; zero result rows reported for blocked windows. Source hashes and rejected dates retained. No raw files in repository or public artifacts. Same supplier/time regime: extension is not broad independent market validation. No new market returns inspected before registering these months.

## External data path and next blockers

- [HF Data Library](https://hfdatalibrary.com/pages/data): provider declares CC BY 4.0 and IEX-only historical share volume, not consolidated volume; sparse minutes must be represented as missing (not synthetic zero bars). Review [IEX HIST terms](https://www.iexexchange.io/) directly before acquisition; raw vs clean adjustment/vintage and missing-minute semantics must be checked. Do not silently use IEX bars as SIP/consolidated. Candidate universe to preregister independently: broad/sector ETFs (SPY, QQQ, IWM, XLF, XLE), liquid large-cap (AAPL, MSFT, NVDA, JPM), a mid/small-cap and delisted cohort from dated instrument master, not current constituents. Fixed periods must be chosen before data/result inspection. Strict complete-minute model may reject sparse IEX data. No new source data acquisition yet.
- [HistoricalData.net sample](https://historicaldata.net/stocks.html) has only four names; further consolidated symbols require a separate permitted source/contract. No purchase or credentials requested.
- Broker actual historical coverage/waivers/rounding, SEC charge date, native currency/settlement, volume coverage and true point-in-time vintages remain unverified. Additional actual dates and KR market need their own contracts. No E6 promotion or live authorization.
