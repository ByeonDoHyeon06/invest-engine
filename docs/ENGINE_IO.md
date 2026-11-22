# Engine I/O Contract — 외부·내부 입출력 명세

**Status:** E3 simulation input Python SDK + `e3-sim-v1` strict OrderIntent JSON parser implemented in PR #17. **Run API, Prediction API, trade performance report and broker/live transport remain design only.**  
**Owner:** Issue #4 + #64 · **Scope:** 실제 E1/E5/E6 계약과 과거 wire 스케치를 구분. 실제 증권사 주문 실행은 엔진 외부.

**Extension plan:** [E6.7 Unified SDK](E6_7_UNIFIED_SDK.md) / [ADR-0034](adr/0034-unified-sdk.md) defines the user-approved, neutral and inert `Engine()` constructor with operation-level capabilities and a proposed shared normalized Python/CLI orchestration contract. See [normative API examples](E6_7_SDK_EXAMPLES.md); changes require explicit user approval. Existing E5 `run_experiment` and CLI are implemented offline; newer unified API examples remain illustrative. No change to wire contracts or execution permissions in planning phase.

## CURRENT contract kernel — E1 ↔ E5 ↔ E6 (2026-11-22)

**우선 이 절을 기준으로 구현 상태를 판단합니다.** 아래의 오래된 `RunRequest/RunResult` 예제·`Live` wire 구상은 설계 이력이며 현재 실행 API가 아닙니다. E6.7 통합 [공개 SDK 문법](E6_7_UNIFIED_SDK.md)과 실제 [E5 CLI](E5_EXPERIMENT.md)는 구분해야 합니다.

### 실제 구현된 경계 (AS-IS)

| 계층 | 현재 타입·함수 | 보증/한계 |
|---|---|---|
| E1 불변 데이터셋 | `data.datasets.DatasetSpec`, `DatasetManifest`, `write_dataset/read_dataset` | DatasetManifest와 raw/normalized Parquet 해시·라이선스·수정 정책을 검증. **Normalized Parquet**는 E5 JSONL이 아님 |
| E2 이벤트 | `domain.events.EventEnvelope`, `core.runtime.EventRuntime` | UTC 이벤트/가용/수신 시점, 실행 전 최종화, **전역 연속 ordinal은 single writer가 부여해야 함** |
| E3 주문/계좌 | `trading.models.OrderIntent`, `trading.ledger.TradingState`, `trading.runtime.TradingRuntime` | **가상** 주문/체결/잔고, 실제 브로커 권한 없음 |
| E4 전략 | `strategies.contracts.StrategyManifest/Strategy`, `strategies.runtime.StrategyRunner` | 고유 ID/버전/요구 데이터·상태 스냅샷, 반복 실행마다 새 전략 인스턴스 |
| E5 과거 연구 | `research.experiment.run_experiment`(`e5-research-v1` JSON), `HistoricalBacktest.run(events)` | 별도 **canonical event JSONL**의 SHA-256을 검증하고 E5 모델/보고서로 실행. `BacktestReport`/manifest는 구현됨 |
| E6 연구 계획 | `research.pipeline.PipelineSpec`, `prepare_pipeline`, `run_development`, `PipelineReview` | 통제된 개발 후보/등록/저널·fold·holdout 규칙. 외부 실행/자동 승격 없음 |

### 이번 정리에서 추가한 최초의 공통 값 계약 (IMPLEMENTED helper only)

`invest_engine.contracts.source.HistoricalSourceIdentity`는 **인터넷·계좌·실행·파일 I/O 없는** 불변 식별 타입입니다. `from_e1_manifest(manifest)`는 E1 normalized Parquet의 정체성과 해시를, `from_e5_dataset(config["dataset"])`는 E5 canonical JSONL의 정체성과 해시를 **서로 다른 `format` 값으로** 보존하고, 공통 버전/공급자/라이선스/원본 해시/거래량 단위로 안정적인 `digest`를 계산합니다.

- **해시 종류가 다릅니다:** E1 `normalized_sha256`는 normalized Parquet 바이트 해시, E5 `dataset.sha256`은 JSONL 파일 바이트 해시입니다. 둘을 내용/시점상 동일한 데이터라고 간주하지 않습니다. 새로운 source digest가 기존 E5 run/config/artifact 해시를 대체하지도 않습니다.
- 단순 값 계약은 **참조 확인용**이지 E1 Parquet→E5 JSONL 변환기, SDK `sources.local()`, 시장 데이터 다운로드, 실시간 Session, 실제 주문 API가 **아닙니다**. 두 데이터를 실제로 연결하려면 별도 검증된 변환·정규화 어댑터와 golden parity가 필요합니다.
- `volume_unit`, `adjustment`, `completeness`, `calendar_version` 등 누락된 실증 근거를 생성하지 않습니다. 알려지지 않은 경우 `UNKNOWN/UNDECLARED`로 남기며, 경제적 사용 가능 여부는 기존 E5 차단 조건과 이후 구현할 capability gate가 결정합니다.
- JSON/CLI에 저장 가능한 값과 Python 전략/캘린더/플러그인 런타임 객체를 나눕니다. 영속 스펙에는 버전된 참조만, 실제 Python 객체는 별도 바인딩/팩토리로 해결해야 하며 전략 재사용 상태 누출은 금지합니다.

### 통일을 완료하기 위한 후속 수락 기준 (NOT YET IMPLEMENTED)

1. E1 `DatasetManifest`의 실제 raw/normalized 파일을 검증하여 canonical E5 events로 변환하고 원본 event identity, provenance, license, PIT/시점, volume 단위, 초과·부족 이벤트를 감사하는 typed adapter. **서로 다른 포맷/해시를 묵시적으로 동일시 금지**.
2. Python과 CLI가 같은 immutable `RunSpecV1` 값·defaults·economics digest를 생성하되, stateful `StrategyFactory`, calendar, artifact storage 등은 버전된 `RuntimeBindings`로 분리하고 미등록 항목을 명시적으로 거부.
3. 새 진입점 `Engine().simulation(...).historical()`은 **기존 E5 HistoricalBacktest** 경로를 그대로 호출하며 결정/체결/원장·비용/PnL/원본 증거를 fixture 단위로 대조. 기존 Python/CLI는 변경 없이 작동해야 함.
4. 결과 대수: `configuration syntax error → exception`; 지원 불가/데이터 부재 → `Blocked`; 시작된 실행 → `Completed/Blocked/Failed`; 정상 무거래는 `NO_TRADE`. 코드와 상태 우선순위를 단일 결과 모델로 정한 뒤 승인.
5. E7는 관측 이벤트의 공급자별 원본 순번과 엔진 전역 `ingest_ordinal` 부여 책임을 **하나의 ingress owner**에 집중. duplicate retry/충돌/gap/warmup cursor를 분리 검증. provider가 제공하지 않은 과거 `available_at`을 합성하지 않음.
6. 위 다섯 가지를 E6.7a의 테스트 가능 목록으로 관리하며 [Issue #64](https://github.com/ByeonDoHyeon06/invest-engine/issues/64) 및 [Issue #59](https://github.com/ByeonDoHyeon06/invest-engine/issues/59)와 연결. SDK의 편리한 문법이 **근거 없는 내부 기능 통합**을 의미하지 않게 함.

### 실험 산출물 경계

E5 `run_experiment()`는 `report.json`, `decisions/fills/equity.jsonl`, `audit.json`, `manifest.json`와 artifact SHA-256을 제공합니다. 공개·재배포 가능한 **집계 기록**은 [evidence](../evidence/README.md)와 `records/`, 개인/라이선스/민감한 상세 추적은 비공개 보존 도구 `scripts/preserve_run_evidence.py`로 분리합니다. 전체 연구 데이터를 공개 저장소에 커밋하지 않습니다.

---

## 0. 빠른 결론

엔진은 "무조건 매수/매도 추천" API가 아니다. 외부에 노출할 세 개의 경계를 구분한다.

1. **Run API (orchestration)**: 데이터셋·전략·자금·위험·체결모델 등 실행 계획 → 실행 ID/상태/결과 보고.
2. **Event/Command API (runtime)**: 타입이 확정된 시장·계좌·주문 이벤트와 명시적인 명령 → 상태 전이/결정/Command. 이 계층에 특정 timeframe 강제 없음.
3. **Prediction/Research API (later)**: 시점 정합 FeatureSet + 예측목표/모델 버전 → 점수/확률·불확실성·근거와 Abstain. 이 출력은 **주문이 아니다**.

**내부 순수 코어의 계약:**

    transition(State, DomainEvent, VersionedConfig)
      -> Transition(new_state, outcomes, commands)

코어에는 DB, 네트워크, Toss SDK, 벽시계, 학습모델 호출이 없다. 외부 I/O shell이 Command를 처리하고 그 결과를 다음 DomainEvent로 환류한다.

**현재 실제 코드:** E0/E1 market EventEnvelope, E2 observation runtime/journal, E3 **별도 버전 네임스페이스의 simulated TradingEvent / RiskDecision / Portfolio ledger**와 `decode_order_intent`. 아직 미구현: Run API, 전략/시장 기반 통합 실행, Prediction API, 수익률 보고/실거래. **아래 RunRequest/RunResult JSON과 RiskDecision JSON은 목표 wire contract 초안**이고 현재 CLI에서 실행되지 않는다.

## 1. 공통 직렬화·버전 규칙 (제안)

- JSON: snake_case, 명시적인 schema_version, unknown fields는 기본 거부(추후 version migration).
- 돈/가격/수량/수익률: JSON **Decimal 문자열** (예: "7000", "0.0025"). Float 사용 금지. 계산 중 소수점 정밀도와 실제 호가·현금 정산 반올림 정책은 **E3 별도 ADR**.
- Time: timezone-aware RFC3339 UTC ("2026-11-16T00:00:00Z"); 영업 세션은 거래소 지역 시간대로 계산. Interval: ISO8601 duration "PT1M", "PT30M"; 원자 입력은 type discriminator로 구분.
- Instrument: (market, venue, identifier, symbol, currency), symbol만 전역 키로 사용 금지.
- 모든 의사결정은 source event IDs, source code/config/data hash, as_of·available_at, reason_codes와 연결.
- Result의 상태: OK, NO_ACTION, REJECTED, DATA_UNAVAILABLE, UNSUPPORTED, HALTED, FAILED. 에러 메시지는 human-readable; 프로그램 분기는 reason_code로.
- Broker의 ACCEPTED는 체결이 아니다; 체결 수량/현금·포지션 갱신은 Fill에서만 발생.
- 실제 구현에서는 E0의 EventEnvelope wire/codec와 호환되는 버전별 decoder를 두고, 주문 DomainEvent를 **별도 namespace/타입**으로 추가한다. 기존 market.codec를 무증거로 확장했다고 주장하지 않는다.

## 2. RunRequest / RunResult (E5 CLI/SDK부터)

**입력 계획의 JSON 예시 — 설계 샘플, 실제 작동하지 않음:**

    {
      "schema_version": "0.1-draft",
      "run_id": "research-kr-orb-001",
      "mode": "BACKTEST",
      "dataset": {
        "dataset_id": "kr-equity-example",
        "sha256": "<verified-dataset-hash>",
        "license_ref": "synthetic-fixture"
      },
      "window": {
        "start": "2025-01-02T00:00:00Z",
        "end": "2025-03-28T06:00:00Z"
      },
      "universe": [
        {"market":"KR","venue":"KRX","identifier":"KR7005930003",
         "symbol":"005930","currency":"KRW"}
      ],
      "requirements": [
        {"event_type":"market.bar","interval":"PT1M","warmup":30}
      ],
      "strategy": {
        "id":"orb-long","version":"1.0.0",
        "parameters":{"opening_range":"PT5M"}
      },
      "opening_portfolio": {
        "base_currency":"KRW",
        "cash":[{"currency":"KRW","amount":"1000000"}]
      },
      "risk_policy_ref":"research-risk-v1",
      "execution": {
        "broker":"SIMULATED",
        "fill_model":"bar-conservative-v1",
        "fees_ref":"synthetic-fees-v1"
      },
      "seed":42
    }

위에서 "PT1M"은 ORB 전략의 요구 데이터일 뿐 엔진 기본 단위가 아니다. dataset_sha256/fees 등은 반드시 유효한 리소스 식별자로 제공; 예시 문자열을 실제 값으로 사용하지 않는다.

**출력 RunResult 설계 샘플:**

    {
      "schema_version":"0.1-draft",
      "run_id":"research-kr-orb-001",
      "status":"COMPLETED",
      "code_sha":"<code-sha>",
      "dataset_sha256":"<verified-dataset-hash>",
      "config_sha256":"<config-hash>",
      "event_count":10000,
      "summary":{
        "trade_count":0,
        "net_pnl":{"currency":"KRW","amount":"0"},
        "max_drawdown":"0"
      },
      "artifacts":{
        "decisions":"artifacts/research-kr-orb-001/decisions.jsonl",
        "orders":"artifacts/research-kr-orb-001/orders.jsonl",
        "fills":"artifacts/research-kr-orb-001/fills.jsonl",
        "equity":"artifacts/research-kr-orb-001/equity.parquet",
        "manifest":"artifacts/research-kr-orb-001/manifest.json"
      }
    }

숫자는 형식을 보여주는 가상 값이며 실제 수익/전략 성과가 아니다. 원시 시세를 RunResult에 인라인으로 넣지 않고 데이터 라이선스 및 artifact store 계약을 따른다.

CLI 후보:
- invest-engine run --config configs/research/orb.yaml
- invest-engine inspect --run-id research-kr-orb-001
- invest-engine explain --decision-id decision-0001

위 세 명령은 아직 구현하지 않았다. 모드 BACKTEST/PAPER/LIVE는 같은 코어를 사용하지만 DataProvider/ExecutionAdapter 권한과 배포 게이트는 별개다. LIVE는 초기 wire contract에서 생성 금지.

## 3. Runtime 입력 (E3부터)

### 3.1 DomainEvent (사실)
- Market: E0 구현된 market.trade, market.quote, market.order_book_snapshot, market.bar, market.status.
- Portfolio: account.opened, account.balance_snapshot, account.fx_converted, account.corporate_action.
- Execution: order.submitted, order.accepted, order.rejected, order.unknown, order.cancel_requested, order.canceled, fill.recorded, broker.reconciled.
- Safety: risk.policy_changed (승인된 configuration event만), risk.halted, feed.unsynced.

단일 Replay Journal의 이벤트는 영속 ingest_ordinal 순서로 재생. Data availability guard는 실제 수신 시각과 공개 시각을 모두 고려하며, 주문 이벤트의 broker_clock과 recorded_at도 기록한다. Market-only EventEnvelope와 Order DomainEvent가 하나의 envelope 인터페이스를 공유하는 방법은 E3 migration 테스트로 확정.

### 3.2 Command (요청)
- ProposeOrderIntent (E3에서는 **테스트 fixture**가 생성; E4부터 전략/Allocator가 생성)
- CancelOrder / ReconcileBroker / PauseNewEntries / ResumeAfterReview / RequestSnapshot
- Command에는 command_id(멱등성), requested_at, actor/authority, correlation_id, expected_state_version을 둔다. 신호 제안과 브로커 제출 명령은 별개의 타입.
- Command는 검증 전 상태 변경을 확정하지 않으며, 리스크 사전 검사를 반드시 통과해야 한다.

### 3.3 E3 입력/출력 예시: 주문 전 위험 심사

**Synthetic OrderIntent (KRW, 실제 계좌 아님):** 아래 JSON은 E3의 `decode_order_intent`에 입력 가능한 형태이며 실제 거래 명령이 아니다.

    {
      "schema_version":"0.1-draft",
      "command_id":"cmd-0001",
      "kind":"PROPOSE_ORDER_INTENT",
      "account_id":"sim-account-1",
      "strategy_ref":"synthetic-fixture",
      "instrument":{"market":"KR","venue":"KRX",
                    "identifier":"KR7005930003","symbol":"005930","currency":"KRW"},
      "side":"BUY",
      "order_type":"LIMIT",
      "quantity":"10",
      "limit_price":{"currency":"KRW","amount":"7000"},
      "time_in_force":"DAY",
      "stop_plan":{"trigger_price":{"currency":"KRW","amount":"6800"},
                   "reason":"SYNTHETIC_STOP_FOR_TEST"},
      "requested_at":"2026-11-16T01:00:00Z",
      "correlation_id":"case-e3-01"
    }

**RiskDecision (성공 예시):**

    {
      "schema_version":"0.1-draft",
      "decision_id":"risk-0001",
      "intent_id":"cmd-0001",
      "decision":"APPROVED",
      "reason_codes":[],
      "approved_quantity":"10",
      "reservation":{
        "currency":"KRW",
        "notional":"70000",
        "estimated_fees":"70",
        "total":"70070"
      },
      "state_version":12,
      "commands":[{"kind":"ENQUEUE_SIMULATED_ORDER","intent_id":"cmd-0001"}]
    }

위의 수수료 70 KRW는 **합성 테스트용 임의 정책 0.1%**를 적용한 예시이며 토스증권 실제 수수료와 무관하다. 현금/비중/구매력 정책을 모두 통과했다는 가정의 샘플. 명시적 승인 없이 시스템이 실제 브로커에 주문하지 않는다.

**NO_ACTION/REJECTED도 정상적인 output:**

    {
      "schema_version":"0.1-draft",
      "decision":"REJECTED",
      "intent_id":"cmd-0002",
      "reason_codes":["INSUFFICIENT_BUYING_POWER"],
      "approved_quantity":"0",
      "commands":[]
    }

### 3.4 주문/체결 이후의 Output
- DomainEvent: ORDER_ACCEPTED, PARTIAL_FILL, ORDER_CANCELED, ORDER_UNKNOWN 등 전이 이벤트.
- Fill: immutable execution_id, order_id, executed_qty, executed_price, fee, trade_currency, effective_at.
- PortfolioSnapshot: cash_by_currency(settled, unsettled, reserved, available), positions, exposure, valuation_as_of, FX provenance.
- DecisionTrace: raw event IDs → Feature snapshot → strategy signal (E4) → allocator → risk decision → outbox → simulated/live broker result → fill.
- EventOutput은 append-only 기록이고 외부에 반환되는 Summary는 스냅샷. 상태를 임의로 수정한 JSON blob을 output으로 취급하지 않는다.

## 4. E3의 최소 기능 경계 (수익 예측 아님)

E3는 ML/전략/백테스트 결과를 만들지 않는다. 입력 fixture와 이벤트로 주문 시뮬레이션 및 장부를 검증한다.

**필수 시나리오:**
- 시작현금 1,000,000 KRW / 합성 수수료 0.1% / 매수 지정가 7,000 KRW × 10주.
- 예상 현금 예약: 70,070 KRW.
- 가상 4주 체결(28,000 KRW + 수수료 28 KRW), 잔여 6주 취소.
- 종료 결과: 포지션 4주, 현금 971,972 KRW, 예약 현금 0 KRW.
- 동일 Fill 5회 수신해도 포지션 4주, 28 KRW 수수료 한 번만 반영.
- 취소 확인 전 미체결 6주 예약금은 사용 가능하지 않음.
- UNKNOWN 접수 상태에서는 신규 위험 증가 주문 차단, 외부 확인 없이 재전송 금지.
- KRW 현금과 USD 현금 자동 합산/소비 금지.

**RiskEngine**은 input의 proposed stop/risk budget이 없는 경우 정책에 따라 거절할 수 있다. 이 가상 장부 시나리오는 거래 허용 규칙을 고정한 합성 fixture이며 영업상 안전설정의 권장값이 아니다.

## 5. E3에서 확정할 기술 계약 및 결정 항목

- **E3-A:** Money/Price/Quantity 반올림·최소 호가단위·수량단위·통화별 settlement precision; 임의 Decimal context/truncate 금지.
- **E3-B:** DomainEvent 확장(계좌/주문/체결) 및 E0/E2 codec/journal version migration.
- **E3-C:** OrderIntent/RiskDecision/Snapshot/Fill 모델, Order state machine, 정확한 reservation accounting.
- **E3-D:** 단일 writer atomic event append + outbox + ledger updates와 restart semantics.
- **E3-E:** Simulated broker, 부분체결/취소/중복/UNKNOWN/계좌불일치 장애 테스트.
- **E3-F:** API contract fixtures, deterministic state+decision trace hash, 문서/CI.

각 단계는 별도 PR 크기로 나누고 실제 구현·CI 근거 없이는 ROADMAP 체크박스를 완료 처리하지 않는다.

## 6. "지원하지 않는 입력"의 의미
- 30m bar를 넣고 1m tick을 요구 → UNSUPPORTED.
- 미확정 바, 지연·손상된 호가 → DATA_UNAVAILABLE/NO_ACTION.
- 예정 공시를 이미 확정된 결과로 사용하려고 함 → PIT_ERROR.
- 주문 불명확/계좌 동기화 불일치 → HALTED.
- 정상적인 데이터에도 아무 전략 신호가 없으면 NO_ACTION.
- 모델 점수가 높더라도 위험 한도 초과 → REJECTED.

정상 응답에는 거래 안 함/중단/불확실성의 이유가 반드시 남아야 한다.

## 7. 호환성 정책
- Python Protocol/dataclass가 우선 **코어 내부 계약**, 위 JSON은 외부 boundary/CLI 아티팩트의 **제안**.
- 스키마 마이그레이션을 통해 과거 Replay/SQLite journal 파일을 읽거나 명시적으로 오류 처리해야 한다.
- 테스트용 fixture는 합성 값만 사용하고 시세·계좌·API 키 공개 금지.
- 구현 시 핵심 input/output 예시는 schema golden fixtures로 복제해 CI 검증.

## E3 실제 SDK 경계 (PR #17)

- 지원: Python `TradingRuntime.submit(OrderIntent)` → `SubmitOutcome(RiskDecision, SimulatedSubmitCommand[])`. 주문 확인/체결/취소는 **직접 호출한 합성 이벤트**로만 처리.
- 지원: JSON 명령 `schema_version="e3-sim-v1"` + `kind="PROPOSE_ORDER_INTENT"` strict parser(`invest_engine.trading.wire.decode_order_intent`). 허용하지 않은 필드, float, 비UTC timestamp, 통화불일치, LIVE mode 요청 거부.
- 지원: immutable `TradingState` 현금(settled/reserved/unsettled), 주문·부분체결·포지션·realized PnL, 이벤트 digest. `SQLiteTradingJournal`에 E2의 `events` 테이블과 충돌하지 않는 `trading_events`/outbox 버전 테이블 사용.
- 실제 Python 사용 예시: [E3_SIMULATION.md](E3_SIMULATION.md). 입력 예제: [examples/e3_simulated_order.py](../examples/e3_simulated_order.py).
- 여전히 초안: `RunRequest/RunResult`, `PredictionResult`, 자동 시장/실시간 주문 데이터 연결, 계좌·위험 통합 마크 평가.
