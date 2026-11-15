# 위험 관리 · 주문 처리 · 포트폴리오 안전 계약

**적용:** Backtest / Paper / Live 공통 코어. Live 활성화는 E8 별도 승인.
**중요:** 위험 한도는 의도된 신규 진입 제한이며 급등락·유동성 부족시 손실을 보장하지 않는다.

## 1. 핵심 불변 조건
1. 전략/ML/연구 코드는 Broker API에 직접 접근할 수 없다.
2. 모든 신규 위험 증가 주문은 PreTradeRisk 승인 필수.
3. 동일한 OrderIntent의 중복 전송 방지. 접수 여부 모르면 주문 조회/정합화 후에만 처리.
4. Fill 중복 적용 금지, 누적체결 수량은 주문수량 이하.
5. 미체결 매수 예약현금을 가용현금에서 제외하고 매도 예약주식도 중복 판매 방지.
6. 현금·포지션은 검증된 Fill/수수료/환전/기업행동 등 명시적 이벤트로만 수정.
7. stale data/unknown orders/account mismatch/invalid FX시 신규 진입 금지.
8. 어떤 학습/모델도 시스템 하드리스크 한도를 자동 완화할 수 없다.

## 2. 주문 데이터 흐름

    StrategySignal → Allocator → OrderIntent
       → RiskDecision(approve/reject/reduce with reason)
       → durable Outbox → ExecutionManager (single active writer)
       → BrokerProtocol (simulated/paper/live)
       → OrderEvent + Fill → Ledger/Position
       → Broker Reconciliation + Audit

주문 전송의 timeout은 실패 확정이 아니다. 실제 브로커가 주문을 접수했는지 불명확하면 상태 UNKNOWN을 유지하고 broker order/fill list 조회로 복원한다. 재전송은 대조 후 안전하다고 입증된 경우에 한함.

## 3. 주문 상태 머신

- CREATED → APPROVED → SUBMITTING → ACCEPTED
- ACCEPTED → PARTIALLY_FILLED → FILLED
- ACCEPTED 또는 PARTIALLY_FILLED → CANCEL_PENDING → CANCELED
- 어느 단계든 API 규약에 맞는 REJECTED 또는 RECONCILING 전환 가능
- SUBMITTING → UNKNOWN → RECONCILING → confirmed external state
- terminal 상태 이후 늦은 fill 이벤트는 버리지 않고 중복/불일치 판단 후 reconcile

OrderIntent ID, BrokerOrder ID, provider clientOrderId, execution ID를 혼동하지 않는다. provider 멱등성 기간에 의존하지 않고 로컬 영속 ID로 dedupe한다.

## 4. Risk Engine 3계층
- **Pretrade:** cash/position/reservations, account exposure, per-symbol cap, trade calendar, stop plan, price limit, spread, data freshness.
- **Continuous:** 계좌 PnL, realized + unrealized loss, market/FX stale, unsettled state, active orders.
- **Posttrade:** Fill accounting, fee, plan 대비 실제 체결, reconciliation, incident reports.

우선순위: SYSTEM_HARD > ACCOUNT > MARKET_INSTRUMENT > STRATEGY_BUDGET > MODEL_SUGGESTION.

상태: NORMAL / REDUCED / PAUSED / HALTED. Halt는 신규 위험 증가 금지와 복구 절차를 뜻하며 반드시 자동 전량시장가 청산을 의미하지 않는다.

명령 분리: PauseEntries, CancelPendingOrders, ReduceExposure, FlattenPositions. 장비/네트워크 장애 시 청산 명령 자체가 실패할 가능성도 기록한다.

## 5. 자금·수량 모델
- 계좌 통화별 settled / unsettled / reserved / available / fees / tax.
- 예상 최악 체결가격과 비용으로 현금 예약, fill에 비례해 예약 조정, 취소 확정 시 잔여 예약 해제.
- Position: instrument, long_qty, average_cost(or FIFO policy after ADR), realized/unrealized pnl, allocated strategies.
- FX 원화 환산은 valuation 이벤트로 표시; 현지통화 실제 주문 가능 금액은 별개.
- 포지션은 broker filled quantity와 일치해야 하며, 불일치시 신규 주문 정지.

초기 검증용 파라미터(최적값 아님):
- trade risk budget = account equity 0.25%
- new-entry daily loss stop = -1%
- per-symbol equity exposure max = 10%
- aggregate equity exposure max = 30%
- max positions = 3
- long-only, no margin/leverage, regular session preferred
- live_enabled = false

Trade qty = floor-to-lot(min(risk_cash/max(entry-stop_distance, valid_tick), symbol_cap, available_cash_cap, venue_limit)).
Stop 주문이 계획가격에 체결될 것이라 가정하지 않는다.

## 6. 장애·복구 매트릭스

| 사례 | 기대 동작 |
| --- | --- |
| 동일 체결 중복 수신 | execution id / 누적체결 기준 한 번만 장부 반영 |
| 부분체결 후 취소 | 체결부분 보유, 미체결 주문/예약만 해제 |
| REST timeout | UNKNOWN → 외부 조회 → 대조. 무분별한 재시도 금지 |
| WebSocket gap | stale 처리 및 재동기화. 미검증 상태 신규 매매 차단 |
| 서버 재시작 | checkpoint+event journal replay 후 외부 주문/계좌와 대조 |
| 현금 예약 경합 | single-writer 및 중복 위험심사 방지 |
| 외부 잔고 불일치 | HALTED, 외부 원본 기록, 운영자 조사 |
| 급격한 변동성/스프레드 확대 | 가격 허용 범위 검사 및 신규 주문 거절 |
| API 인증 만료/IP 제한 | 안전 중지, 토큰/네트워크 재인증, 알림 |

## 7. E3 acceptance tests
- 같은 intent 3회 처리 = 한 번의 유효 주문 의도.
- 10주 매수 주문 → 4주 부분체결, 6주 취소 → 4주 보유, 예약금 잔여 0.
- 동일 Fill 재전송 5회에도 1회만 반영.
- USD 현금은 명시적 환전 없이 KRW로 합산 소비할 수 없음.
- 다중 전략이 같은 종목에 노출을 요청해도 종목/계좌 최대한도 준수.
- UNKNOWN 주문이 하나 있으면 신규 위험 증가 주문 거절.
- 부분 체결, 장애, 재기동, 시세 결측 테스트에서 불변식 유지.

**연동 계약 세부는 INTEGRATIONS.md, 백테스트 체결 가정은 VALIDATION.md 참조.**
