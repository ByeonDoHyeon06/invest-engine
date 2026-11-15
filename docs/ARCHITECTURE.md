# 시스템 아키텍처 — Adaptive Trading Engine

**상태:** 설계 초안 v0.1. 구현 완료를 뜻하지 않는다.

## 1. 핵심 목표
국내/미국 주식을 typed market events로 처리하고 동일한 Trading Core에서 Backtest, Forward Paper, 향후 Live를 실행한다. 데이터 공급자·해상도·전략·브로커를 자유롭게 교체하면서 **계좌/위험/주문은 중앙에서 관리**한다.

비목표: HFT, 1분봉 강제, GUI·SaaS 초기 개발, 매매수익 보장, 자동 코드 수정·승인 없는 실거래 배포.

## 2. 구성요소와 방향

    External Sources (historical/live market, filings, macro)
         ↓
    Adapters → Normalizer → Validation → PIT Event Store
         ↓
    Aggregator / FeatureGraph → StrategyContext (read-only)
         ↓
    Regime/Selector → StrategyPlugin → StrategySignal
         ↓
    Portfolio Allocator → OrderIntent → Pretrade Risk
         ↓
    Durable Outbox → ExecutionManager → BrokerProtocol
         ↓
    Order/Fill Events → Ledger/Position/Reconciliation
         ↓
    Event Journal + Performance/Experiment Registry
                          ↘ Research → Candidate → Validation → Shadow

- **Data:** 원본 보존, 시간·거래세션·결측 관리, 데이터 소스 책임.
- **Features:** EMA/ATR/VWAP/거래량·호가·재무 Feature 계산, 캐시·warmup·버전.
- **Intelligence:** 시장상태 분류/기업 분석/예측. 직접 주문권한 없음.
- **Strategies:** 타입/주기 요구사항 선언, 신호/목표노출 제안. 직접 브로커 호출 금지.
- **Allocator:** 같은 종목 여러 전략의 신호를 계좌 단위 목표노출로 통합.
- **Risk:** 시스템 hard limits > 계좌 > 시장/종목 > 전략 > AI 제안.
- **Execution:** 주문 상태머신, 영속 outbox, 누락/중복/불확실 주문 복구.
- **Portfolio:** KRW/USD 분리장부, 예약금, 체결, 수수료, 미결제, 손익.
- **Research:** 후보 생성·실험·워크포워드·미관측 데이터 평가. Live 자동 승격 금지.

## 3. 결정론적 Core와 비동기 Shell

**Core:** (ImmutableState, OrderedEvent, ImmutableConfig) → (NewState, Commands, Outcomes). Reducer는 외부 호출이 없고 단일 writer가 상태를 변경한다. replay는 기록된 이벤트 순서와 버전/시드가 같으면 상태 해시가 같다.

**Shell:** WebSocket, REST, Storage, File I/O, timer, notification. 외부 비동기 수신 순서는 불안정할 수 있으므로 ingest ordinal, source sequence, available-at을 기록한다. Backtest는 그 기록을 재현한다.

처리:
1. Data Adapter → 정규화/품질 검사/저널에 기록
2. Clock/Coordinator가 관측 가능한 이벤트를 확정
3. 기존 주문/체결/포트폴리오/위험상태를 갱신
4. 적절한 Strategy 구독 및 FeatureGraph 평가
5. 신호→allocation→pretrade risk→outbox
6. Broker 인터페이스 호출; 결과를 새로운 이벤트로 다시 입력
7. snapshot/report/관측 로그 기록

이전 시점에는 알 수 없었던 Feature에 접근하는 API를 허용하지 않는다. 이벤트 순서·스키마 버전은 실험 manifest에 저장한다.

## 4. Event / Command 분리
- Event = 이미 일어난 사실 (BarFinalized, FillRecorded, TradingHalted).
- Command = 수행 요청 (SubmitOrder, CancelOrder, ReconcileOrders, PersistSnapshot).
- Result = Accepted, Rejected, Unsupported, Unavailable 등 명시적 결과.
- Strategy는 Event를 소비해 Signal을 만들며, 신호가 바로 Order를 실행하지 않는다.
- Outbox/명령 처리는 durable 상태 확보 후 발생한다. Broker 결과 수신 전 실제 체결을 가정하지 않는다.

## 5. 데이터 해상도와 FeatureGraph
- TradeTick/QuoteTick/OrderBook/Bar/MarketStatus/Fundamental/Disclosure를 서로 다른 타입으로 유지.
- DataRequirements는 타입·주기·warmup·시장세션·최대 지연을 선언.
- Tick→Bar, 1m→30m 등 상향 집계만 지원; 원본이 없으면 30m→1m/호가 복원 불가.
- 세션별 anchor, DST, 조기종료, corporate-action adjustment, 결측 관리.
- Feature cache key는 종목+집계주기+파라미터+계산 버전+원본 버전+as-of.
- 실시간 증분 계산과 과거 배치 계산은 동일 조건에서 수치 일치 테스트.

## 6. Research/Trading 권한 격리
Research는 승인된 원본/복제된 데이터에서만 실험하며, 운영 프로세스의 인증키/실거래 계좌/하드리스크 정책 변경 권한이 없다.

후보 상태: PROPOSED → BACKTESTED → VALIDATED → SHADOW → PAPER_APPROVED → LIVE_ELIGIBLE → (명시적 승인 이후) LIVE / RETIRED.
각 상태 변화는 실험 버전, 데이터 해시, 평가 근거 및 운영자 승인을 기록해야 한다. 이전 검증 버전으로 롤백 가능해야 한다.

## 7. 패키지·배포 단계
    src/invest_engine/
      domain/ core/ data/ features/ intelligence/
      strategies/ allocation/ risk/ execution/ portfolio/
      brokers/ research/ cli.py
    configs/ tests/ fixtures/ docs/

Core/domain/strategies/risk는 Toss SDK 등 브로커 의존성을 import하지 않는다.

- R0~R1: 로컬 Python package/CLI, Parquet 실험 데이터, 합성 fixture, 통합 CI.
- R2: 독립 Research runtime/experiment registry. DB 선택은 별도 ADR.
- R3: Paper 실시간 DataProvider + 영속 저널 + 복구.
- R4: Live는 단일 active executor, 고정 송신 IP, 토큰 단일 관리자, 모니터링.
- R5: GUI/SaaS는 별도 제품/법무 결정.

**참조:** DOMAIN.md, STRATEGIES.md, RISK_EXECUTION.md, VALIDATION.md, ADR.
