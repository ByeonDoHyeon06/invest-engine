# invest-engine

**Engine first. Evidence before trading.**

국내·미국 주식 대상으로 시장 데이터, 전략, 위험관리, 주문·체결, 포트폴리오, 연구·자기개선을 분리한 독립형 적응형 트레이딩 엔진.

**현재 상태:** E0·E1·E2 완료, **E3.1 합성 주문·현금 예약·체결·저널 [PR #17](https://github.com/ByeonDoHyeon06/invest-engine/pull/17) 병합 완료**. E3 전체는 진행 중. **실거래/증권사 연동/전략 기반 거래/백테스트는 없음.** 개인용·headless·검증 우선.

## 설계 원칙
- 해상도 비종속: Tick/Quote/OrderBook/Bar/재무·공시 이벤트를 각각 정확한 타입으로 처리한다. 1분봉은 전략 설정이지 엔진 제한이 아니다.
- 브로커 비종속: 토스증권 연결은 어댑터. API 키 없이 Simulation부터 구현한다.
- 결정론적 코어: 같은 데이터·설정·버전·이벤트 순서는 같은 상태와 결과를 낸다.
- 책임 분리: 전략은 신호만 제안하며 Risk → Execution이 주문을 통제한다.
- Point-in-time: 당시 알 수 없었던 데이터, 과적합, 생존편향을 방지한다.
- 자기개선의 통제: Research가 후보를 탐색해도 운영 전략을 무승인 변경하지 않는다.
- 엔진 우선: UI/SaaS/고객 계좌 관리는 엔진 검증 이후로 미룬다.

## 프로젝트 문서 (진실 공급원)
- [현재 상태·다음 작업](docs/STATUS.md)
- [단계별 로드맵 및 완료 조건](docs/ROADMAP.md)
- [전체 아키텍처](docs/ARCHITECTURE.md)
- **[Engine 입출력 계약](docs/ENGINE_IO.md)**
- **[AI·ML 연구 목표 및 평가 계약 (E6 설계안)](docs/ML_RESEARCH.md)**
- [E2 이벤트 런타임과 복구 규칙](docs/EVENT_RUNTIME.md)
- **[E3 모의매매 주문·위험·포트폴리오 구현](docs/E3_SIMULATION.md)**
- [기술 스택/선택 근거](docs/TECH_STACK.md)
- [도메인·이벤트·시간 계약](docs/DOMAIN.md)
- [E1 데이터 수집·품질 계약](docs/DATA_INGESTION.md)
- [E1.2 거래 세션·시간봉 집계](docs/RESAMPLING.md)
- [E1.3 데이터셋·무결성·출처](docs/DATASETS.md)
- [전략·지능·연구](docs/STRATEGIES.md)
- [위험·주문·포트폴리오](docs/RISK_EXECUTION.md)
- [백테스트·Forward·검증 게이트](docs/VALIDATION.md)
- [외부 데이터·증권사 연동](docs/INTEGRATIONS.md)
- [개발·리뷰 규칙](docs/CONTRIBUTING.md)
- [ADR 인덱스](docs/adr/README.md)
- [작업 에이전트 가이드](AGENTS.md)

Roadmap은 순서와 완료 기준을, Status는 진행 상태를, ADR은 결정 근거를 기록한다. 실제 완료 여부는 테스트와 코드로 검증한다.

## 예정 순서
E0 기초 계약 → E1 데이터 → E2 이벤트 코어 → E3 모의 주문·위험·회계 → E4 전략 API/ORB → E5 백테스팅 → E6 리서치·자동 후보 평가 → E7 실시간 Paper/Shadow → E8 통제된 소액 실거래 → E9 후속 고도화.

**초기 제외:** 실제 주문, 자동 코드 수정/무검증 전략 배포, 대시보드, SaaS, HFT, 공매도·레버리지, 수익 보장.

**보안:** API key/secret/token, 계좌정보, 비공개 시세 원본은 저장소에 커밋하지 않는다. 공개/배포 권리가 있는 데이터 또는 합성 테스트 데이터만 사용한다.

## E0 — 오프라인 이벤트 검증기 (PR #11)

이 단계에는 **시장 데이터 수신·전략·백테스트·주문 기능이 없다**. 순수 합성 데이터의 이벤트 정렬·검증·결정론적 결과 해시만 제공한다.

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
ruff check .
mypy src
invest-engine replay-synthetic --count 500 --market KR
invest-engine replay-synthetic --count 1000 --market US
```

정상적인 실행에서는 거래 0건, API 호출 0건이며 JSON에 count, events_by_type, state_hash가 출력된다. 해시의 같음은 **입력 이벤트의 정합/재현성**을 의미하지 매매 수익성을 의미하지 않는다. 

[구현 PR #11](https://github.com/ByeonDoHyeon06/invest-engine/pull/11) · [E0 Epic #1](https://github.com/ByeonDoHyeon06/invest-engine/issues/1)

**E0 CI 증거:** [Actions run 43708153842](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43708153842) — Python 3.12/3.13 각각 37 tests, Ruff/mypy/secret guard 통과.

## E1 — Market data foundations (PR #12–#14)

데이터 공급자 계약, 엄격한 Tick/Quote/Bar 정규화, stale/late/중복 감지, Point-in-Time 관측 격리, 세션 기반 임의 시간봉 집계, DST/조기폐장·누락된 시간봉 검증, 원본/정규화 분리 Parquet 및 무결성/라이선스 Manifest까지 구현·검증했다.

```bash
python -m pip install -e ".[dev,data]"
ruff check .
mypy src
python -m pytest -q
```

[PR #12](https://github.com/ByeonDoHyeon06/invest-engine/pull/12) · [PR #13](https://github.com/ByeonDoHyeon06/invest-engine/pull/13) · [PR #14](https://github.com/ByeonDoHyeon06/invest-engine/pull/14) · [E1 검증 CI](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43714655109)

**주의:** E1은 데이터 기반만 제공한다. 주문/계좌/전략/실시간 트레이딩 및 수익 검증은 미구현이다. 실제 거래소 공휴일 캘린더 제공자, 라이브 watermark finalization, 시세 공급자 라이선스 검토 및 실제 시장 데이터 보정은 별도 과제로 남는다.

## E3 착수 전 I/O 설계 검토

전략/모델은 직접 주문하지 않는다. [ENGINE_IO.md](docs/ENGINE_IO.md)에 RunRequest/RunResult·DomainEvent/Command·RiskDecision·NoAction·결과 추적을, [ML_RESEARCH.md](docs/ML_RESEARCH.md)에 예측 대상·baseline·no-leakage 평가를 정리했다. **두 문서의 JSON은 아직 실행되는 API가 아닌 설계 초안**이며, E3 주문/회계 코드를 병합하기 전 버전·스키마·코어 호환성 테스트로 확정한다.

## E3 — Synthetic order / risk / ledger (PR #17)

현재 코드에 추가된 것은 **명시적 합성 주문 입력 → 사전 위험 평가 → 예약현금·예약주식 → 수동 모의 체결/취소 → 손익·저널 복구**까지의 Python SDK야. 실제 시세와 주문을 연결하는 자동 체결 전략 또는 토스증권 주문 기능은 없다.

```bash
python -m pip install -e ".[dev,data]"
python examples/e3_simulated_order.py
python -m pytest -q
```

기대 합성 출력: 10주 × 7,000 KRW 주문 70,070 KRW 예약 → 4주 체결 및 나머지 취소 후 **971,972 KRW 현금·4주 포지션·예약 0**. 수수료율 0.1%, KRW 반올림은 테스트 설정이지 실제 증권사 조건이 아니다.

[E3 상세 구현·남은 과제](docs/E3_SIMULATION.md) · [PR #17](https://github.com/ByeonDoHyeon06/invest-engine/pull/17)
