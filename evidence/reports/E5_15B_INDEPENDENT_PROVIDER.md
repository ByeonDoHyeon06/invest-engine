# E5.15b — Independent US market sample and coverage diagnostics

Status: candidate; tests/independent provider data retrieval pending. E5 issue #6 remains open. The engine does not have broker credentials or live trading authority.

## Prior verified release

PR [#41](https://github.com/ByeonDoHyeon06/invest-engine/pull/41) merged as 87b6cd4; [#42](https://github.com/ByeonDoHyeon06/invest-engine/pull/42) merged as d6239b7. [Core CI](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44501266992) 328 passed on Python 3.12 and 3.13, lint/type/secret checks passed. [Fee-aware replay](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44501267176) all 20 jobs succeeded, six eligible windows and 42 completed arms. Compared all 42 arms with [fixed-tape audit](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44499969770): source file/archive hashes, window sizes, PnL, total fees, SEC, TAF, buy/sell quantity, fill and stop/session-close counts and final inventory all match numerically. 14 invalid windows are not performance observations. All 12 hold arms acquired shares; all 12 protected arms ended flat.

| Window (2022) | Session-flat base USD PnL | Stress USD PnL | Base MDD % |
|---|---:|---:|---:|
| TSLA October | -275.47 | -504.99 | 0.322448 |
| TSLA November | -53.37 | -229.88 | 0.201670 |
| SPY November | -130.22 | -248.52 | 0.156389 |
| SPY August | -183.25 | -447.38 | 0.183250 |
| KO August | -159.26 | -327.77 | 0.159260 |
| TSLA December | -145.91 | -204.26 | 0.145910 |

Independent-account loss sums -947.48 base / -1962.80 stress, not a compounded portfolio. All six base and six stress arms negative. MDD now from fee-aware equity traces, not repriced fixed tape. Actual retail charges, trade/charge-date correspondence, independent historical data vintage and execution liquidity remain uncertified.

## Source selection / terms checked 2026-11-19

| Source | Scope | Access / price basis | Decision |
|---|---|---|---|
| Kibot | Vendor states consolidated stock/ETF trade prices/volume across exchanges, ECNs, reported off-exchange | Public rolling sample IBM, OIH, unadjusted files | Run independent diagnostic subject to complete coverage |
| HF Data Library | IEX single venue | Account/email/profile/API key required; even Raw is stock-split adjusted | No acquisition or trading-strategy certification here; academic quality data only |
| FirstRate Data | Vendor multi-venue aggregation | Public two-week sample per symbol | Cannot meet 20 prior sessions plus fixed month with these samples |
| FinzData | Intraday stock data | Public preview ten bars, full files account required | Not a complete evaluation sample |

Kibot [sample page](https://www.kibot.com/free-historical-intraday-data.html), [license](https://www.kibot.com/license.html), [format](https://www.kibot.com/file-format/data-format-reference.html), [FAQ](https://www.kibot.com/faq.html), [comparison](https://www.kibot.com/quality/data-comparison.html). License provides internal research use, allows cloud AI acting solely for the licensee and aggregate results sharing, forbids raw redistribution. Only aggregate results, hashes and counts are published. No account requested or purchase. Vendor data provenance/coverage, odd-lot inclusion and actual vintages are still unverified. Never label brokerage execution proven from these minute bars.

HF Data [API](https://hfdatalibrary.com/pages/api), [dataset card](https://huggingface.co/datasets/elkassabgi/hfdatalibrary/blob/main/README.md), [provider terms](https://hfdatalibrary.com/pages/terms), [IEX historical terms](https://www.iex.io/legal/hist-data-terms). Do not reinterpret IEX volume as consolidated market liquidity or split-adjusted prices as as-traded. The provider describes academic/educational purposes, and IEX data is reference only, not the basis for trading decisions. No bypass of account or download requirements. FirstRate [samples](https://firstratedata.com/stock-data), FinzData [samples](https://finzdata.com/samples).

## Preregistration

Instruments: the **entire public Kibot unadjusted minute sample universe** (IBM, OIH), no screening by observed returns. 2026 September and October, the two complete months before Nov 19; no moving the fixed dates to find successful cases. Four instrument-month windows, up to 28 arms. All 20 prior sessions and full evaluation calendar required; Labor Day closed Sep 7 per [NYSE calendar](https://www.nyse.com/trade/hours-calendars). Known IBM Aug 10 quarterly dividend entitlement date from [2026 second-quarter issuer release](https://newsroom.ibm.com/2026-07-22-IBM-RELEASES-SECOND-QUARTER-RESULTS); IBM 2026-11-10 record date outside the windows; [OIH distribution history](https://www.vaneck.com/us/en/investments/oil-services-etf-oih/performance/) and [annual schedule](https://www.vaneck.com/us/en/vaneck-etfs-distributions-schedule-2026.pdf) show annual distribution, not October quarterly. These are conservative known event checks, not proof of corporate-action completeness; splits/spin-offs/security identity require complete independent verification. Record all blocked windows. Rolling samples downloaded once per symbol, hash exact received bytes, report missing by session and observed/expected counts. Re-run may fail once old dates roll out.

Headerless CSV Date, Time, OHLC, share volume; timestamp is start of bar in ET (DST converted). Preserve exact decimal observations including subcent prints. Whole-share positive volume, OHLC validation, monotonically increasing unique timestamps, no blank fabricated bars. Out-of-schedule minutes in the declared date span count as extra. No synthetic price or forward-fill. Only create EventEnvelope tuples for complete windows and validate again with E5.12 contract. Incomplete windows report BLOCKED, source malformed/download unavailable reports SOURCE_ERROR, actual strategy failures report PARTIAL and a failing CI job. Do not publish exception text containing rows. Source timestamp receipt at bar end is an explicit retrospective assumption, not historical receipt evidence.

Use exactly existing seven E5.14 arms (cash/hold retry/ORB entry/ORB flat, same base/stress scenarios), USD100k cash and 5% target. 2026 fee schedule not verified: use synthetic percentages (not 2022 dated regulatory rules). 0.01 order-grid scenario only, not certified current tick regime. Retain real subcent marks; do not round source data; report signals without intents, counts/reason codes, and subcent close observations to expose no-order bias. No-fill buy-and-hold is not a valid performance comparator. Do not pool sample metrics with 2022 market results as independent holdouts.

## Next

Expand to predeclared broad/index/sector ETFs (SPY, QQQ, IWM, XLF, XLE), large caps (AAPL/MSFT/NVDA/JPM) plus verified mid/small-cap and delisted cohorts, with licensed dated instrument master and complete raw minute/quote provenance. Sample cohorts are not survivorship-free. If incomplete real minutes are pervasive, design explicit gap/known-unavailable interval events and separate stateful safety semantics before permitting sparse-window strategy evaluation; never fabricate volume/price or silently alter strict E5.12. New 2026 cost and charge-date evidence still needed. KR feeds need separate license, corporate events, calendar and fee validation. E6 research readiness is gated on robust evidence, not all-green job states or profitable-looking curves.
