# 시스템 아키텍처 — Adaptive Trading Engine

**상태:** 설계 초안 v0.1. 구현 완료를 뜻하지 않는다.

## 1. 핵심 목표
국내/미국 주식을 typed market events로 처리하는 증권사 독립 Trading Core를 만든다. **Simulation**은 Historical/Paper에서 가상 계좌·가상 체결을 다루고, **Evaluate/Session**은 거래 판단 **제안**을 생성한다. 실제 주문과 증권사 API, 실계좌의 권위 있는 원본은 **별도 외부 Execution Host/브로커 어댑터** 책임이다. 같은 전략·리스크·시장 이벤트 계약을 재사용하되 코어에 증권사 종속성과 실거래 권한을 넣지 않는다.

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
    Simulation: Synthetic Orders/Fills → Virtual Ledger/Position
                  OR
    Evaluate / Session → Decision / OrderIntent proposal
         ↓ (explicit boundary: external app only)
    External Execution Host → BrokerAdapter → Broker-owned Accounts
         ↓
    Verified Snapshot / Observed Order Events (read-only to Engine)
         ↓
    Event Journal + Performance/Experiment Registry
                          ↘ Research → Candidate → Validation → Shadow

- **Data:** 원본 보존, 시간·거래세션·결측 관리, 데이터 소스 책임.
- **Features:** EMA/ATR/VWAP/거래량·호가·재무 Feature 계산, 캐시·warmup·버전.
- **Intelligence:** 시장상태 분류/기업 분석/예측. 직접 주문권한 없음.
- **Strategies:** 타입/주기 요구사항 선언, 신호/목표노출 제안. 직접 브로커 호출 금지.
- **Allocator:** 같은 종목 여러 전략의 신호를 계좌 단위 목표노출로 통합.
- **Risk:** 시스템 hard limits > 계좌 > 시장/종목 > 전략 > AI 제안.
- **Simulation execution:** 엔진 내부의 주문 상태와 체결은 **가상 자금·가상 체결·모델 비용**만 의미한다. 외부 실행 Host만 실제 주문 outbox/멱등성/복구·대조를 소유한다.
- **Portfolio:** Historical/Paper의 **시뮬레이션** KRW/USD 장부, 예약금, 합성 체결, 수수료, 미결제, 손익. 실계좌 자산/미체결 주문의 권위 있는 기록은 브로커에 존재한다.
- **Research:** 후보 생성·실험·워크포워드·미관측 데이터 평가. Live 자동 승격 금지.

## 3. 결정론적 Core와 비동기 Shell

**Core:** (ImmutableState, OrderedEvent, ImmutableConfig) → (NewState, Commands, Outcomes). Reducer는 외부 호출이 없고 단일 writer가 상태를 변경한다. replay는 기록된 이벤트 순서와 버전/시드가 같으면 상태 해시가 같다.

**Shell:** WebSocket, REST, Storage, File I/O, timer, notification. 외부 비동기 수신 순서는 불안정할 수 있으므로 ingest ordinal, source sequence, available-at을 기록한다. Backtest는 그 기록을 재현한다.

처리:
1. Data Adapter → 정규화/품질 검사/저널에 기록
2. Clock/Coordinator가 관측 가능한 이벤트를 확정
3. 기존 주문/체결/포트폴리오/위험상태를 갱신
4. 적절한 Strategy 구독 및 FeatureGraph 평가
5. 신호→allocation→위험검증→(a) Simulation용 가상 주문 또는 (b) 외부 제출되지 않은 Decision/OrderIntent 제안 생성
6. Simulation은 합성 체결/가상 잔고를 갱신한다. 별도 실제 실행 애플리케이션은 자체 승인·영속 outbox·브로커 호출 및 주문/계좌 대조를 소유하며 엔진 SDK는 호출하지 않는다.
7. 엔진이 허용되는 검증된 관측 이벤트/스냅샷, 시뮬레이션 결과 및 감사 증거를 기록한다.

이전 시점에는 알 수 없었던 Feature에 접근하는 API를 허용하지 않는다. 이벤트 순서·스키마 버전은 실험 manifest에 저장한다.

## 4. Event / Command 분리
- Event = 이미 일어난 사실 (BarFinalized, FillRecorded, TradingHalted).
- Command = 수행 요청 (SubmitOrder, CancelOrder, ReconcileOrders, PersistSnapshot).
- Result = Accepted, Rejected, Unsupported, Unavailable 등 명시적 결과.
- Strategy는 Event를 소비해 Signal을 만들며, 신호가 바로 Order를 실행하지 않는다.
- 엔진 SDK의 OrderIntent는 **주문 송신 명령이 아니라 제출되지 않은 제안 값**이다. 외부 주문 서비스는 승인·별도 영속 outbox·브로커 결과를 근거로 실제 주문 상태를 관리하며, 확인 전 실제 체결을 추정하지 않는다.

## 5. 데이터 해상도와 FeatureGraph
- TradeTick/QuoteTick/OrderBook/Bar/MarketStatus/Fundamental/Disclosure를 서로 다른 타입으로 유지.
- DataRequirements는 타입·주기·warmup·시장세션·최대 지연을 선언.
- Tick→Bar, 1m→30m 등 상향 집계만 지원; 원본이 없으면 30m→1m/호가 복원 불가.
- 세션별 anchor, DST, 조기종료, corporate-action adjustment, 결측 관리.
- Feature cache key는 종목+집계주기+파라미터+계산 버전+원본 버전+as-of.
- 실시간 증분 계산과 과거 배치 계산은 동일 조건에서 수치 일치 테스트.

## 6. Research/Trading 권한 격리
Research는 승인된 원본/복제된 데이터에서만 실험하며, 운영 프로세스의 인증키/실거래 계좌/하드리스크 정책 변경 권한이 없다.

연구 후보 상태(가치/검증 추적): PROPOSED → HISTORICALLY_SIMULATED → VALIDATED → SHADOW → PAPER_APPROVED → EXTERNAL_EXECUTION_ELIGIBLE / RETIRED. 외부 실주문 배포는 애플리케이션 소유의 독립적 승인 절차이고 엔진 자동 전이가 아니다.
각 상태 변화는 실험 버전, 데이터 해시, 평가 근거 및 운영자 승인을 기록해야 한다. 이전 검증 버전으로 롤백 가능해야 한다.

## 7. 패키지·배포 단계
    src/invest_engine/
      domain/ core/ data/ features/ intelligence/
      strategies/ allocation/ risk/ execution/ portfolio/
      interfaces/ research/ cli.py
    external-execution-host/ (separate project / optional)
      adapters/ authorization/ outbox/ reconciliation/
    configs/ tests/ fixtures/ docs/

Core/domain/strategies/risk 및 신규 통합 Engine SDK는 Toss/Alpaca 등의 **실주문용 브로커 SDK를 import하지 않는다**. 실제 주문 어댑터·토큰·송신 I/O는 외부 애플리케이션 패키지만 소유한다. 기존 저수준 BrokerProtocol은 호환/인터페이스 경계이지 SDK에 Live 전송권을 부여하는 기능이 아니다.

- R0~R1: 로컬 Python package/CLI, Parquet 실험 데이터, 합성 fixture, 통합 CI.
- R2: 독립 Research runtime/experiment registry. DB 선택은 별도 ADR.
- R3: Paper 실시간 DataProvider + 영속 저널 + 복구.
- R4/E8: 별도 External Execution Host 연동의 검증/운영 트랙. 단일 active executor·고정 송신 IP·토큰/모니터링은 그 Host의 책임이며 Engine SDK에 `engine.live`를 도입하지 않는다.
- R5: GUI/SaaS는 별도 제품/법무 결정.

**참조:** DOMAIN.md, STRATEGIES.md, RISK_EXECUTION.md, VALIDATION.md, ADR.

## 8. 2026-11-22 SDK 책임 경계 개정

현재 설계의 신규 공개 API는 `Engine()` 아래 `simulation(...).historical()`, `simulation(...).paper()`, `research(...)`, `evaluate(...)`, `session(...)`이다. 앞의 Simulation만 가상 계좌·가상 체결을 소유한다. Evaluate/Session은 외부 브로커의 신뢰 가능한 계좌 스냅샷을 받아 **제안만 생성**한다. 실주문 실행은 외부 서비스가 따로 승인·대조하고, 엔진은 실계좌 권위 원장을 보관하거나 외부 주문 기능을 제공하지 않는다. E8은 그 외부 서비스의 선택적 연동 검증 단계다. [SDK 명세](E6_7_UNIFIED_SDK.md), [시뮬레이션 계약](E6_7_UNIFIED_SDK.md#historical-and-paper-simulation), [ADR-0034](adr/0034-unified-sdk.md) 참고. 이 경계 개정은 기존 E0–E6 구현/API를 삭제하거나 실거래를 승인하지 않는다.
