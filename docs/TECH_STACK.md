# 기술 스택 및 도입 결정 — Engineering Plan

**상태:** 계획. 아래 기술이 설치되었거나 테스트되었다는 뜻은 아니다. 실제 패키지 버전은 E0 lockfile과 CI에서 고정한다.

## 1. 처음 구현하는 기술 (R0~R1)

| 영역 | 기본 선택 | 이유 |
| --- | --- | --- |
| 언어 | Python 3.12+ | 타입·async IO·퀀트 분석 생태계 |
| 패키징 | pyproject.toml, uv 후보 | 재현 가능한 의존성, 간단한 도구 |
| core type | dataclasses / enums / typing Protocol | 순수 도메인 모델, 불필요한 런타임 의존성 최소 |
| 금융 금액/수량 | Decimal, UTC-aware datetime, zoneinfo | 통화/호가 정밀도와 시간 규칙 |
| 데이터 저장 | Parquet + PyArrow, dataset manifest | columnar 저장, 실험 데이터 해시 |
| 연구 계산 | NumPy + pandas (필요 시 Polars) | 초기 지표·시계열 변환 |
| 실험 CLI | argparse 또는 Typer (E0 검토) | UI 없이 실행 가능한 작업 |
| 테스트 | pytest + Hypothesis | 상태/시간/체결 불변식의 속성 기반 검증 |
| 품질 | Ruff, mypy, GitHub Actions | lint/format/type/unit/replay CI |

**판단 기준:** E0에서는 외부 데이터·브로커 연결 없는 이벤트 재생이 최우선. 빠른 속도를 위한 C++/Rust/Redis/Kafka를 선투입하지 않음. 초저지연 요구가 측정된 후 ADR로 결정.

## 2. Data/Research 확장 (E1~E6)
- 데이터 로더/정렬: PyArrow/Parquet; 복잡한 분석쿼리는 DuckDB 후보.
- 분봉 집계: 정확한 세션 anchor, available-at, 불완전 봉 처리. 외부 pandas resample에 시장 달력 판단을 맡기지 않는다.
- Research: NumPy/pandas로 기준선 구현; 대규모 실험 병목이 생기면 Polars/Numba 등 검토.
- 자동 탐색: Optuna 후보(E6).
- ML: scikit-learn baseline, LightGBM/CatBoost/MLflow/River는 선택적(E9). 모델이 주문권한을 갖지 않음.
- 데이터 검증: 명시적 schema + integrity checks, timezone, asset/corporate-action metadata.

## 3. 실시간/브로커 (E7~E8)
- HTTP: HTTPX, WebSocket: websockets (공식 OpenAPI/AsyncAPI 스키마에서 계약 생성/검증 가능)
- 비동기 I/O: asyncio(데이터 수신과 명령 처리), Core 상태 전이는 단일 writer
- 상태 영속성: SQLite Write-Ahead Log/append journal 후 필요 시 PostgreSQL로 이전 (정확한 선택은 E7 ADR)
- 배포: Linux VPS + Docker Compose 후보(고정 IP, 비밀정보 환경, 로그/재시작).
- 알림/관측: structured logs + metrics; Prometheus/Grafana 및 Telegram은 운영 규모에서 검토.
- UI: 초기에는 제공하지 않음. 추후 FastAPI + Next.js/TS를 별도 프로젝트로 구성할 수 있음.

## 4. 가장 중요한 인터페이스
- DataProvider → MarketEvent envelopes + capabilities/quality
- FeatureProvider → Point-in-Time FeatureSnapshots
- Strategy → immutable StrategySignal, no Broker access
- RiskEngine → RiskDecision with reason codes
- BrokerProtocol → order/position/market capabilities, order-event stream
- ExecutionManager → durable outbox, state machine, reconciliation
- ResearchRuntime → Experiment/StrategyCandidate and ValidationReport

이 인터페이스가 유지되면 특정 시장 데이터/브로커/ML 구현 교체가 가능하다.

## 5. E0에서 확정해야 할 개발 도구
- [ ] 실제 Python/min supported version 및 dependency lock
- [ ] formatter/linter/type-checker 설정
- [ ] CI matrix(가능한 OS, Python), test commands
- [ ] semantic versioning 및 architecture/ADR migration process
- [ ] synthetic fixtures를 이용한 deterministic test
- [ ] security secret scan / ignore policy

**원칙:** 테스트를 실행해 확인하기 전까지 지원한다고 쓰지 않는다.
