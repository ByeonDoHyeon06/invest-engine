**E6.5a candidate (2026-11-19):** [Bounded parameter search](E6_5A_PARAMETER_SEARCH.md), [ADR-0031](adr/0031-bounded-parameter-grid.md). Canonical ORB parameter axes, explicit candidate/full matched replay budgets, immutable search digest pinned before fixed fold replay; four tests pending. E6.3b #47 merged `9d9ee94` (32 historical jobs, 63 eligible rows matched); E6.4a #48 merged `60a9d5d` (374 tests each); E6.4b #49 merged `b931a70` (378 tests each). Regime diagnostics synthetic only. No verified real-market search, adaptive feedback, holding-outcome access, or automatic strategy selection. E5 #6 OPEN, E6/G2 NOT ACCEPTED, LIVE NOT AUTHORIZED.

**E6.4b candidate (2026-11-19):** [Regime exposure and entry cohorts](E6_4B_REGIME_EXPOSURE.md), [ADR-0030](adr/0030-regime-exposure-cohorts.md). All observed validation minutes including unknown/no-fill; opening position share-minutes; allocate actual E5 average-cost realized PnL to FIFO entry quantity cohorts, with exact conservation and remaining inventory. Optional diagnostics pinned in fold context, four new tests pending. #47 merged `9d9ee94` after 32 successful historical jobs and 63 matched rows. #48 corrected Core CI 374 tests each, not yet merged at registration. No independent market profitability, cost-basis replacement or LIVE authority. E5 #6 OPEN, E6/G2 NOT ACCEPTED. Next E6.5 bounded candidate search.

**E6.4a candidate (2026-11-19):** [Causal market regimes](E6_4_MARKET_REGIME.md), [ADR-0029](adr/0029-causal-market-regimes.md). Session-local causal trend and RMS volatility axes; unknown missing/late/flagged data; pre-fill-bar-start attribution, cost/exit-PnL reconciliation, optional policy pinned to fold execution. Ten fixture cases including 12-arm opt-in integration, CI pending. No model training, calibrated thresholds, strategy filtering, market-wide regime or actual performance evidence. #47 corrected Core CI 364 tests each; latest f298ec3 Core CI green, real 2022 fee-aware/session-flat regressions pending. E5 #6 OPEN, E6/G2 NOT ACCEPTED, LIVE NOT AUTHORIZED.

**E6.3b candidate (2026-11-19):** [Fixed-rule fold execution](E6_3B_FOLD_EXECUTION.md), [ADR-0028](adr/0028-fixed-rule-fold-replay.md). Strict E5 replay across all registered validation folds/instruments and matched baseline/cost arms, exact timing and config digests bound before registered execution, durable provisional evidence. Four new integration tests including 12 synthetic E5 arms; CI pending. #46 Core CI 360 tests each on Python 3.12/3.13, #45 Core CI 354 each; parent fee regression pending at registration. No model fit, final holdout execution, actual market performance, or deployment approval. E5 #6 OPEN; next E6.4 market regime and fold-level summaries. LIVE NOT AUTHORIZED.

**E6.3a candidate (2026-11-19):** [Temporal walk-forward planner](E6_3_WALK_FORWARD.md), [ADR-0027](adr/0027-temporal-walk-forward.md). Rolling/expanding folds, timing-based label purge, embargo, disjoint validation, per-instrument minima and logical final partition; six fixture tests pending. Depends on #45 corrected f114f34; Core CI 44507038437 354 tests each, fee-aware regressions pending at registration. No fitting, fold execution, verified PIT data, or final holdout isolation certificate. E6.3b fold evidence execution/linkage next. #6 OPEN, LIVE NOT AUTHORIZED.

**E6.2 candidate (2026-11-19):** [Durable registry and E5 report bridge](E6_2_RESEARCH_JOURNAL.md), [ADR-0026](adr/0026-durable-research-journal.md). SQLite transactional command log, replay integrity, local holdout reservation and report structural reconciliation; imported reports are explicitly provisional. CI pending. No external attestation, actual holdout isolation or E6 release. Next walk-forward, regime, evidence adapter hardening. E5 #6 OPEN, LIVE NOT AUTHORIZED.

**E5.15b/c and E6.1 foundation VERIFIED + MERGED:** PR #43 merge `cbb8800` all six workflows green, 338 tests each; 42 prior eligible fee-aware rows unchanged. Kibot both samples retrieved; 4/4 blocked, 0 backtests. PR #44 merge `13e615f` Core CI 44505913031 344 tests each and independent gap diagnostic green. Missing observations remain unknown; IBM Oct 16 isolated minutes; OIH Oct max gap eight minutes. Pure candidate gate synthetic verification only. [Details](E6_2_RESEARCH_JOURNAL.md). E5/G1 market-data acceptance and E6/G2 remain open.

# 실행 로드맵 — Engine-first

**버전:** 0.1 · **작성:** 2026-11-15 · **상태:** Planned  
**원칙:** 체크리스트는 구현 여부가 아니라 검증 가능한 결과로 닫는다. **날짜가 아닌 품질 게이트 기반 진행.**

## 0. 범위·최종 목표

최초 목표는 개인용 headless **KR/US 주식 Long-only** 연구 엔진이다. 특정 봉에 종속되지 않는 데이터 이벤트, 결정론적 코어, 플러그인 전략, Risk-gated 주문, 재현 가능한 백테스트와 Forward Paper를 먼저 완성한다. Toss 연결 및 실거래는 후순위이고 GUI·SaaS는 범위 밖이다.

최종 비전은 시장 데이터 + 공시·재무·거시 Feature + Market Regime + 자동 전략 연구·비교를 통해 개선 후보를 발굴하는 **Adaptive Engine**이다. 연구 프로세스는 실거래 전략을 임의 변경하지 못한다.

## 1. 작업 방법

- **각 E단계 = Epic**. 구현 시 이슈를 작은 PR 단위로 분리한다. 한 PR은 테스트 가능한 범위만 담는다.
- **진척 기준:** [ ] Todo / [~] In progress / [x] Verified (증거/PR 링크 필수). 완료를 근거 없이 표기하지 않는다.
- **Definition of Done (공통):** 타입·스키마 문서, 테스트(정상/경계/장애), 예제/CLI 사용법, 회귀 CI, 변경된 ADR·Status·Roadmap 정리.
- **Gate:** 단위 테스트 통과만으로 다음 단계로 넘어가지 않는다. 재현성·데이터 무결성·안전성 조건을 확인한다.
- Phase E6의 Research는 **데이터 검증/실험 설계**부터 도입. 실시간 적용은 E7 이후.
- 개발 순서 기본값: E0 → E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8. E9는 별도 승인.
- 일정: 개발 추정치 대신 측정 가능한 완료 조건을 사용. 실시간 Paper 최소 **양국 각 20 거래일** 관찰은 시간 요건일 뿐 통과 보장은 아니다.

## 2. 단계별 계획

### E0 — Foundation & Contracts [VERIFIED, MERGED: PR #11]
**목표:** 외부 브로커 없이 순수 엔진의 타입·시간·결정론 계약 수립.

**작업:**
- [x] pyproject/표준 패키징, Python 3.12+, src layout, Ruff, mypy, pytest, GitHub Actions CI — run 43708153842
- [x] InstrumentId, Money, Quantity, UTC Timestamp, Market, EventEnvelope 정의 — PR #11 local test
- [x] TradeTick / QuoteTick / OrderBook / Bar / MarketStatus 이벤트 타입, 스키마 버전 — PR #11 local test
- [x] Trading Clock(UTC 내부 + 거래소 캘린더 주입), 순서/중복 정책 — PR #11 local test
- [x] 이벤트 유효성 검사 + typed exceptions(UnsupportedData, StaleData, InvalidEvent) — PR #11 local test. Result 래퍼/운영 상태 전이는 E2.
- [x] Synthetic fixtures + replay hash verifier + CLI; durable journal/production logs are E2 — PR #11 local test
- [x] API 키/비밀정보 기본 패턴 검사 스크립트·기존 gitignore 연동 — CI run 43708153842. (완전한 secret scanner가 아님)

**DoD:** 합성 입력 100~1,000개에 대해 같은 정렬/계산/상태 해시 재현; UTC/타임존 경계 테스트, 잘못된 이벤트 거절, 외부 의존성·실거래 없음.


**증거:** [PR #11](https://github.com/ByeonDoHyeon06/invest-engine/pull/11) · [CI run 43708153842](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43708153842). Python 3.12/3.13 각 37개 테스트·Ruff·mypy·기본 secret guard 통과. E0는 기초 데이터/이벤트 검증기만 완료했고 실제 Trading Core/Backtest는 E2~E5.

### E1 — Market Data, Resolution & PIT [VERIFIED, MERGED: PR #12–#14]
**의존성:** E0.

**작업:**
- [x] DataProvider Protocol, Normalizer, Validation, 품질 플래그 — [PR #12](https://github.com/ByeonDoHyeon06/invest-engine/pull/12), CI [43712325371](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43712325371)
- [x] Event-time / Available-at / Received-at 모델과 in-memory watermark/late quarantine policy — E1.1, durable state는 E2
- [x] 원본과 정규화 데이터의 분리 저장(Parquet + manifest/해시/라이선스 출처) — [E1.3 PR #14](https://github.com/ByeonDoHyeon06/invest-engine/pull/14), [CI 43714655109](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43714655109)
- [x] Tick→Time Bar(임의 positive timedelta), Bar→상위 Time Bar — [E1.2 PR #13](https://github.com/ByeonDoHyeon06/invest-engine/pull/13), [CI 43713285009](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43713285009)
- [x] 주입형 세션 anchor, DST, 명시적 조기폐장, 결측 거부, finalized bar의 offline aggregation — E1.2 PR #13. 공식 거래소 캘린더 공급자와 실시간 finalization은 후속
- [x] Volume/Dollar/Tick bars는 E0 BarKind 기본 타입으로 확장 지점 정의. 실제 집계 알고리즘은 후속 ADR/실험 단계에서 구현
- [x] DataCapability/DataRequest.require_capability 및 resampler의 하위 분봉·호가 허위 복원 거부 — PR #12/#13

**검증 결과:** [E1.1](DATA_INGESTION.md), [E1.2](RESAMPLING.md), [E1.3](DATASETS.md) 구현·검증 완료. [CI 43714655109](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43714655109): Python 3.12/3.13 각 76 passed + Ruff/mypy/secrets guard. 실제 거래소 캘린더 자동수집, 실시간 finalization, 기업행동 수정주가 적용 엔진은 이번 범위가 아니며 뒤 단계에서 별도 검증 필요.

**DoD:** 합성 Tick에서 1m/30m 바 생성, 거래소 세션/DST, 데이터 중복·지연·갭, 수정주가 정책의 데이터셋 메타데이터 보존(기업행동 변환 자체는 추후), 30m→1m 요청 거부, Parquet 재생·checksum 테스트 통과. [PR #12](https://github.com/ByeonDoHyeon06/invest-engine/pull/12) / [#13](https://github.com/ByeonDoHyeon06/invest-engine/pull/13) / [#14](https://github.com/ByeonDoHyeon06/invest-engine/pull/14).

### E2 — Deterministic Event Runtime [VERIFIED + MERGED: PR #15]
**의존성:** E1.

**작업:**
- [x] Single-writer immutable state reducer, typed observation-dispatch command contract — PR #15 tests
- [x] Strict ordinal/event-id/quality/observation-time ordering. E1 source-sequence gap quarantine retained; no implicit reordering.
- [x] SQLite WAL event journal, atomic append+checkpoint, restart replay/snapshot integrity checks; unsupported event schema rejected (migration implementation deferred).
- [x] Subscription routing by event type/market/bar interval and feature dependency DAG scheduler skeleton. Strategy execution/feature calculation deferred E4.
- [x] BACKTEST/PAPER share pure core; LIVE config intentionally refused pending authorized E8 adapter.
- [x] Fail-closed HALTED on invalid/stale/duplicate event, journal failure; persisted halt, explicit operator-reviewed restart. Full broker/account reconciliation remains E8.

**DoD:** Synthetic 500-event deterministic state hash, invalid event/clock rollback/duplicate rejection, 5 market payload codec roundtrips, snapshot+tail recovery, persisted halt, journal/snapshot corruption tests. **GitHub CI [run 43834211614](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43834211614): Python 3.12 and 3.13 each 99 tests passed; Ruff, mypy, secret guard successful** (before documentation-only final update).

**Merged evidence:** [Final CI 43834608280](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43834608280) — Python 3.12/3.13 each 99 passed, Ruff/mypy/secret guard green. [Merge 7d1b814](https://github.com/ByeonDoHyeon06/invest-engine/commit/7d1b814366cb5b4c4976db04ecbddf764c65ef82).

**Deliverable:** [PR #15](https://github.com/ByeonDoHyeon06/invest-engine/pull/15) · [E2 runtime contract](EVENT_RUNTIME.md). **Limitation:** E2 is observation state only; no order, trading ledger, real strategy execution or live broker, and restart currently replays entire journal (O(N)). Schema migration not implemented; unknown schema fails closed. Storage fault can prevent persisted halt, so operation host must block unattended restart on database fault.

### E3 — Portfolio, Risk, Order Simulation [COMPLETE — synthetic-only PR #17~#20]
**Pre-E3 contract gate (review first):** [ENGINE_IO.md](ENGINE_IO.md) · [ML_RESEARCH.md](ML_RESEARCH.md) · [ADR-0005](adr/0005-io-contracts.md). 외부 Run/Runtime/Prediction 계층을 구분하고 E3에 필요한 주문·포트폴리오 DomainEvent, 명시적 NO_ACTION/REJECTED, reason_codes, Decimal/UTC serialization, codec/journal migration을 고정한다. **E3의 ML 모델 구현은 금지(연구는 E6).**

**E3.4 PR #20 (검증·병합):** [E3_SETTLEMENT.md](E3_SETTLEMENT.md) + [ADR-0008](adr/0008-synthetic-settlement.md) — 합성 매도 비용/세금, 명시적 unsettled→settled 확정 이벤트, 재시작·감사 불변식. 실제 법적 세율/T+N 캘린더를 주장하지 않음. **CI [43852453688](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43852453688) Python 3.12/3.13 각 160 passed + Ruff/mypy/secrets 성공, [merge affe843](https://github.com/ByeonDoHyeon06/invest-engine/commit/affe8439642260923614f07394f8b9f46345942e). 합성 기반 E3 Gate 통과**. E4 전략, E5 자동체결, E8 실브로커는 별도 Gate.

**권장 E3 PR 분할:** (a) Money/Quantity precision·rounding ADR + 타입·스키마 golden fixtures, (b) Account/Order/Fill DomainEvent + codec/journal migration, (c) 위험·예약금·포트폴리오 reducer, (d) simulated broker/부분체결/UNKNOWN 장애 테스트, (e) API artifact/결정 이력 검증.

**의존성:** E2.

**E3.3 구현/검증 대상:** [PR #19](https://github.com/ByeonDoHyeon06/invest-engine/pull/19) · [E3_MONITORING.md](E3_MONITORING.md) · [ADR-0007](adr/0007-monitored-risk.md). 계좌통화별 신선한 mark/FX를 이용한 지분 평가, 손실 도달 시 세션 래치, external *synthetic* account snapshot 비교, 불일치 운영자 검토, SQLite replay. **CI 검증/병합 완료: 43849493669 (Python 3.12/3.13 각 150 passed)**. Legacy `require_monitoring=False`는 E3 합성 fixtures 호환을 위한 정책이며 실거래 허용치가 아니다.

**추후 범위:** 실제 거래소 캘린더 기반 일일 기준자산, 외부 브로커/신뢰정보 비교, 통합 FX 계좌 손실 제한, **실제 세율·거래소 결제/기업행동**은 E7/E8 또는 별도 ADR; E4 전략, E5 자동 체결 시뮬레이션에서 계약을 이어받아야 함.

**E3.2 하위 단계:** [PR #18](https://github.com/ByeonDoHyeon06/invest-engine/pull/18) — 합성 운영자 PAUSE/RESUME, 취소 요청 분리, 신선한 quote 기반 청산 계획(실제 체결 아님) 및 저널 복구 **CI 132 passed × 2, main 병합**.

**최초 하위 단계:** [PR #17](https://github.com/ByeonDoHyeon06/invest-engine/pull/17) — 합성주문 DTO·시뮬레이션 위험평가/장부·원자적 SQLite trade journal/outbox 및 정상·장애 테스트 **CI 검증·main 병합**. E3.2~3.4는 PR #18~#20에서 검증·병합됨.

**작업:**
- [x] KRW/USD 분리 ledger, 현금 예약, 합성 수수료·거래세·미결제금, 실현·선택적 시세기반 평가손익 ([PR #17~#20](https://github.com/ByeonDoHyeon06/invest-engine/pull/20), [CI](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43852453688))
- [x] OrderIntent → Pretrade Risk → Durable Outbox → **수동 합성** Fill → 주입된 계좌 참조 정합성 검사 (실시간 자동 Fill은 E5, 브로커 대조는 E8)
- [x] 주문 상태 머신(UNKNOWN/부분체결/취소/거부) 및 합성 부분체결
- [x] 동일 intent/Fill 재처리 방지, 저널·outbox·정산 상태 및 restart consistency
- [x] 합성 RiskLimits/mark freshness/daily loss/reconciliation hold (실제 시장/증권사 정책은 E7/E8)
- [x] Halt/Pause/Cancel/Flatten **계획** 분리, 오류 시 신규 진입 차단 (매도 실행·실거래 아님)

**DoD (E3 synthetic): PASS [PR #20 CI](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43852453688). 현금/미결제금·체결 수량·합성 세금/수수료·예약금 일관성, 중복 이벤트 0중복 반영, 재시작/UNKNOWN·복구·E3.3 레거시 저널 재생 검증. **실시간 자동 체결 추론(E5), 실제 증권사 계좌 대조(E8), 결제 달력·실제 세율(E7/E8) 제외.**

### E4 — Strategy SDK & Baseline [VERIFIED]
**의존성:** E2, E3. **병합/검증:** [PR #21](https://github.com/ByeonDoHyeon06/invest-engine/pull/21) + [PR #22](https://github.com/ByeonDoHyeon06/invest-engine/pull/22); [CI 43857703057](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43857703057) Python 3.12/3.13 각 191 passed, Ruff/mypy/secret guard green. [세부 사양](E4_STRATEGY.md) · [ADR-0009](adr/0009-strategy-boundary.md).

**작업:**
- [x] Strategy Manifest(DataRequirements, warmup, version, supported markets)
- [x] read-only StrategyContext + signal/target-position proposal (trusted internal Python plugins only)
- [x] FeatureGraph(EMA, ATR, volume filters) 및 as-of 조회 (reference batch implementation)
- [x] ORB_LONG_V1 기준 구현; 1m/5m은 **전략 설정**만으로 지정 (수익성 미검증)
- [x] 최저기준 비교군: NoTrade (buy-and-hold/EMA 전략은 필요 시 E5 실험에서 추가)
- [x] 여러 전략 충돌 시 allocator 정책 및 **합성 Fill 기반 전략별 가상 손익 장부**(in-memory, audit 포함)

**DoD:** 동일 입력에 동일 신호; warmup/데이터·세션 부족 시 신호 없음; 전략 Context에 브로커/계좌 변경 권한 없음; 위험/주문은 E3만 승인; 가상 Fill 귀속 보존/감사. Python Protocol은 외부 플러그인에 대한 보안 샌드박스가 아니므로 신뢰된 내부 전략만 허용.

**E5 통합 의존:** strategy decision/attribution ticket의 영속성, E2→E4→E3 실행기, 체결모델 및 Backtest report. **E4가 Live 안전성을 뜻하지 않는다.**

**E5.5 검증·병합 (PR #27, e638133; CI #44055595945 Python 3.12/3.13 232 passed):** [E5_FX_REPORTING](E5_FX_REPORTING.md) · [ADR-0013](adr/0013-point-in-time-fx-reporting.md) · PR #27. 사용자 제공 환율 자료를 신뢰 가능한 시각 이후에만 연구 보고에 사용하며, 누락 환율은 기본 통화 손익/MDD를 산출하지 않는다. 실제 비용/FX 공급원·기업행동·상폐/유니버스·틱/호가 검증 게이트는 여전히 OPEN.

### E5 — Backtest Engine & Reporting

**E5.13 provisional research COMPLETE + MERGED (2026-11-19):** [PR #38](https://github.com/ByeonDoHyeon06/invest-engine/pull/38), [merge d2550bb](https://github.com/ByeonDoHyeon06/invest-engine/commit/d2550bb98e7a197975da5799a0044dca35404878), [Core CI](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44494674900) 301 tests each (Python 3.12/3.13), [market study](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44494674899). 1,512/1,512 daily runs, 3,732 simulated fills, 67 initial attribution errors fixed. Three of 12 minute windows passed strict declared-session preflight; 12/12 comparison arms completed. 47,610 window-bars including 20 warmup sessions per window (24,210 evaluation; overlapping windows). Exact common numeric/result-field parity in eight completed pre/post-optimization minute runs. [Study and limitations](E5_13_MARKET_STUDY.md). **E5 release acceptance NOT met**; Issue #6 OPEN, LIVE NOT AUTHORIZED.

**E5.15b candidate (2026-11-19):** [Independent provider study](E5_15B_INDEPENDENT_PROVIDER.md), [ADR-0024](adr/0024-independent-provider-diagnostic.md). Kibot IBM/OIH raw sample, fixed Sep/Oct 2026 windows with strict minute-grid coverage and aggregate-only diagnostics. CI/study pending. HF Data Library account required, split-adjusted and IEX single-venue; no promotion from that source. Broader licensed panel, corporate-action/PIT verification and actual 2026 fees remain open. #6 OPEN, LIVE NOT AUTHORIZED.

**E5.14b.1/E5.15a and E5.14b.2 VERIFIED + MERGED:** [PR #41](https://github.com/ByeonDoHyeon06/invest-engine/pull/41) merge `87b6cd4`; [PR #42](https://github.com/ByeonDoHyeon06/invest-engine/pull/42) merge `d6239b7`. Core CI 328 tests each on 3.12/3.13, 42/42 eligible arms across six of 20 windows, all protected arms ended flat. [Fee-aware replay](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44501267176) matches fixed-tape PnL/costs/quantities/fills across all arms; base protected loss -947.48 USD, stress -1962.80 USD across independent accounts. [Results](E5_15B_INDEPENDENT_PROVIDER.md). Profitability and actual broker fees not established. E5 acceptance not met.

**E5.14a VERIFIED + MERGED (2026-11-19):** [PR #40](https://github.com/ByeonDoHyeon06/invest-engine/pull/40), merge `1d63a3c`, [CI](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44497904693) 311 tests each 3.12/3.13; 21/21 new provisional arms completed, hold 6/6 entries, all protected arms flat, profitability not established. [Results and current E5.14b/E5.15a candidate](E5_14B_FEE_AUDIT.md). **Next:** verify dated fixed-fill fee audit and eight newly prespecified Aug/Dec windows; then full fee-aware ledger/reservation replay and broader licensed independent market coverage. E5 #6 OPEN; LIVE NOT AUTHORIZED.

**Next E5.14 — acceptance and comparator quality:** add a separately versioned session-flat ORB exit/protection study and an executable, cost-comparable entry baseline with explicit fill coverage (no-fill is not proof of outperformance). Independently confirm provider rights, source/venue coverage, raw price/share units, historical data vintages, issuer actions, complete calendar and venue/broker fees; expand to more instruments and regimes without selecting windows by realized results. Record rejected/missing windows; distinguish retrospective research from PIT-certified results. Do not advance E6 release gates on these provisional results alone.

**E5.12 infrastructure VERIFIED + MERGED (2026-11-19):** [PR #36](https://github.com/ByeonDoHyeon06/invest-engine/pull/36), [merge 3146b96](https://github.com/ByeonDoHyeon06/invest-engine/commit/3146b96b4276644f60bd2235f967feb458b466b8), [PR CI 44492013440](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44492013440): Python 3.12/3.13 **298 passed each**, Ruff/mypy/secrets green. Fixed complete-session evaluation with >=20 prior sessions, no warm-up orders/strategy callbacks/equity, declared raw share volume and PIT evidence, NoTrade/initial-entry-hold/ORB synthetic next-bar integration tests. [Spec](E5_EVALUATION_WINDOW.md) / [ADR-0020](adr/0020-fixed-evaluation-window.md). **Actual 1m provider data NOT acquired or validated; no new real market ORB results.** Issue #6 OPEN, LIVE NOT AUTHORIZED.

**Historical E5.13 plan — practical study acquisition and acceptance:** Source a permitted consolidated or explicitly single-venue raw share-volume 1m series covering a predeclared evaluation month plus 20 prior sessions. Separate provisional historical study from real-provider acceptance: preserve unverified flags when only retrospective bars are available, never synthesize actual release timestamps/vintages or missing minutes. Independently verify source license, calendar, issuer actions, actual cost rules, and compare fixed-window ORB with predeclared baselines. No E6 promotion on synthetic evidence alone.



**E5.11 VERIFIED + MERGED (2026-11-19):** [PR #34](https://github.com/ByeonDoHyeon06/invest-engine/pull/34), [merge 7c2e733](https://github.com/ByeonDoHyeon06/invest-engine/commit/7c2e7336071eb37f3764d276048f5ca92b1c3d52), [PR CI 44489789537](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44489789537): Python 3.12/3.13 **291 passed each**, Ruff, mypy and basic secret guard passed. Evidence-declared terminal cash receipt for a held delisted position, bound to the exact issuer action ID and instrument; non-fill accounting, attribution and restart tests. No assumed recovery amount, no delayed settlement beyond terminal bar, no verified provider data. [Main CI](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44489896885). [Spec](E5_TERMINAL_SETTLEMENT.md) / [ADR-0019](adr/0019-terminal-delisting-cash-receipt.md). E5 Issue #6 OPEN; LIVE NOT AUTHORIZED.

**Next E5.12 — real-data acceptance:** obtain licensed historical 1m raw OHLCV with actual share volume and market coverage identified (not tick count); include at least 20 completed warm-up sessions before a fixed one-month evaluation window. Validate session calendar, gaps, point-in-time availability, splits/dividends/delistings, provenance, and fee/slippage assumptions. Compare ORB against predeclared NoTrade and buy/hold baselines using the same risk/cost assumptions; report realized/unrealized PnL, drawdown, fills, coverage, reproducibility and cost sensitivity. If data cannot be verified, report a blocker, not a performance claim. No E6 promotion or Issue #6 closure on synthetic evidence alone.

**E5.10 terminal delisting gate (research-only; [PR #33](https://github.com/ByeonDoHyeon06/invest-engine/pull/33), [PR CI 44072634428](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44072634428) green):** PIT-pinned final witnessed bar; record DelistingObserved via E3 and suppress last-bar entry signals. Held shares/unresolved orders fail closed with no synthetic recovery or forced price; historical E5.9 config/run hashes preserved when extension absent. [Design](E5_DELISTING_REPLAY.md) / [ADR-0018](adr/0018-delisting-terminal-bar-research.md). Release and real-world provider completeness remain unverified; E5 Issue #6 OPEN.\n\n

**E5.9 PR #31 (MERGED [963743d](https://github.com/ByeonDoHyeon06/invest-engine/commit/963743d3990180eba5d4e7635d7df618f98775d9), main CI [44070594750](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44070594750) success, Python 3.12/3.13 each 275 passed):** Optional PIT-declared dividend entitlement and later witnessed synthetic payment; net receivable in research equity, not spendable cash. Delisted position handling and one-month actual 1m share-volume ORB, verified real KR/US fee/tax/issuer data remain blockers. [E5_DIVIDEND_REPLAY](E5_DIVIDEND_REPLAY.md)/[ADR-0017](adr/0017-dividend-research-replay.md). Do not close E5 Issue #6 on synthetic evidence alone.


**E5.8 split-only PIT replay:** [PR #30](https://github.com/ByeonDoHyeon06/invest-engine/pull/30) · [CI 44067166215](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44067166215) Python 3.12/3.13 each 266 passed. Session-open, known-in-advance share split from SHA-pinned raw unadjusted price inputs and PIT evidence; E3/E4 inventory change and E4 history reset. [Spec](E5_SPLIT_REPLAY.md) / [ADR-0016](adr/0016-session-open-split-replay.md). Unsupported issuer events / standing protection still blocked. Real market provider completeness, dividends/delistings, Tick/Quote, and live fees remain UNVERIFIED. E5 epic remains OPEN.

 [E5.6 PIT metadata contract; real-data gate OPEN]

**E5.6 research contract ([PR #28](https://github.com/ByeonDoHyeon06/invest-engine/pull/28), [PR CI 44057468935](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44057468935), Python 3.12/3.13 each 245 passed):** optional SHA-pinned `pit_evidence` JSONL validates as-of universe membership and per-event canonical vintage hashes; dated corporate-action coverage; SPLIT/DIVIDEND/DELIST/MERGER/SYMBOL_CHANGE abort the entire backtest until actual portfolio adjustments exist. Generates `pit_gate.json` + manifest hashes; prior synthetic CLI remains valid with explicit missing-evidence warning. [Contract](E5_PIT_EVIDENCE.md) / [ADR-0014](adr/0014-pit-universe-vintage-gate.md). **Provider truth/completeness, broker fees, real corporate-action accounting and Tick/Quote execution are NOT VERIFIED. Issue #6 remains OPEN.**

**E5.4 research reliability:** [PR #26](https://github.com/ByeonDoHyeon06/invest-engine/pull/26), [E5_ROBUSTNESS.md](E5_ROBUSTNESS.md), [ADR-0012](adr/0012-audit-stress.md). Historical data gap/partial-session coverage, audit warnings (license, corporate action, PIT universe, real fees/FX unverified), file SHA256/source tree fingerprint, deterministic 4-case cost/liquidity stress. **PR #26 MERGED: [cac9bfe](https://github.com/ByeonDoHyeon06/invest-engine/commit/cac9bfede31f6ffc5bee555ee8be1913a4485c9f). Final PR [CI 44053364040](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44053364040): Python 3.12/3.13 each 225 passed, Ruff/mypy/secrets success.** No broker credentials or Live code. Original market files and baseline artifacts remain unchanged by stress runner. 

**Next E5.7 gate:** independently sourced/as-of issuer and adjustment data, actual split/dividend inventory and cash events, market-specific fee/tax/FX/timezone policy, Tick/Quote-assisted fill model scope and E5 research acceptance. E5.5 added research FX reporting; E5.6 adds a synthetic metadata consistency gate, **not** real-data certification. Do not close Issue #6 merely on synthetic tests.

**E5.3 code PR:** [#25](https://github.com/ByeonDoHyeon06/invest-engine/pull/25) (merged c4adfc6; GitHub PR CI Python 3.12/3.13 each 216 passed); [E5_PROTECTION](E5_PROTECTION.md) / [ADR-0011](adr/0011-protective-ohlcv.md). 보호청산은 기본 비활성·합성 OHLCV 가정; Live stop 주문과 다름. 충돌은 stop-first, 갭 하락은 adverse open 기준, 기존 미체결 SELL 충돌은 fail-closed. E5 전체 DoD는 E5.4에서 별도 점검 필요. 다음: 실험 manifest 재현/seed·FX/세금·다중시장 cost sensitivity·corporate actions/data vintage 검증.

**Implementation status (E5.1 merged PR #23, E5.2 merged PR #24):** 역사 이벤트→E2→E4 전략·Feature→E3 위험·가상 주문/체결 연결. 지정가 strict penetration, volume participation cap, fee/tax 및 별도 통화별 리포트. [E5_BACKTEST.md](E5_BACKTEST.md), [ADR-0010](adr/0010-bar-fill-assumptions.md). **E5 전체 검증/종료 아님.** E5.2 stop/target 겹침·갭·민감도, E5.2 오프라인 RunRequest/CLI/JSONL·manifest를 구현한 PR #24 GitHub CI 204 passed (Python 3.12/3.13) 후 병합 완료. E5.3은 stop/target 겹침·갭 손절과 비용/체결 강건성 검증 및 golden 테스트를 우선한다.
**의존성:** E3, E4.

**작업:**
- [ ] Event replay runner, next-eligible-event execution, no look-ahead
- [ ] Market-specific fees/tax/FX + slippage/spread sensitivity (**synthetic sensitivity verified E5.4**, real KR/US cost/FX rules unverified)
- [ ] OHLCV bar-based conservative fill vs Tick/Quote-assisted fill interface
- [x] partial fill/participation cap, unknown intrabar stop/take-profit ordering worst-case ([PR #25](https://github.com/ByeonDoHyeon06/invest-engine/pull/25), offline synthetic OHLCV only)
- [ ] experiment manifest = git commit + config + dataset hash + seeds + assumption versions (**actual source tree SHA/file digests verified in E5.4, user-supplied code_sha not authenticated; no randomized fills/seed yet**)
- [ ] equity, drawdown, CAGR(적절한 경우), PF, expectancy, turnover, trade log export

**E5.4 verified additions:**
- [x] Synthetic same-dataset cost/liquidity stress scenarios, ORB signal and fill sensitivity tests — PR #26 / CI 44053364040
- [x] Intraday bar gap/partial session warnings and unchanged historical inputs — PR #26
- [x] Output audit.json, file SHA-256 and actual Python source tree hash; tampering detection — PR #26
- [ ] Verified real-data point-in-time corporate adjustments/issuer universe and exchange/FX/fees provenance (E5.5 or explicit ADR scope decision)

**DoD:** 합성 체결 golden cases/경계 테스트, 미래 봉 가격 이용한 동시 체결 금지, 동일 실험 결과 재현, 수수료/슬리피지 변경이 결과에 반영.

### E6 — Research, Robustness & Adaptive Candidate Pipeline
**예측 모델 검증 계약:** [ML_RESEARCH.md](ML_RESEARCH.md). Persistence/zero-return/dummy baseline, 거래 비용 차감 경제적 성능, 시간 기반 split·purge, Feature as-of/label horizon, OOS/Shadow 검증을 필수화. 모델은 PredictionResult만 반환하며 주문 명령을 생성하지 않는다.

**의존성:** E5.

**작업:**
- [ ] 시계열 train/validation/untouched test 분리, walk-forward
- [ ] KR/US 기간·종목·시장상태별 성과 분해, 생존편향·공시시각 검증
- [ ] 수익률이 아닌 순수익·MDD·비용·거래수·안정성·실행 가능성 평가
- [ ] 시장 Regime baseline(추세/횡보/변동성/불확실) 및 no-trade 판정
- [ ] StrategyCandidate/ExperimentRegistry와 immutable version
- [ ] 자동 파라미터 제안(예: Optuna) → 독립 검증 → SHADOW 승인 후보
- [ ] ML(예측·드리프트 감지)은 선택적, 검증 없는 자동승격 금지

**DoD:** 기준선 대비 성능을 미관측 구간과 여러 비용 시나리오로 보고; 실패 전략 기각 기록; 최종 test set 재사용·과적합 경고; 자율 적용은 Shadow까지만.

### E7 — Real-time Paper & Shadow
**의존성:** E5, E6 일부; 실시간 데이터 공급자 별도 계약.

**작업:**
- [ ] Streaming Data Provider + reconnect/heartbeat/staleness detect
- [ ] Paper Broker, 실제 시세↔모의 체결, 종목별 data-quality dashboard(CLI/로그)
- [ ] active 전략 vs shadow 후보 독립 비교, 미체결 주문/portfolio 재시작 복구
- [ ] 양국 정규장·조기폐장·DST·휴장 및 네트워크 장애 처리
- [ ] 최소 각 시장 20거래일 Forward 관찰, 충분한 거래수/시장 상태 충족 검사
- [ ] 운영 Runbook, 수동 PAUSE 및 경고

**DoD:** 리플레이·실시간 처리 의미 일치, 장애/재시작 후 state reconcile, 증권사 실제 주문 0건, 누락·비정상 데이터 거래 중단 증거.

### E8 — Controlled Live (별도 GO 승인 필수)
**의존성:** E7 + API/이용약관 검토 + 보안 감사.

**작업:**
- [ ] Toss Adapter 별도 패키지(요청 스키마·토큰·허용 IP·rate-limit·WebSocket)
- [ ] 계좌별 single active executor, durable outbox, broker order reconciliation
- [ ] API 키 비공개 저장, egress 고정 IP, 권한 최소화, 백업·복구
- [ ] LIVE 기본 비활성화; 환경변수 한 개만으로 켜지지 않도록 2중 안전장치
- [ ] 처음은 소액·정규장·종목 제한·무레버리지·당일 청산 시도
- [ ] kill switch, 원격 알림, 주문/계좌/환율/세션 모니터링

**DoD:** 운영자 별도 승인·소액 주문 테스트·주문 체결 일치·장애복구 시연·runbook·자동 중지 검증. **수익률만으로 승인 불가.**

### E9 — Optional Extensions (착수 전 별도 ADR)
- [ ] OpenDART/SEC 시점정합 재무·공시 Feature
- [ ] Macro/sector, execution quality predictor, supervised ML·drift checks
- [ ] Multi-strategy portfolio optimization 및 자동 후보 승격 거버넌스 강화
- [ ] 모바일 관제, OSS 배포, 개인 앱; SaaS는 데이터 라이선스·금융법·브로커 계약 검토 이후 별도 프로젝트

## 3. 단계별 릴리스 정의
- **R0 — Correct Core:** E0~E3. 주문·자금·이벤트 모델 정확성 입증.
- **R1 — Researchable Engine:** E4~E5. 재현 가능한 전략 평가 완료.
- **R2 — Adaptive Research:** E6. 과적합 통제 하에 후보 제안·검증.
- **R3 — Observable Paper:** E7. 여러 주 동안 실시간 모의 검증.
- **R4 — Restricted Live:** E8. 별도 승인 후 제한된 주문.
- **R5 — Optional Product:** E9. 범위·라이선스 재검토.

## 4. 기술 부채·리스크 및 불확실성
1. Toss에서 필요한 수년치 분봉/체결 데이터가 확보될지는 미검증: 외부 데이터 라이선스/합성 fixtures 필요.
2. 1분 OHLCV는 intrabar 경로와 호가 대기열을 제공하지 않음: 체결 모델 과신 금지.
3. 실시간 거래 비용·수수료·세금·환전/미국 주문 조건은 실제 계좌 조건을 확인한 구성으로 주입.
4. Paper 성과는 Live 성과를 보장하지 않으며, 적은 거래수에서 수익성 주장 금지.
5. 개인용 API 사용 조건을 SaaS로 전제하지 않음.
6. 실거래 중 자율 코드 수정·자동 무승인 전략 배포 금지.

## 5. 개발 시작 체크리스트
- [ ] E0 이슈/하위 작업 확정 및 브랜치 생성
- [ ] pyproject.toml + tests + CI, 외부 API 호출 없는 구조 마련
- [ ] InstrumentId, Money, EventEnvelope, Clock의 불변 규칙 테스트
- [ ] fixture event replay → 결과 hash 비교
- [ ] README/STATUS에 구현 결과, PR, 테스트 명령, 다음 작업 기록

**완료 관리:** Roadmap의 체크박스는 실제 검증 시에만 업데이트한다. 작업별 상세 변경점은 이슈와 PR에 기록하고 Status에는 다음 작업과 블로커를 남긴다.
