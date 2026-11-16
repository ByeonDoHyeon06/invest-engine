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

### E5 — Backtest Engine & Reporting
**의존성:** E3, E4.

**작업:**
- [ ] Event replay runner, next-eligible-event execution, no look-ahead
- [ ] Market-specific fees/tax/FX + slippage/spread sensitivity
- [ ] OHLCV bar-based conservative fill vs Tick/Quote-assisted fill interface
- [ ] partial fill/participation cap, unknown intrabar stop/take-profit ordering worst-case
- [ ] experiment manifest = git commit + config + dataset hash + seeds + assumption versions
- [ ] equity, drawdown, CAGR(적절한 경우), PF, expectancy, turnover, trade log export

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
