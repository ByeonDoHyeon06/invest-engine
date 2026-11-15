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

### E1 — Market Data, Resolution & PIT [NEXT: Issue #2]
**의존성:** E0.

**작업:**
- [ ] DataProvider Protocol, Normalizer, Validation, 품질 플래그
- [ ] Event-time / Available-at / Received-at 모델과 watermark/late policy
- [ ] 원본과 정규화 데이터의 분리 저장(Parquet + manifest/해시/라이선스 출처)
- [ ] Tick→Time Bar(10s/1m/5m/30m/임의 기간), Bar→상위 Time Bar
- [ ] 세션 anchor, DST, 조기폐장, 결측, incomplete/finalized bar
- [ ] Volume/Dollar/Tick bars는 기본 계약 설계, 구현은 후속 단계 가능
- [ ] Capability 협상: 하위 분봉/호가를 가짜 복원하지 않고 거부

**DoD:** 합성 ticks와 동일한 기댓값으로 1m/30m 바 생성; 집계 경계, 중복·지연·갭·분할/수정주가 정책 테스트; 30m→1m 요청 명시적 실패.

### E2 — Deterministic Event Runtime
**의존성:** E1.

**작업:**
- [ ] single-writer reducer, immutable event/command 계약
- [ ] 이벤트 ordering(available_at, provider sequence, ingest index), replay clock
- [ ] checkpoint/snapshot, 이벤트 저널, schema migration policy
- [ ] strategy subscription routing, feature dependency scheduler 기본 뼈대
- [ ] Runtime(mode=BACKTEST/PAPER/LIVE)에서 동일 순수 코어 호출
- [ ] 처리 실패·중복·재시작 시 fail-closed 상태 설계

**DoD:** 이벤트 입력과 설정/버전/시드가 같으면 이벤트 로그와 상태 해시가 동일; 미래 정보 노출 및 동시성 비결정성이 테스트로 방지.

### E3 — Portfolio, Risk, Order Simulation
**의존성:** E2.

**작업:**
- [ ] 별도 통화 KRW/USD ledger, 현금 예약, 체결/수수료/세금/실현·평가손익
- [ ] OrderIntent → Pretrade Risk → Outbox → SimBroker → Fill → Reconciliation
- [ ] 주문 상태 머신 및 불명확한 접수(UNKNOWN)/부분체결/취소/거부
- [ ] unique intent/filled-event dedupe, idempotency & journal consistency
- [ ] System/Account/Market/Instrument/Strategy risk policy
- [ ] Halt/Pause/Cancel/Flatten 명령 분리, 오류 시 신규 진입 차단

**DoD:** 현금 불변식, 체결 수량·수수료·예약금 정확, 중복 이벤트 0중복 반영, 재시작·응답 유실 장애 주입 테스트.

### E4 — Strategy SDK & Baseline
**의존성:** E2, E3.

**작업:**
- [ ] Strategy Manifest(DataRequirements, warmup, version, supported markets)
- [ ] read-only StrategyContext + signal/target-position proposal
- [ ] FeatureGraph(EMA, ATR, volume filters) 및 as-of 조회
- [ ] ORB_LONG_V1 기준 구현; 1m/5m은 **전략 설정**만으로 지정
- [ ] 최저기준 비교군: buy-and-hold 또는 no-trade / 간단 EMA (연구 기준)
- [ ] 여러 전략 충돌 시 allocator 정책 및 전략 가상 장부

**DoD:** 전략 코드로 API/현금 변경 불가, 동일 입력에 동일 신호, 주기만 변경 시 코어 수정 불필요, warmup 미달·데이터 부재 때 주문 없음.

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
