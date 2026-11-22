## Current project state — 2026-11-20 (authoritative; supersedes historical entries below)

**E6.7 SDK public API design revised 2026-11-22** ([Issue #59](https://github.com/ByeonDoHyeon06/invest-engine/issues/59), [spec](E6_7_UNIFIED_SDK.md), [ADR-0034](adr/0034-unified-sdk.md), [23 reorganized examples](E6_7_SDK_EXAMPLES.md), [contract/migration matrix](E6_7_API_CONTRACT_MATRIX.md)). Inert mode-neutral `Engine()`. Direct `engine.backtest/research/evaluate(...)`; advanced typed `prepare/run`; caller-fed decision-only **`engine.session(...)`** E7; managed `engine.paper.start(...)` E7; `engine.live.start(...)` reserved E8 only. Uniform `data_provider`, strategy factories, risk/execution policy namespaces and finite-run result contract. Design only, no SDK/streaming implementation or permissions; prior E5/E6 validation gates remain open.

Current streaming design: preserve direct one-shot `engine.evaluate(...)`, use **`engine.session(...)`** for external continuous observations and `async with engine.paper.start(...)` for simulated managed data. [Streaming contract](E6_7_STREAMING_CONTRACT.md), examples 18–23. E6.7a defines the typed shape; E7 handles streaming implementation; E8 separately authorizes Live. Constructor/factory never opens accounts or starts tasks.

- E0–E4: verified simulation/core implementation. E5 [#6](https://github.com/ByeonDoHyeon06/invest-engine/issues/6) and E6 [#7](https://github.com/ByeonDoHyeon06/invest-engine/issues/7) remain **OPEN**; G1/G2 acceptance not met. E7/E8 not authorized; no actual trading.
- [#52](https://github.com/ByeonDoHyeon06/invest-engine/pull/52) merged `914439f`: E6.6a integrated offline research pipeline. Core [44513340667](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44513340667) 392 tests each (3.12/3.13), 74 source files; [44513340928](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44513340928) 20/20 jobs, 42 common result rows identical to #50 excluding elapsed/version hashes. Synthetic integration and durable review; no independent holdout.
- [#53](https://github.com/ByeonDoHyeon06/invest-engine/pull/53) merged `8b3f73f`: [44513901581](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44513901581) 20/20 jobs, 6/20 eligible windows, 72 arms. All four ORB variants negative in both base/stress aggregate PnL; 30m least loss (-584.51/-1,119.87 USD), not profitable. Reused retrospective panel.
- [#54](https://github.com/ByeonDoHyeon06/invest-engine/pull/54) merged `8f5a42b`: KRUS-80 frozen 40 US/40 KR cohort, five development years plus 2020 warmup; public [44515703858](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44515703858) 96/96 daily partitions, 24,128 rows, structural only. Core 393 tests each.
- [#55](https://github.com/ByeonDoHyeon06/invest-engine/pull/55) merged `d24b192`: authenticated raw SIP [44519434207](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44519434207) all 8 jobs successful, 58,593/60,320 daily observations (230/240 complete partitions), 22,393,263/23,438,400 minute observations (1,416/2,880 complete); 91 zero-volume daily rows; no source/duplicate/invalid errors. Missing rows include ticker identity and delisted periods; raw files ephemeral, not retained.
- [#56](https://github.com/ByeonDoHyeon06/invest-engine/pull/56) merged `3e1d1c5`: [44692687102](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44692687102) five annual jobs passed, 2,674/2,800 intended arms, 191/200 symbol-year windows, 9 blocked, zero execution errors; 115 windows matched to entered hold in both costs. All five active strategies negative mean and negative matched excess both costs. Adjusted retrospective prices, simulated costs, no executable-price/PIT certification. Core CI and public audit green.
- [#57](https://github.com/ByeonDoHyeon06/invest-engine/pull/57) MERGED `f4f1038`: [v4 run 44700445084](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44700445084) 12/12 jobs, 190,800 complete window-bars incl overlapping warmups, six provisional symbol-month windows/60 arms; five dividend overlap blocks and one unsupported merger. No execution errors. Aggregate base/stress net PnL (USD independent accounts): ORB15 -888.69/-1978.37, ORB30 -589.62/-1493.91, volume2 -269.13/-1249.70, hold -1459.11/-1458.12, cash zero. [Core CI 44700443964](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44700443964) 402 tests each 3.12/3.13, mypy 74 files. Research-only, no PIT/real execution certification. [Pilot details](ALPACA_RAW_MINUTE_PILOT.md).
- [#61](https://github.com/ByeonDoHyeon06/invest-engine/pull/61) MERGED `d75727d`: 72 arms / six provisional windows; 36 common controls matched #57, 405 tests each, mypy 75. USD PnL base/stress volume -269.13/-1249.70, weekly -118.55/-552.38, range +93.63/-252.08, combined +64.63/-162.80. All negative vs stronger hold/cash baseline; no strategy promoted. [Results](E6_6_REDUCED_TURNOVER.md).
- [#62](https://github.com/ByeonDoHyeon06/invest-engine/pull/62) temporal replication evidence complete (code `a3ab56b`, [run 44713239696](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44713239696)): 24/24 jobs, 14 eligible windows, 168/288 intended arms; 10 corporate-action blocks (8 warmup dividend overlaps, 2 unresolved cash merger), no replay errors; 375,660 observed/expected window-bars including warmups. All 14 hold pairs entered, 112 active arms end flat, no active arm exceeds max(cash, entered hold). Aggregate base/stress USD PnL volume -739.12/-1770.15, weekly -641.24/-1228.40, range -140.00/-249.32, combined -282.63/-361.69; hold +2323.67/+2024.59. No strategy promoted; not independent holdout. Core [44713239712](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44713239712) 412 passed/2 skipped each, mypy 75; legacy fee replay [44713239638](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44713239638) 20 jobs, 42 matched prior numeric/result rows (elapsed and three hashes excluded). This closes the frozen experiment, not E5/E6 gates. Final docs-only CI/review/merge pending.
- Next: finalize #62 review/merge and reconcile parallel SDK design #63 (design only); E6.7a API inventory/contracts may proceed in parallel, implementation follows existing evidence prerequisites. Separately predeclare corporate-action coverage follow-up (warmup-only domestic cash dividends with complete dates/no entitlement, raw-price discontinuity and feature checks; investigate unresolved merger identity with provider evidence; never relax evaluation-window action gates or invent data). No new parameter tuning on this panel, no independent holdout access, provider/PIT/actual cost/KR evidence still open.
- Authoritative docs: [KRUS-80](KRUS_80_DATASET.md), [Alpaca acquisition](ALPACA_AUTHORIZED_DATA_AUDIT.md), [daily research](ALPACA_DAILY_STRATEGY_PANEL.md), [pipeline](E6_6A_RESEARCH_PIPELINE.md), [sensitivity](E6_PROFITABILITY_AUDIT.md). Older dated notes are historical snapshots, not outstanding work instructions.

**E6.6a candidate (2026-11-19):** [Integrated research pipeline](E6_6A_RESEARCH_PIPELINE.md), [ADR-0033](adr/0033-offline-research-pipeline.md). #50 merged `8ef3b7a` (382 tests each; 20 historical jobs and 42 matched fee-aware rows), #51 merged `2d5c8a5` (388 tests each; Ruff B008 fixed). Compile deterministic plan and validation grid, execute E5+E6 journal, reconstruct canonical development review, explicit complete-matrix close only; four synthetic tests pending. No holdout execution or verified evidence upgrade. Caller retains prepared manifest; local journal is not external data isolation. E5 #6 OPEN, E6/G2 NOT ACCEPTED, LIVE NOT AUTHORIZED. Next E6.6b independent evidence and final evaluation boundary.

**E6.5b candidate (2026-11-19):** [Search lineage and robustness](E6_5B_SEARCH_LINEAGE.md), [ADR-0032](adr/0032-search-lineage-stability.md). Immutable local validation scope reservation before first replay, recorded/failed outcome matrices, reject reuse of reserved validation scopes, correlated UTC temporal blocks, paired worse-cost excess, positive fraction and worst leave-one-out. Six new synthetic tests pending. Parent #50 Core CI 382 tests each; real 2022 fee-aware regression pending at registration. Descriptive gates only; not formal significance, cross-DB data isolation or verified performance. Next E6.6 integrated offline research; E5 #6 OPEN, E6/G2 NOT ACCEPTED, LIVE NOT AUTHORIZED.

**E6.5a candidate (2026-11-19):** [Bounded parameter search](E6_5A_PARAMETER_SEARCH.md), [ADR-0031](adr/0031-bounded-parameter-grid.md). Canonical ORB parameter axes, explicit candidate/full matched replay budgets, immutable search digest pinned before fixed fold replay; four tests pending. E6.3b #47 merged `9d9ee94` (32 historical jobs, 63 eligible rows matched); E6.4a #48 merged `60a9d5d` (374 tests each); E6.4b #49 merged `b931a70` (378 tests each). Regime diagnostics synthetic only. No verified real-market search, adaptive feedback, holding-outcome access, or automatic strategy selection. E5 #6 OPEN, E6/G2 NOT ACCEPTED, LIVE NOT AUTHORIZED.

**E6.4b candidate (2026-11-19):** [Regime exposure and entry cohorts](E6_4B_REGIME_EXPOSURE.md), [ADR-0030](adr/0030-regime-exposure-cohorts.md). All observed validation minutes including unknown/no-fill; opening position share-minutes; allocate actual E5 average-cost realized PnL to FIFO entry quantity cohorts, with exact conservation and remaining inventory. Optional diagnostics pinned in fold context, four new tests pending. #47 merged `9d9ee94` after 32 successful historical jobs and 63 matched rows. #48 corrected Core CI 374 tests each, not yet merged at registration. No independent market profitability, cost-basis replacement or LIVE authority. E5 #6 OPEN, E6/G2 NOT ACCEPTED. Next E6.5 bounded candidate search.

**E6.4a candidate (2026-11-19):** [Causal market regimes](E6_4_MARKET_REGIME.md), [ADR-0029](adr/0029-causal-market-regimes.md). Session-local causal trend and RMS volatility axes; unknown missing/late/flagged data; pre-fill-bar-start attribution, cost/exit-PnL reconciliation, optional policy pinned to fold execution. Ten fixture cases including 12-arm opt-in integration, CI pending. No model training, calibrated thresholds, strategy filtering, market-wide regime or actual performance evidence. #47 corrected Core CI 364 tests each; latest f298ec3 Core CI green, real 2022 fee-aware/session-flat regressions pending. E5 #6 OPEN, E6/G2 NOT ACCEPTED, LIVE NOT AUTHORIZED.

**E6.3b candidate (2026-11-19):** [Fixed-rule fold execution](E6_3B_FOLD_EXECUTION.md), [ADR-0028](adr/0028-fixed-rule-fold-replay.md). Strict E5 replay across all registered validation folds/instruments and matched baseline/cost arms, exact timing and config digests bound before registered execution, durable provisional evidence. Four new integration tests including 12 synthetic E5 arms; CI pending. #46 Core CI 360 tests each on Python 3.12/3.13, #45 Core CI 354 each; parent fee regression pending at registration. No model fit, final holdout execution, actual market performance, or deployment approval. E5 #6 OPEN; next E6.4 market regime and fold-level summaries. LIVE NOT AUTHORIZED.

**E6.3a candidate (2026-11-19):** [Temporal walk-forward planner](E6_3_WALK_FORWARD.md), [ADR-0027](adr/0027-temporal-walk-forward.md). Rolling/expanding folds, timing-based label purge, embargo, disjoint validation, per-instrument minima and logical final partition; six fixture tests pending. Depends on #45 corrected f114f34; Core CI 44507038437 354 tests each, fee-aware regressions pending at registration. No fitting, fold execution, verified PIT data, or final holdout isolation certificate. E6.3b fold evidence execution/linkage next. #6 OPEN, LIVE NOT AUTHORIZED.

**E6.2 candidate (2026-11-19):** [Durable registry and E5 report bridge](E6_2_RESEARCH_JOURNAL.md), [ADR-0026](adr/0026-durable-research-journal.md). SQLite transactional command log, replay integrity, local holdout reservation and report structural reconciliation; imported reports are explicitly provisional. CI pending. No external attestation, actual holdout isolation or E6 release. Next walk-forward, regime, evidence adapter hardening. E5 #6 OPEN, LIVE NOT AUTHORIZED.

**E5.15b/c and E6.1 foundation VERIFIED + MERGED:** PR #43 merge `cbb8800` all six workflows green, 338 tests each; 42 prior eligible fee-aware rows unchanged. Kibot both samples retrieved; 4/4 blocked, 0 backtests. PR #44 merge `13e615f` Core CI 44505913031 344 tests each and independent gap diagnostic green. Missing observations remain unknown; IBM Oct 16 isolated minutes; OIH Oct max gap eight minutes. Pure candidate gate synthetic verification only. [Details](E6_2_RESEARCH_JOURNAL.md). E5/G1 market-data acceptance and E6/G2 remain open.

**E5.15b candidate (2026-11-19):** [Independent provider study](E5_15B_INDEPENDENT_PROVIDER.md), [ADR-0024](adr/0024-independent-provider-diagnostic.md). Kibot IBM/OIH raw sample, fixed Sep/Oct 2026 windows with strict minute-grid coverage and aggregate-only diagnostics. CI/study pending. HF Data Library account required, split-adjusted and IEX single-venue; no promotion from that source. Broader licensed panel, corporate-action/PIT verification and actual 2026 fees remain open. #6 OPEN, LIVE NOT AUTHORIZED.

**E5.14b.1/E5.15a and E5.14b.2 VERIFIED + MERGED:** [PR #41](https://github.com/ByeonDoHyeon06/invest-engine/pull/41) merge `87b6cd4`; [PR #42](https://github.com/ByeonDoHyeon06/invest-engine/pull/42) merge `d6239b7`. Core CI 328 tests each on 3.12/3.13, 42/42 eligible arms across six of 20 windows, all protected arms ended flat. [Fee-aware replay](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44501267176) matches fixed-tape PnL/costs/quantities/fills across all arms; base protected loss -947.48 USD, stress -1962.80 USD across independent accounts. [Results](E5_15B_INDEPENDENT_PROVIDER.md). Profitability and actual broker fees not established. E5 acceptance not met.

**E5.14a VERIFIED + MERGED (2026-11-19):** [PR #40](https://github.com/ByeonDoHyeon06/invest-engine/pull/40), merge `1d63a3c`, [CI](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44497904693) 311 tests each 3.12/3.13; 21/21 new provisional arms completed, hold 6/6 entries, all protected arms flat, profitability not established. [Results and current E5.14b/E5.15a candidate](E5_14B_FEE_AUDIT.md). **Next:** verify dated fixed-fill fee audit and eight newly prespecified Aug/Dec windows; then full fee-aware ledger/reservation replay and broader licensed independent market coverage. E5 #6 OPEN; LIVE NOT AUTHORIZED.

**E5.13 provisional research COMPLETE + MERGED (2026-11-19):** [PR #38](https://github.com/ByeonDoHyeon06/invest-engine/pull/38), [merge d2550bb](https://github.com/ByeonDoHyeon06/invest-engine/commit/d2550bb98e7a197975da5799a0044dca35404878), [Core CI](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44494674900) 301 tests each (Python 3.12/3.13), [market study](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44494674899). 1,512/1,512 daily runs, 3,732 simulated fills, 67 initial attribution errors fixed. Three of 12 minute windows passed strict declared-session preflight; 12/12 comparison arms completed. 47,610 window-bars including 20 warmup sessions per window (24,210 evaluation; overlapping windows). Exact common numeric/result-field parity in eight completed pre/post-optimization minute runs. [Study and limitations](E5_13_MARKET_STUDY.md). **E5 release acceptance NOT met**; Issue #6 OPEN, LIVE NOT AUTHORIZED.

**Next E5.14 — acceptance and comparator quality:** add a separately versioned session-flat ORB exit/protection study and an executable, cost-comparable entry baseline with explicit fill coverage (no-fill is not proof of outperformance). Independently confirm provider rights, source/venue coverage, raw price/share units, historical data vintages, issuer actions, complete calendar and venue/broker fees; expand to more instruments and regimes without selecting windows by realized results. Record rejected/missing windows; distinguish retrospective research from PIT-certified results. Do not advance E6 release gates on these provisional results alone.

**E5.12 infrastructure VERIFIED + MERGED (2026-11-19):** [PR #36](https://github.com/ByeonDoHyeon06/invest-engine/pull/36), [merge 3146b96](https://github.com/ByeonDoHyeon06/invest-engine/commit/3146b96b4276644f60bd2235f967feb458b466b8), [PR CI 44492013440](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44492013440): Python 3.12/3.13 **298 passed each**, Ruff/mypy/secrets green. Fixed complete-session evaluation with >=20 prior sessions, no warm-up orders/strategy callbacks/equity, declared raw share volume and PIT evidence, NoTrade/initial-entry-hold/ORB synthetic next-bar integration tests. [Spec](E5_EVALUATION_WINDOW.md) / [ADR-0020](adr/0020-fixed-evaluation-window.md). **Actual 1m provider data NOT acquired or validated; no new real market ORB results.** Issue #6 OPEN, LIVE NOT AUTHORIZED.

**Historical E5.13 plan — practical study acquisition and acceptance:** Source a permitted consolidated or explicitly single-venue raw share-volume 1m series covering a predeclared evaluation month plus 20 prior sessions. Separate provisional historical study from real-provider acceptance: preserve unverified flags when only retrospective bars are available, never synthesize actual release timestamps/vintages or missing minutes. Independently verify source license, calendar, issuer actions, actual cost rules, and compare fixed-window ORB with predeclared baselines. No E6 promotion on synthetic evidence alone.

**E5.11 VERIFIED + MERGED (2026-11-19):** [PR #34](https://github.com/ByeonDoHyeon06/invest-engine/pull/34), [merge 7c2e733](https://github.com/ByeonDoHyeon06/invest-engine/commit/7c2e7336071eb37f3764d276048f5ca92b1c3d52), [PR CI 44489789537](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44489789537): Python 3.12/3.13 **291 passed each**, Ruff, mypy and basic secret guard passed. Evidence-declared terminal cash receipt for a held delisted position, bound to the exact issuer action ID and instrument; non-fill accounting, attribution and restart tests. No assumed recovery amount, no delayed settlement beyond terminal bar, no verified provider data. [Main CI](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44489896885). [Spec](E5_TERMINAL_SETTLEMENT.md) / [ADR-0019](adr/0019-terminal-delisting-cash-receipt.md). E5 Issue #6 OPEN; LIVE NOT AUTHORIZED.

**Next E5.12 — real-data acceptance:** obtain licensed historical 1m raw OHLCV with actual share volume and market coverage identified (not tick count); include at least 20 completed warm-up sessions before a fixed one-month evaluation window. Validate session calendar, gaps, point-in-time availability, splits/dividends/delistings, provenance, and fee/slippage assumptions. Compare ORB against predeclared NoTrade and buy/hold baselines using the same risk/cost assumptions; report realized/unrealized PnL, drawdown, fills, coverage, reproducibility and cost sensitivity. If data cannot be verified, report a blocker, not a performance claim. No E6 promotion or Issue #6 closure on synthetic evidence alone.

**E5.10 (2026-11-17; implementation/verification):** Narrow PIT-pinned delisting gate: at the final confirmed historical bar, E3 delisting is recorded only for instruments with no holdings and no unresolved orders. Any held shares require separately verified terminal settlement; no cash proceeds, final price or bankruptcy recovery are invented. E5.9 research hashes are preserved when the extension is omitted. Synthetic local regression: 280 passed / 3 skipped; [PR #33](https://github.com/ByeonDoHyeon06/invest-engine/pull/33): [PR CI 44072634428](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44072634428) Python 3.12/3.13 both SUCCESS (Ruff, mypy, pytest and secrets); merge state on PR. [E5_DELISTING_REPLAY](E5_DELISTING_REPLAY.md) · [ADR-0018](adr/0018-delisting-terminal-bar-research.md). Real provider evidence, held-delist settlement and one-month 1m share-volume ORB remain UNVERIFIED; E5 Issue #6 OPEN, LIVE NOT AUTHORIZED.\n\n**E5.9 PR #31 (2026-11-17, VERIFIED + MERGED):** Implemented optional PINNED/PIT cash dividend ex-date entitlement and separately witnessed payment. Unpaid net receivable contributes to research equity, **not settled cash/buying power**. Local Python 3.13: **272 passed / 3 skipped** (Hypothesis/PyArrow missing); GitHub PR CI [44070182139](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44070182139): Python 3.12/3.13 **each 275 passed**, Ruff/mypy/secret guard success. Existing AAPL October 2026 22-day historical daily regression: USD 100,148.49 unchanged. [PR #31](https://github.com/ByeonDoHyeon06/invest-engine/pull/31) **main merged** [963743d](https://github.com/ByeonDoHyeon06/invest-engine/commit/963743d3990180eba5d4e7635d7df618f98775d9); final main [CI 44070594750](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44070594750) success, Python 3.12/3.13 each 275 passed, Ruff/mypy/secrets green. Delisted position resolution, real issuer/cost evidence and real 1m share-volume ORB remain unverified. E5 Issue #6 OPEN; LIVE NOT AUTHORIZED. [E5_DIVIDEND_REPLAY.md](E5_DIVIDEND_REPLAY.md) / [ADR-0017](adr/0017-dividend-research-replay.md).

# 프로젝트 현황 및 재개 지점

**E5.8 verified (2026-11-17, PR #30):** [PR #30](https://github.com/ByeonDoHyeon06/invest-engine/pull/30) PIT evidence + SHA-pinned raw session-open share split replay: E3 trading account / E4 virtual attribution and feature history transition, unsupported issuer actions rejected. [CI 44067166215](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44067166215): Python 3.12/3.13 each 266 passed, Ruff/mypy/secrets passed. [E5_SPLIT_REPLAY.md](E5_SPLIT_REPLAY.md), [ADR-0016](adr/0016-session-open-split-replay.md). 2026-10 AAPL 22 daily bars regression retains USD 100,148.49 final synthetic research valuation (NOT 1m ORB). Real provider completeness, broker costs, dividends/delistings and protected lots UNVERIFIED; E5 Issue #6 OPEN; LIVE NOT AUTHORIZED.


**최신 E5.7 완료 (2026-11-17):** [PR #29](https://github.com/ByeonDoHyeon06/invest-engine/pull/29) **main squash 병합 [cf1227b](https://github.com/ByeonDoHyeon06/invest-engine/commit/cf1227b167610e8d9324ccc2b4b0f0024eded452)**. 기업행동 합성 ledger/codec/저널 및 오프라인 CSV 변환기·거래량 단위 경계. 로컬 Python 3.13 **257 passed, 3 skipped**, GitHub Actions [44060129801](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44060129801) Python 3.12/3.13 **각 260 passed**, Ruff/mypy/secrets 성공. AAPL README 공개 미리보기 5개 봉으로 NoTrade 오프라인 파이프라인 시험(체결 0, PnL USD 0) 완료. **실제 ORB 수익성/데이터 원본 완전성 검증 아님.** E5.6 PIT는 여전히 기업행동 있으면 fail-closed; E5 Issue #6 OPEN, E7 forward paper 및 E8 Live 미착수.


**E5.6 (2026-11-17) [PR #28](https://github.com/ByeonDoHyeon06/invest-engine/pull/28):** PIT issuer/universe/vintage input gate implemented and local regression verified (242 passed, 3 skipped); GitHub PR CI [44057649091](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44057649091) verified: Python 3.12/3.13 **245 passed each**, Ruff/mypy/secret guard passed. [PR #28](https://github.com/ByeonDoHyeon06/invest-engine/pull/28) **main merged** as [98eb43c](https://github.com/ByeonDoHyeon06/invest-engine/commit/98eb43c34a8c1774020549e4bab00b097c597fb8). Next E5.7: actual issuer adjustment/accounting and market provider coverage verification; E5 Issue #6 still OPEN. See [E5_PIT_EVIDENCE](E5_PIT_EVIDENCE.md), [ADR-0014](adr/0014-pit-universe-vintage-gate.md). Optional synthetic-only evidence file; action-in-window abort and no silent delisted-symbol exclusion. **Real provider evidence, splits/dividends, exchange fees, tick/quote execution and E5 acceptance still OPEN.**


**기준일:** 2026-11-17
**현재:** E0~E4 완료. E5.1/#23·E5.2/#24·E5.3/#25 병합, **E5.4 PR #26 main 병합 (cac9bfede) / 최종 PR CI 통과** (Python 3.12/3.13 각 225 passed; Ruff/mypy/secrets green). E5 최종 신뢰성 게이트는 실제 시장별 비용·FX·PIT 기업행동/유니버스 검증 불완전으로 열어 둔다. 실거래 없음.
**E5.5 완료(2026-11-17, 연구 범위):** [PR #27](https://github.com/ByeonDoHyeon06/invest-engine/pull/27) main 병합 [e638133](https://github.com/ByeonDoHyeon06/invest-engine/commit/e6381333d4dbe74694c482d75e33ab113842256e). Python 3.12/3.13 각 232 passed·Ruff/mypy/secrets 성공 ([CI #44055595945](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44055595945)). [FX 명세](E5_FX_REPORTING.md)/[ADR-0013](adr/0013-point-in-time-fx-reporting.md). E5 실제 데이터 적격성 Gate OPEN.
**현재 Stage:** [E5 Issue #6](https://github.com/ByeonDoHyeon06/invest-engine/issues/6) (E5.7 synthetic issuer ledger + CSV smoke PR #29 VERIFIED/MERGED; next E5.8 integrated PIT action repricing/strategy attribution and licensed share-volume data). E5 real-provider PIT/actual share volume/action-price-adjustment gates OPEN; LIVE NOT AUTHORIZED.
**실거래 승인 상태:** NOT AUTHORIZED

## 완료된 E0/E1와 다음 실행 지점 (2026-11-15)

- E0 Epic: https://github.com/ByeonDoHyeon06/invest-engine/issues/1 (CLOSED)
- 병합 PR: https://github.com/ByeonDoHyeon06/invest-engine/pull/11
- Squash merge: https://github.com/ByeonDoHyeon06/invest-engine/commit/aae7bf7838c0abe8eeea6363461a358cb70db974
- **검증된 구현:** Python 패키지/CLI, InstrumentId·Money·Price·Quantity, MarketEvent 타입, UTC Clock, deterministic synthetic Replay, 기본 secret guard.
- **GitHub CI:** https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43708153842 — Python 3.12 및 3.13 **각 37 passed**; Ruff / mypy / credential guard 통과.
- E0 범위: **계좌/주문/위험·거래전략/백테스트 없음**. Replay는 이벤트의 일관된 해시를 검증할 뿐 실제 체결 시뮬레이터가 아님.
- 로컬: Python 3.13에서 36 passed + Hypothesis 미설치로 1 skipped. CI는 Hypothesis 포함 37 passed.
- **검증 완료:** [PR #12](https://github.com/ByeonDoHyeon06/invest-engine/pull/12) — DataProvider/Normalizer/Quality/PIT 계약. GitHub CI [run 43712325371](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43712325371): Python 3.12/3.13 Ruff/mypy/pytest/secret guard 전부 통과; PR #12 merged (13cb52d).
- **검증 완료:** [PR #13](https://github.com/ByeonDoHyeon06/invest-engine/pull/13), squash [1d8756c](https://github.com/ByeonDoHyeon06/invest-engine/commit/1d8756c6ae13fffdb79d39ecf33fdc0f9d443611). [GitHub CI 43713285009](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43713285009): Python 3.12/3.13 Ruff/mypy/pytest/secret guard 통과. 로컬 66 passed, 1 skipped(로컬 Hypothesis 미설치).
- **검증 완료:** [PR #14](https://github.com/ByeonDoHyeon06/invest-engine/pull/14), squash [77e7aab](https://github.com/ByeonDoHyeon06/invest-engine/commit/77e7aab5fb9433edbe53f084d800e52dd051cae2). [CI 43714655109](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43714655109): Python 3.12/3.13 각각 76 passed + Ruff/mypy/secret guard. 로컬 73 passed, 3 skipped(로컬 의존성 미설치). Parquet 실제 저장/복원 테스트는 CI에서 실행됨.
- **E2 구현:** [PR #15](https://github.com/ByeonDoHyeon06/invest-engine/pull/15) immutable State/Reducer + pure observation routing, DAG scheduler skeleton, SQLite event journal/atomic checkpoints/restart verification, fail-closed halt.
- **E2 CI:** [run 43834211614](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43834211614): Python 3.12/3.13 각각 99 passed + Ruff/mypy/secret guard. 로컬은 96 passed, 3 skipped (선택 라이브러리 미설치).
- **E2 병합 증거:** [PR #15](https://github.com/ByeonDoHyeon06/invest-engine/pull/15) squash commit [7d1b814](https://github.com/ByeonDoHyeon06/invest-engine/commit/7d1b814366cb5b4c4976db04ecbddf764c65ef82). 최종 PR CI [43834608280](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43834608280), Python 3.12/3.13 각 99 passed, Ruff/mypy/secret guard green.
- **다음 단일 작업:** E5.4에서 E5 전체 Gate 감사: 장세·종목/다중 통화별 비용 민감도, FX/세금/기업행동/데이터 계보, 체결 모델 한계, 백테스트 보고서·실험 manifest 누락 항목을 우선 점검하고 부족한 부분을 작은 PR로 구현. E6 자동연구 착수는 그다음. [E5 Issue #6](https://github.com/ByeonDoHyeon06/invest-engine/issues/6)에서 E2 관측 저널 → E4 전략 신호/배분 → E3 합성 OrderIntent/Fill/virtual attribution의 **결정론적 통합 Replay**를 먼저 설계하고, bar-only 보수적 체결모델과 cost/experiment manifest를 별도 PR로 구현. E4 연구 코드를 Live로 자동연결하지 않음.
- 미래 개선 TODO: Decimal 자릿수/통화별 반올림 정책은 E3 money ledger 이전에 별도 ADR 결정. 단순 범위 제한된 속성 테스트를 모든 입력에 대한 임의 정밀도 보장으로 해석하지 말 것.
- LIVE: NOT AUTHORIZED, 브로커 주문 호출 경로 없음.

## 기술 선택 상태
| 주제 | 상태 | 출처 |
| --- | --- | --- |
| Event-driven deterministic core | 채택 | ADR-0001 |
| Resolution-agnostic market events | 채택 | ADR-0002 |
| Personal-first, broker-independent | 채택 | ADR-0003 |
| Research/Live 분리, 승인된 전략만 Live | 채택 | ADR-0004 |
| ORM/DB/메시징/모델 | 미확정 | 필요 시 ADR |
| 실제 토스 API 계약·Rate limit 상세 | 검증 필요 | INTEGRATIONS.md |
| 주문 실거래 허용 | 미승인 | E8 Gate |


## GitHub Epic 추적
- [E0 — Issue #1](https://github.com/ByeonDoHyeon06/invest-engine/issues/1)
- [E1 — Issue #2](https://github.com/ByeonDoHyeon06/invest-engine/issues/2)
- [E2 — Issue #3](https://github.com/ByeonDoHyeon06/invest-engine/issues/3)
- [E3 — Issue #4](https://github.com/ByeonDoHyeon06/invest-engine/issues/4)
- [E4 — Issue #5](https://github.com/ByeonDoHyeon06/invest-engine/issues/5)
- [E5 — Issue #6](https://github.com/ByeonDoHyeon06/invest-engine/issues/6)
- [E6 — Issue #7](https://github.com/ByeonDoHyeon06/invest-engine/issues/7)
- [E7 — Issue #8](https://github.com/ByeonDoHyeon06/invest-engine/issues/8)
- [E8 — Issue #9](https://github.com/ByeonDoHyeon06/invest-engine/issues/9)
- [E9 — Issue #10](https://github.com/ByeonDoHyeon06/invest-engine/issues/10)

## Pre-E3 인터페이스 검토 (2026-11-16)

- 문서: [Engine Run/Runtime I/O](ENGINE_IO.md), [ML 연구 I/O/검증](ML_RESEARCH.md), [ADR-0005 Proposed](adr/0005-io-contracts.md).
- 목적: E0~E2 시장 데이터 이벤트/저널은 구현되었지만 외부 RunRequest/RunResult, 주문 이벤트, AI PredictionResult API는 **미구현**임을 명확히 구분.
- 검토 상태: Design proposal (NOT MERGED until review). **E3 개발·Live 주문은 시작하지 않음**.
- E3 연결 시 E2 SQLite journal/codec가 MarketPayload만 지원하므로 버전 있는 확장·복구 테스트 필수.

## E3 진행 기록 (2026-11-16)

- [PR #16](https://github.com/ByeonDoHyeon06/invest-engine/pull/16) 입출력·ML 설계 문서 2026-11-16 병합 완료. ADR-0005 boundary 원칙 승인; Run/ML 구현은 추후.
- [PR #17](https://github.com/ByeonDoHyeon06/invest-engine/pull/17) (MERGED): simulated-only OrderIntent/Fill/Portfolio Ledger, RiskLimits(cost basis), Decimal·currency precision (ADR-0006), 별도 versioned SQLite trading journal/outbox 및 복구, strict e3-sim-v1 JSON wire.
- E3.1 로컬 테스트: Python 3.13 **122 passed, 3 skipped**(Hypothesis/PyArrow 로컬 미설치). GitHub CI [run 43843169134](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43843169134) Python 3.12/3.13 Ruff/mypy/pytest/secret guard 모두 통과. [PR #17](https://github.com/ByeonDoHyeon06/invest-engine/pull/17) squash merged as [d49f95f](https://github.com/ByeonDoHyeon06/invest-engine/commit/d49f95f34001e0b0695e8565f1b14e1f108f231c).
- E3 잔여: mark-to-market equity/FX와 시장 세션 평가, 실시간 데이터로 모의 체결 결정하는 모델(E5), 실제 broker sync(E8), 전략/E2 통합 실행(E4~E5). E3 기간에는 적어도 **Pause/Cancel/Reduce/Flatten 명령** 및 위험 상태 정책을 후속 PR로 설계·검증해야 함.
- LIVE: NOT AUTHORIZED. 토스증권 API 모듈 없음.

## E3.2 진행 및 남은 E3.3 (2026-11-16)

- [PR #18](https://github.com/ByeonDoHyeon06/invest-engine/pull/18) (MERGED [96a2366](https://github.com/ByeonDoHyeon06/invest-engine/commit/96a2366a8f9dd57b33554ae08afe6ad28680779c)): 신규 BUY 일시중지/검토 후 재개, 확정 전 예약을 유지하는 일괄 취소 요청, 신선한 가격을 명시 입력받는 제한가 SELL 청산 *계획만* 생성. 새로운 이벤트 타입은 기존 E3 v1을 깨지 않도록 추가.
- 로컬 Python 3.13: **129 passed, 3 skipped**(Hypothesis/PyArrow 미설치). GitHub CI [43844743665](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43844743665): Python 3.12/3.13 각각 **132 passed**, Ruff/mypy/secret guard 성공.
- 다음 단계: Risk monitoring / stale market mark / daily-loss gate / reference broker account mismatch behavior 검증. 실제 시장·브로커 호출은 아직 없는 상태.

## E3.3 시세 평가·계좌 대조 (2026-11-16 · PR #19 MERGED)

- [PR #19](https://github.com/ByeonDoHyeon06/invest-engine/pull/19) **main 병합 / CI 검증 완료**: `MarketMark`, `FxMark`, session baseline, optional synthetic account reference, replayable `RiskObserved`/`AccountReconciliationReviewed`, daily-loss latch, marked equity/entry gate.
- 최종 PR CI [run 43849493669](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43849493669): Python 3.12·3.13 각각 **150 passed**, Ruff/mypy/secret guard 통과. [Squash merge d631e33](https://github.com/ByeonDoHyeon06/invest-engine/commit/d631e33f594448da6f73fac7b465fa0f05f9745b). 로컬 Python 3.13: **147 passed, 3 skipped** (Hypothesis/PyArrow 선택적 패키지 부재); CI에서는 둘 다 설치하여 3.12/3.13 수행.
- [E3_MONITORING.md](E3_MONITORING.md) · [ADR-0007](adr/0007-monitored-risk.md) · 금액/FX/세션 및 외부 스냅샷의 프로덕션 신뢰성은 후속 검증 항목.
- 실거래 연동 및 권한은 **NOT AUTHORIZED**; `require_monitoring=False` 기본값은 E3 합성 fixture 호환용이고 Live 안전성을 의미하지 않음.

## E3.4 — 합성 거래 세금·정산·Audit (2026-11-16 · verified/merged)

- [PR #20](https://github.com/ByeonDoHyeon06/invest-engine/pull/20): sell_tax_rate (합성값), 명시적 매도대금 미결제금/현금 정산 이벤트, 각 Fill별 gross/fee/tax 장부, reducer invariants 감사. 문서 [E3_SETTLEMENT](E3_SETTLEMENT.md) · [ADR-0008](adr/0008-synthetic-settlement.md).
- 로컬 Python 3.13: **157 passed, 3 skipped** (Hypothesis/PyArrow 미설치). 이전 E3.3 코드로 작성한 SQLite 저널을 신코드에서 동일 해시/금액으로 복구했음.
- GitHub CI: 최초 mypy 변수 이름 충돌 수정 후, 최종 PR CI [43852259445](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43852259445) 성공, Python 3.12/3.13 각 160 passed; merge [affe843](https://github.com/ByeonDoHyeon06/invest-engine/commit/affe8439642260923614f07394f8b9f46345942e) 후 [main CI 43852453688](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43852453688) 성공.
- 정산 방식은 실제 거래소 영업일이나 법적 세금 규정이 아닌 합성 확인 정책이며, 증권사 API나 실제 주문은 없음.

## E4 Strategy SDK 검증 완료 (2026-11-16)

- [PR #21](https://github.com/ByeonDoHyeon06/invest-engine/pull/21): StrategyManifest/DataRequirements/읽기 전용 Context/Signal/Registry/NoTrade, as-of EMA/ATR/median volume, ORB_LONG_V1, multiple-strategy target allocator and broker-free simulated intent planner.
- 문서: [E4_STRATEGY.md](E4_STRATEGY.md) · [ADR-0009](adr/0009-strategy-boundary.md).
- **검증 상태:** [PR #21](https://github.com/ByeonDoHyeon06/invest-engine/pull/21) merged (970834b); [PR #22](https://github.com/ByeonDoHyeon06/invest-engine/pull/22) merged (6d32a30), [CI 43857703057](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43857703057) Python 3.12/3.13 각 191 passed + Ruff/mypy/secret guard; [E4 Issue #5](https://github.com/ByeonDoHyeon06/invest-engine/issues/5) CLOSED.
- 구현: E4.3은 실제 합성 Fill을 전략별 가상 포지션/실현손익으로 귀속하고 E3 장부와 수량을 감사. **단, 가상 귀속 티켓은 아직 in-memory**: E2/E3 저널과 원자적으로 결합한 복구·백테스트 실행기는 E5. 실제 수익 검증/Backtest 미구현, Live는 E8 별도 승인.

## E4 완료 요약 (2026-11-16)

- [PR #21](https://github.com/ByeonDoHyeon06/invest-engine/pull/21): typed Strategy SDK, validated FeatureRegistry, NoTrade/ORB, account-currency allocation/OrderIntent planning (squash 970834b).
- [PR #22](https://github.com/ByeonDoHyeon06/invest-engine/pull/22): shared synthetic Fill attribution, strategy-level virtual holdings/realized P&L, idempotency/overfill checks, E3 portfolio audit (squash 6d32a30).
- **최종 E4 PR CI:** [43857703057](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43857703057) Python 3.12/3.13 각각 191 passed, Ruff/mypy/secret guard green. 로컬 Python 3.13 188 passed + 3 skipped (선택 패키지 미설치).
- **E5로 이월:** 전략 신호/귀속 티켓의 영속 트랜잭션 경계, E2/E4/E3 replay orchestration, actual fill model, fee/slippage stress, report/Run API.
- LIVE: NOT AUTHORIZED; 토스증권 연결 없음.

## E5.3 합성 보호청산 모델 (2026-11-17 · PR #25 MERGED)

- [PR #25](https://github.com/ByeonDoHyeon06/invest-engine/pull/25): `ProtectionPolicy` 기본 비활성, 관측된 매수 Fill 이후 다음 봉에서만 stop/target 평가, stop-first 충돌, 갭하락 불리한 체결, 엄격 target 관통, per-bar 참여 상한, 부분 청산, E3/E4 장부 귀속.
- [E5_PROTECTION.md](E5_PROTECTION.md) · [ADR-0011](adr/0011-protective-ohlcv.md). 합성 정책은 증권사 실제 stop 주문이 아니며 가격·체결 보장 없음. 주문 충돌은 InvalidEvent로 fail-closed.
- 로컬 Python 3.13: **213 passed, 3 skipped** (Hypothesis/PyArrow 미설치). GitHub CI [run 44050886947](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44050886947) Python 3.12/3.13 각각 **216 passed**, Ruff/mypy/secrets 성공. E5 전체는 아직 미완료.
- **다음:** E5.4 데이터 계보·비용·보고서·시장 모델 잔여 Gate 검토. E6 ML/Walk-forward는 E5 릴리스 통과 후.

## E5.4 데이터 감사·비용 민감도 검증 (2026-11-17)

- [PR #26](https://github.com/ByeonDoHyeon06/invest-engine/pull/26): 종목·시간봉·세션별 BAR_GAP/partial coverage 검사, 무검증 자료의 명시적 경고, `audit.json`·artifact file SHA-256·코드 소스트리 fingerprint, `invest-engine stress` 4단 비용/유동성 가정 비교.
- **최종 GitHub PR CI [run 44053364040](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44053364040): Python 3.12/3.13 각각 225 passed + Ruff/mypy/secret guard 통과. 병합 커밋 [cac9bfe](https://github.com/ByeonDoHyeon06/invest-engine/commit/cac9bfede31f6ffc5bee555ee8be1913a4485c9f).** 첫 PR run의 mypy Optional interval 오류는 후속 커밋에서 수정·재검증.
- 로컬 Python 3.13: 222 passed, 3 skipped (Hypothesis/PyArrow 미설치).
- [E5_ROBUSTNESS.md](E5_ROBUSTNESS.md) · [ADR-0012](adr/0012-audit-stress.md). 합성 ORB 시나리오와 데이터 훼손/기존 결과 보호 테스트 포함.
- **미검증:** 실제 시장별 수수료·세금·FX, PIT 기업행동/상폐 종목·원본 라이선스, Tick/Quote 체결 모델. E5 Issue #6 아직 OPEN; LIVE NOT AUTHORIZED.

## 변경 기록
- 2026-11-17: E5.3 [PR #25](https://github.com/ByeonDoHyeon06/invest-engine/pull/25) squash merged [c4adfc6](https://github.com/ByeonDoHyeon06/invest-engine/commit/c4adfc6d55a010dbd0fa57e24fd48f828fac1556); final PR [CI 44051089001](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44051089001) Python 3.12/3.13 각 216 passed, Ruff/mypy/secret guard 성공. E5.4 gate audit NEXT.

- 2026-11-16: E3.4 [PR #20](https://github.com/ByeonDoHyeon06/invest-engine/pull/20) merged `affe843`, main CI `43852453688` Python 3.12/3.13 each 160 passed + Ruff/mypy/secrets. E3 synthetic core complete, E4 Issue #5 NEXT.
- 2026-11-16: E3.3 PR #19 squash merged `d631e33`, PR CI 43849493669 3.12/3.13 각각 150 passed. 잔여 E3.4 점검 후 E4로 이동 예정.
- 2026-11-16: [E2 PR #15](https://github.com/ByeonDoHyeon06/invest-engine/pull/15) squash merged (7d1b814); 최종 [CI 43834608280](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43834608280) Python 3.12/3.13 각 99 passed + Ruff/mypy/secret guard. E2 Issue #3 closed; E3 다음 단계.
- 2026-11-16: E2 코드 PR #15에서 통과(GitHub CI 43834211614). 문서/상태 반영 중, 병합 전. 라이브 기능 없음.
- 2026-11-15: E1.3 PR #14 squash merged (77e7aab), [CI 43714655109](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43714655109) Python 3.12/3.13 각각 76 passed. E1 전체 데이터 기반 검증, Issue #2 종료 및 E2 next.
- 2026-11-15: E1.3 PR #14 생성; immutable Parquet raw/normalized datasets, SHA256 및 provenance 명세. CI 검증 중.
- 2026-11-15: E1.2 PR #13 squash merged (1d8756c), GitHub CI 43713285009 양쪽 Python 버전 통과. E1.3 next.
- 2026-11-15: E1.2 PR #13 구현 중. 세션 기준 시간봉 재구성과 미국 DST/조기폐장 검증(로컬 66 passed + Hypothesis 미설치 1 skipped).
- 2026-11-15: E1.1 PR #12 squash merged (13cb52d), CI run 43712325371 양쪽 Python 버전 정상. E1.2가 다음 작업.
- 2026-11-15: E1.1 브랜치 feat/e1-ingestion-quality-pit 및 Draft PR #12 생성. 엄격한 공급자 원시데이터 정규화·feed quarantine·as-of 관측 경계 추가. 전체 E1은 미완료.
- 2026-11-15: 빈 저장소에서 비전/계획 문서 작성, E0 진입 예정.
- 2026-11-15: E0 도메인/이벤트/결정론적 replay 코드·CLI·테스트·CI 초안, Draft PR #11 (로컬 36 passed, 1 skipped).
- 2026-11-15: [CI run 43708332491](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43708332491)에서 Python 3.12/3.13 각 37 passed 및 Ruff/mypy/secret 검사 성공. E0 검증 통과.
- 2026-11-15: PR #11 squash merged (aae7bf7); Issue #1 closed. E1 Issue #2가 다음 작업.

## 회차 종료·재개 기록 템플릿
- 날짜:
- 현재 E단계:
- 완료된 PR/commit:
- 검증 커맨드·결과:
- 미완료 작업:
- 블로커:
- 다음 단일 작업:
- 변경된 ADR:
- 라이브 안전 상태:

**에이전트 및 개발자는 새 작업 시작 전 README → STATUS → ROADMAP → 관련 설계/ADR을 읽고, 끝날 때 STATUS를 갱신한다.**

## E5.1 구현 기록 (2026-11-16)
- [PR #23](https://github.com/ByeonDoHyeon06/invest-engine/pull/23): E2→E4→E3 결정론적 역사 replay 연결, 기존 주문의 다음 봉 관통 조건과 참여 상한·부분 체결, 가상 수수료·통화별 성과·결정 trace. 코드에서 broker/network 호출 없음.
- 로컬 Python 3.13 196 passed, 3 skipped (Hypothesis/PyArrow 로컬 미설치). GitHub CI Python 3.12/3.13 검증 후 [squash f3b0626](https://github.com/ByeonDoHyeon06/invest-engine/commit/f3b062686ef4ec5ff24a2acce39802923e74a394) main 병합 완료.
- E5.1은 E5 전체 완료가 아님: stop/target/갭·큐·실험 CLI 미완료. E6 자동 학습·E7 Forward·E8 LIVE 미착수.

## E5.2 CLI/manifest (2026-11-16)
- [PR #24](https://github.com/ByeonDoHyeon06/invest-engine/pull/24): `invest-engine backtest --config`와 strict e5-research-v1 JSON, canonical market JSONL·dataset SHA256, 명시적 sessions/strategy/risk/cost, manifest/report export. LIVE 입력 금지. 테스트 ORB 21-session end-to-end 추가.
- 로컬 전체 테스트 201 passed, 3 skipped (선택 Hypothesis/PyArrow 부재). [GitHub CI #43862781540](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43862781540) Python 3.12/3.13 각 204 passed, Ruff/mypy/secrets 통과. [PR #24](https://github.com/ByeonDoHyeon06/invest-engine/pull/24) squash [12823e7](https://github.com/ByeonDoHyeon06/invest-engine/commit/12823e755dbbacba6898711d6e0dbb01021fbd71) main 병합. E5 완료 처리는 보류.

## E5.5 PIT FX 연구 보고 (2026-11-17)
- [PR #27](https://github.com/ByeonDoHyeon06/invest-engine/pull/27): 옵트인 FX JSONL, direct pair/as-of 시간/파일 해시 검증 및 기준 통화 연구 평가. 불완전한 FX 이력은 `fx_net_pnl`·`fx_max_drawdown`을 null로 반환.
- [E5_FX_REPORTING](E5_FX_REPORTING.md), [ADR-0013](adr/0013-point-in-time-fx-reporting.md) 참고. FX 실거래·매수 가능 금액 계산 미포함.
- **E5 최종 게이트 OPEN:** 시장별 실제 수수료·세금, 역사적 기업행동·상장폐지/유니버스(PIT), 틱·호가 체결 가정 실증. E6 및 실거래 진입 승인 아님.
- **다음 작업:** corporate-action & point-in-time instrument-universe 데이터 적격성 계약, historical tick/quote fill 모델 검증의 범위 분리. E5 Issue #6 OPEN.

- **E5.5 최종 병합 검증:** PR #27 squash e638133; PR CI #44055595945 Python 3.12/3.13 각 232 passed, Ruff/mypy/secret guard 통과. 실데이터/수익성 검증 아님.
