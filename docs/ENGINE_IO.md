# Engine I/O Contract — 외부·내부 입출력 명세

**Status (2026-11-22):** E3 simulation OrderIntent parser and **E5 offline `run_experiment`/BacktestReport/CLI are implemented**; E6 development pipeline partly implemented. **Unified E6.7 SDK, prediction and broker/Live transport remain unimplemented.** Historical wire sketches below are not executable E5 configs.  
**Owner:** Issue #4 + #64 · **Scope:** 실제 E1/E5/E6 계약과 과거 wire 스케치를 구분. 실제 증권사 주문 실행은 엔진 외부.

**Extension plan:** [E6.7 Unified SDK](E6_7_UNIFIED_SDK.md) / [ADR-0034](adr/0034-unified-sdk.md) defines the user-approved, neutral and inert `Engine()` constructor with operation-level capabilities and a proposed shared normalized Python/CLI orchestration contract. See [normative API examples](E6_7_SDK_EXAMPLES.md); changes require explicit user approval. Existing E5 `run_experiment` and CLI are implemented offline; newer unified API examples remain illustrative. No change to wire contracts or execution permissions in planning phase.

## Pre-SDK Contract Reset — SDK 구현 전 내부 계약 전면 통일 계획 (PLANNED)

> **상태: 계획만 승인, 아직 리팩터링/삭제/마이그레이션 실행하지 않음.** [Issue #64](https://github.com/ByeonDoHyeon06/invest-engine/issues/64)에서 이 작업을 추적한다. [Issue #59](https://github.com/ByeonDoHyeon06/invest-engine/issues/59)의 E6.7 공개 SDK **구현보다 먼저 완료해야 할 선행 게이트**다. 이 절은 아래의 과거 “하위 호환 유지” 가정보다 우선한다.

### 1. 설계 원칙과 범위

- 프로젝트의 **미배포 내부 API, E1/E5/E6 개별 RunSpec/JSON 설정, 중복 데이터 및 실행 타입에 대한 하위 호환성 보장은 요구하지 않는다.** 별도 데이터/스펙/실행 경로를 위한 호환 래퍼·구버전 파서·이중 네임스페이스는 통합 후 제거한다. 이 변경은 미래 작업의 승인된 목표이며, **이번 PR에서 코드를 삭제하지는 않는다.**
- 단, **과거 연구 기록과 실행 근거는 불변 아카이브로 보존**한다. 옛 설정 파일/리포트를 새 형식으로 마이그레이션할 필요는 없지만, 당시 커밋/버전·데이터 원천·라이선스·해시·비용 정책·실험 결과를 추적할 수 있어야 한다. 신규 엔진의 결과 해시는 변경 가능하되 그 변경을 명시한다.
- **경제적·인과적 안전성은 하위 호환보다 우선**한다. 동일한 유효 입력/가정/시드로 얻은 결정·가상 체결·현금·포지션·수수료·PnL·위험 차단은 재현·대조해야 한다. 버그 수정을 위해 결과가 바뀐다면 변경 이유와 영향을 golden fixture에 기록하고 검증한다. PIT, 기업행동, 통화, 캘린더, 데이터 권리/불완전성, 연구 홀드아웃 및 리스크 게이트는 축소하지 않는다.
- 최종 구조는 **단일 정규화 이벤트/실행 계약 + 동작별 명시적 capability**를 갖춘다. Historical/Paper는 가상 계좌·가상 체결, Evaluate/Session은 제안만 생성하며 실제 주문·브로커 계좌 권위는 외부 실행 Host로 분리한다.
- #70에서 시작한 `HistoricalSourceIdentity`는 **임시 출처 식별용 값 타입**으로 취급한다. 향후 단일 Source/RunSpec 설계에서 필요 없거나 중복된다면 교체·삭제한다. 기존 타입 유지 자체를 완료 조건으로 삼지 않는다.

### 2. 목표 내부 계약 (TO-BE)

| 계약 | 통일 목표 | 기존 분리 계약의 처리 |
|---|---|---|
| `SourceRef / SourceManifest` | E1 Parquet·E5 JSONL·향후 provider/manual 입력이 타입·권리·시간 증거·데이터 품질·포맷을 **명시**하고, 필요한 경우 검증 가능한 변환을 통과 | 포맷 추측/해시 혼용/전역 provider 우선순위/중복 소스 레지스트리 제거 |
| `CanonicalEvent` + `Ingress` | event/available/received time, source ID, event ID/sequence, calendar, finalization, duplicate/gap 규칙 및 단일 writer ordinal의 책임 고정 | E1·E5·E7별 다른 이벤트 의미·무단 timestamp 합성 제거 |
| `RunSpec` | Python과 CLI 모두 같은 **불변 직렬화 가능한 경제적 설정값** + versioned reference를 사용. operation별 capability 선언 | E5 전용 JSON 스펙, 비직렬화 Python 객체 포함 스펙 등 이중 입력 계약 제거 |
| `RuntimeBindings` | 전략 팩토리·정책·캘린더·데이터 변환·스토리지의 **실행 객체**를 RunSpec의 값/식별자와 분리 | 재사용 전략 인스턴스 누출과 숨겨진 I/O, 미등록 임의 객체 거부 |
| `TradingCore / State` | 전략→allocation→risk→(가상 주문/체결 또는 판단 제안)의 단일 흐름. 다종목 공유 계좌·자본/예약금 단일 소유 | 중복 가상 포트폴리오·위험 검사/서로 다른 주문 상태머신 제거 |
| `Outcome / Evidence` | invalid config / unsupported-or-blocked / failed / valid no-trade / completed를 분리. 결과 및 증거의 버전·해시·권한 경계 통일 | Result/Report/ResearchReview의 상충하는 상태 의미 및 암묵적 성공값 정리 |
| `ResearchPlan` | 같은 RunSpec/Core 위에서 후보·fold·저널·홀드아웃·예산만 확장 | E6의 별도 경제적 실행 경로·결과 합산 로직 제거 |

명칭은 **설계용 개념 이름**이다. 실제 모듈/클래스 경계와 타입 시그니처는 첫 설계 PR에서 확인한다. 모든 기능을 하나의 만능 클래스에 몰아넣지 않고, 공통 계약만 공유하며 operation별 책임은 분리한다.

### 3. 실행 순서 및 독립 PR 게이트 (SDK 구현 선행)

| 순서 | 작업 | 완료 조건 |
|---|---|---|
| **P0 — 병렬 작업 정리** | Codex가 진행하는 [#66](https://github.com/ByeonDoHyeon06/invest-engine/pull/66)·[#69](https://github.com/ByeonDoHyeon06/invest-engine/pull/69)의 변경·의존성 확정. #70은 문서/증거/식별 타입 변경만 유지 | 공유 계좌·다종목 계약의 기준 커밋 확보, 서로 다른 브랜치의 동일 파일 중복 수정 중단 |
| **P1 — 목표 계약 동결** | 실제 E1–E6 API/상태/데이터·해시·경제 규칙 inventory. TO-BE 타입/의존 그래프/strict Python·CLI 설정값/Source capability/Result 상태 대수 확정 | **단일 규범 계약**, 구버전 호환 정책 **없음** 명시, 기존 계약 삭제 대상 표와 테스트 계획 리뷰 |
| **P2 — 핵심 경로 교체** | E1 데이터→정규화 이벤트→E2 ingest→E4 전략 팩토리→E3 가상 risk/체결·공유 계좌→E5 historical runner를 새 계약에 맞게 리팩터링. 구형 경로를 단계적으로 삭제 | 단일·다종목 deterministic golden test, NoTrade/Block/Fail, 비용·FX·PIT·기업행동·원장·증거 보존; 모순된 결과는 원인 기록 |
| **P3 — 연구/CLI 통합** | E6 후보/Walk-forward/연구 저널/holdout이 동일 RunSpec·Core·Outcome을 사용. CLI와 Python 입력은 같은 정규화 값을 구성 | 사전 등록/홀드아웃 차단·자원 예산 유지, 동일 fixture에서 CLI/Python 경제적 결과 대조, 유령/중복 레거시 API 삭제 |
| **P4 — 통합 검증 및 제거** | 구 코드·중복 스펙/파서/어댑터/문서 정리. 전체 CI + 실패 주입/회귀/해시 변경 감사 + 실험 증거 인덱스 점검 | **한 가지 명세/한 가지 실행 경로** 검증, 참조 끊김 없음, 변경 이유가 적힌 결과 비교 리포트, 과거 evidence 기록 유지 |
| **P5 — E6.7 SDK 구현 착수** | 검증된 단일 내부 계약 위에 공개 `Engine().simulation/research/evaluate/session` facade와 23개 예제/반환 계약 구현 | P0–P4 통과 전 새 SDK facade 기능 확장 **금지**; E7 Paper/Session과 외부 E8 실거래는 별도 승인 |

### 4. 수락 기준 및 비목표

- [ ] Python/CLI로 같은 설정을 만들면 정규화 `RunSpec`, 경제적 설정·전략·비용 정책 digest가 같다. Python 실행 객체는 RuntimeBindings로 연결하고 strategy state는 run마다 격리한다.
- [ ] E1/E5 입력은 포맷/해시/권한을 구분하며 변환된 canonical tape를 검증한다. 허위 PIT·available_at·거래량·호가를 생성하지 않는다.
- [ ] 단일 종목과 #69의 다종목 공유 계좌 모두 같은 core risk/ledger/fee/fill 규칙을 사용하며, 가상 체결 없는 제안-only 경로가 구별된다.
- [ ] 원인별 ConfigurationError/Blocked/Failed/NoTrade/Completed 및 연구 holdout/실험 증거 결과가 서로 충돌하지 않고 typed fixture로 검증된다.
- [ ] 기존 내부 API와 JSON config의 사용처는 새 계약으로 직접 수정하고, **legacy wrapper / schema migration / 구버전 CI 지원은 완료 조건이 아니다.**
- [ ] 기존 데이터·실험 보고서는 **재작성하거나 삭제하지 않는다.** 새 결과와 경제적 비교가 필요하면 같은 fixture·가정으로 **재실행하고 차이/버그 수정 이유**를 기록한다.
- [ ] E7 실시간 입력/복구와 E8 외부 실주문 호스트는 계약상 확장점만 예약한다. 실시간 운영/실주문을 이번 전면 리팩터링의 범위에 넣지 않는다.

**비목표:** 이전 내부 API의 소스 호환, 과거 실험 아티팩트의 새 포맷 변환, 이미 수집하지 못한 원시 시세의 재구성, 새 전략 수익성 주장, 실제 브로커 주문. **이번 변경은 문서·이슈의 계획 반영만**이며 구현 PR을 시작하지 않는다.

---

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
3. 새 진입점 `Engine().simulation(...).historical()`은 **기존 E5 HistoricalBacktest** 경로를 그대로 호출하며 결정/체결/원장·비용/PnL/원본 증거를 fixture 단위로 대조. **이 항목은 이전 호환성 중심 설계의 기록**이며, 위 P1–P4 전면 통일 계획에서 내부 Python/CLI는 새 계약으로 동시 변경할 수 있다. 결과 동등성과 증거 감사는 유지한다.
4. 결과 대수: `configuration syntax error → exception`; 지원 불가/데이터 부재 → `Blocked`; 시작된 실행 → `Completed/Blocked/Failed`; 정상 무거래는 `NO_TRADE`. 코드와 상태 우선순위를 단일 결과 모델로 정한 뒤 승인.
5. E7는 관측 이벤트의 공급자별 원본 순번과 엔진 전역 `ingest_ordinal` 부여 책임을 **하나의 ingress owner**에 집중. duplicate retry/충돌/gap/warmup cursor를 분리 검증. provider가 제공하지 않은 과거 `available_at`을 합성하지 않음.
6. 위 다섯 가지를 **P1–P4 선행 작업의 테스트 가능 목록**으로 관리하며 [Issue #64](https://github.com/ByeonDoHyeon06/invest-engine/issues/64) 및 [Issue #59](https://github.com/ByeonDoHyeon06/invest-engine/issues/59)와 연결. SDK의 편리한 문법이 **근거 없는 내부 기능 통합**을 의미하지 않게 함.

### 실험 산출물 경계

E5 `run_experiment()`는 `report.json`, `decisions/fills/equity.jsonl`, `audit.json`, `manifest.json`와 artifact SHA-256을 제공합니다. 공개·재배포 가능한 **집계 기록**은 [evidence](../evidence/README.md)와 `records/`, 개인/라이선스/민감한 상세 추적은 비공개 보존 도구 `scripts/preserve_run_evidence.py`로 분리합니다. 전체 연구 데이터를 공개 저장소에 커밋하지 않습니다.

---

## 0. 이전 E3 wire 초안의 맥락 (역사적 설계, 현재 E5 구현을 대체하지 않음)

엔진은 "무조건 매수/매도 추천" API가 아니다. 외부에 노출할 세 개의 경계를 구분한다.

1. **Run API (orchestration)**: 데이터셋·전략·자금·위험·체결모델 등 실행 계획 → 실행 ID/상태/결과 보고.
2. **Event/Command API (runtime)**: 타입이 확정된 시장·계좌·주문 이벤트와 명시적인 명령 → 상태 전이/결정/Command. 이 계층에 특정 timeframe 강제 없음.
3. **Prediction/Research API (later)**: 시점 정합 FeatureSet + 예측목표/모델 버전 → 점수/확률·불확실성·근거와 Abstain. 이 출력은 **주문이 아니다**.

**내부 순수 코어의 계약:**

    transition(State, DomainEvent, VersionedConfig)
      -> Transition(new_state, outcomes, commands)

코어에는 DB, 네트워크, Toss SDK, 벽시계, 학습모델 호출이 없다. 외부 I/O shell이 Command를 처리하고 그 결과를 다음 DomainEvent로 환류한다.

**당시 E3 단계의 구현 상태 (역사적 기록):** E0/E1 market EventEnvelope, E2 observation runtime/journal, E3 simulated TradingEvent / RiskDecision / Portfolio ledger 및 `decode_order_intent`. **그 이후 E5 `run_experiment`와 실제 보고서/CLI가 구현되었으며** 아래 E3시점 `RunRequest/RunResult` 및 `RiskDecision` JSON 초안과 **동일한 wire API가 아닙니다**. 유효한 실행 계약은 상단 CURRENT 표와 [E5 experiment](E5_EXPERIMENT.md)를 확인하세요.

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
