# 도메인·시간·데이터 계약

**상태:** E0에서 실제 타입/테스트로 고정할 설계 계약. 변경 시 schema_version과 ADR 갱신.

## 1. 원시 타입
- InstrumentId: market(KR/US), venue, stable instrument identifier, symbol history, asset class, trade currency. Ticker만 전역 키로 쓰지 않음.
- Money: Decimal(value, ISO currency); Price: Decimal(value, quote currency); Quantity: Decimal(value, valid lot rules).
- InstrumentSpecification: tick size, lot size, session, tradability, valid_from/until. 과거 종목 정의를 PIT로 조회.
- FXRate: base/quote/rate/effective_at/available_at/provider. 실제 보유 현금과 평가 환산을 분리.
- UTC aware datetime 내부 표준. 달력/세션은 거래소 로컬 타임존으로 계산.

## 2. 공통 EventEnvelope

    EventEnvelope[T]:
      event_id: stable unique identifier
      schema_version: integer
      event_type: tagged union discriminator
      source: source name + adapter version
      instrument_id: optional
      event_time: datetime UTC (시장에서 사건 발생)
      available_at: datetime UTC (의사결정에 정보 이용 가능)
      received_at: datetime UTC (엔진 실수신 또는 replay 가정)
      source_sequence: optional
      ingest_ordinal: journal index
      correlation_id / causation_id: optional
      quality_flags: list
      payload: T

- decision_clock=t에서는 available_at <= t만 조회 가능.
- 기존에 발표된 지표의 revision이나 늦게 수신된 데이터는 소급 이용 불가.
- raw ingestion와 replay 정렬은 다른 책임. Replay는 영속 저장된 순서를 그대로 적용.
- timestamp가 같을 때 ingest_ordinal을 최종 tie-breaker로 사용하는 결정적 정렬 정책을 버전화.

## 3. 이벤트 종류

| 타입 | 최소 데이터 | 주의점 |
| --- | --- | --- |
| TradeTick | price, qty, trade timestamp, trade id(있으면) | 체결가≠최우선 호가 |
| QuoteTick | bid/ask price/size, quote time | 출처별 거래소 범위 |
| OrderBookSnapshot/Delta | venue, levels, seq | gap 발생하면 delta 적용 중지 |
| Bar | start/end, OHLCV, interval, finalized | [start,end)·세션 기준 anchor |
| MarketStatus | session, halt reason, calendar version | 데이터 존재≠거래 가능 |
| FundamentalFact | issuer, period, metric, filed_at, revision, available_at | 분기말과 공개일 분리 |
| CorporateEvent | type, announcement, effective date | 분할·배당·증자 처리 |
| MacroObservation | series, reference period, released_at, vintage | 수정된 과거값 누출 주의 |
| DocumentEvent | source, published_at, parsed output version | LLM 출력 검증 필수 |

주문/체결/계좌/위험 이벤트는 시장 이벤트와 다른 타입 네임스페이스로 관리하며 같은 Envelope을 사용.

## 4. 시세 해상도
- 엔진에는 기본 시간봉이 없다. Strategy/DataRequirements가 입력 타입과 주기(예: Tick, 1m, 30m)를 명시.
- Tick→1m/5m/30m 집계 가능. 1m→30m 가능. 30m→1m, OHLCV→원본 Tick/Quote 복원 불가.
- 시간봉은 완성 이벤트 이후만 시그널에 노출. 완료 전 봉 값은 명시적 live partial 타입으로 분리.
- 거래량 0/결측/휴장/거래정지/조기종료를 구분한다. 임의 앞채움/보간은 옵션으로 명시.
- 늦게 도착한 Tick은 revision/quality event로 기록하고 실행된 주문을 과거로 되돌리지 않는다.
- Tick/Volume/Dollar Bar aggregation은 별도 플러그인.

## 5. 전략과 주문 계약

StrategyManifest:
    id, version, code artifact hash, supported markets,
    requirements[], features[], warmup, params, risk class

StrategySignal:
    signal_id, strategy/version, instrument,
    desired_direction / target_exposure,
    entry/stop hypothesis, as_of, expires_at,
    reason codes, feature_snapshot_id

OrderIntent:
    intent_id, account, instrument, side, quantity,
    order_type, limit/stop when relevant, time_in_force,
    allocation refs, pretrade risk snapshot, created_at

BrokerOrder:
    order_id, broker_order_id, client_order_id,
    requested_qty, cumulative_filled, remaining,
    state, timestamps, version

ExecutionFill:
    immutable execution identifier, order_id,
    price, qty, fees/tax, settlement, currency

StrategySignal은 제안일 뿐 실행 명령이 아니다. OrderIntent는 Allocator·Risk 통과 후에만 생긴다.
NoAction/UnsupportedData/StaleData는 정상적인 결과 타입이며 데이터가 없으면 신호 생성하지 않음.

## 6. 포트폴리오
- KRW와 USD는 서로 다른 현금 ledger: settled/unsettled/reserved/available.
- 포지션은 체결 이벤트로만 증가·감소하며 주문 접수만으로 수정되지 않음.
- 평가 시 FX 시점과 환산 규칙 기록; 거래가능 금액은 현지통화와 결제 상태에 맞춰 검증.
- 수수료/세금/기업행동/매수예약금/매도예약주식 고려. 평균 단가 vs FIFO는 실제 연결 이전 별도 ADR 확정.

## 7. 데이터 Manifest
필수 메타데이터: provider, license, coverage, record type, timezone, calendar version, adjustment mode, retrieval date, published vintage, schema version, checksum. 실험마다 git SHA, config, dataset hash, strategy/model version, seed, fill model 기록.

## 8. E0/E1 검증
- naive datetime, 음수수량, 유효하지 않은 호가/가격, 이벤트 ID 중복, market 누락 거부
- 시점 밖 Feature 조회 실패
- 서로 다른 시장 종목코드가 충돌하지 않음
- 임의 5분/30분봉 집계의 합계/고저가 불변식
- 비활성 세션 Bar와 시간대/DST 테스트
- 같은 입력·정렬 정책·버전에서 동일 상태 해시
