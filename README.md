# invest-engine

**Engine first. Evidence before trading.**

국내·미국 주식 대상으로 시장 데이터, 전략, 위험관리, 주문·체결, 포트폴리오, 연구·자기개선을 분리한 독립형 적응형 트레이딩 엔진.

**현재 상태:** E0~E4 합성 엔진 검증, E5.1~E5.4 오프라인 백테스트·실험 감사 구현. E5 실데이터/PIT 기업행동·수수료/FX 검증 게이트는 미완료. **실거래 기능 없음.** 자세한 진행 현황은 [STATUS](docs/STATUS.md) 참고.

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
- **[E5.1 과거 데이터 재생 및 체결 모델](docs/E5_BACKTEST.md)**
- **[E5.2 오프라인 RunRequest/실험 CLI](docs/E5_EXPERIMENT.md)**
- **[E3 모의매매 주문·위험·포트폴리오 구현](docs/E3_SIMULATION.md)**
- **[E3.3 시세 평가·일일 손실·계좌 대조](docs/E3_MONITORING.md)**
- **[E3.4 합성 세금·매도 미결제금·정산 확인·Gate](docs/E3_SETTLEMENT.md)**
- [기술 스택/선택 근거](docs/TECH_STACK.md)
- [도메인·이벤트·시간 계약](docs/DOMAIN.md)
- [E1 데이터 수집·품질 계약](docs/DATA_INGESTION.md)
- [E1.2 거래 세션·시간봉 집계](docs/RESAMPLING.md)
- [E1.3 데이터셋·무결성·출처](docs/DATASETS.md)
- [전략·지능·연구](docs/STRATEGIES.md)
- [E4 Strategy SDK 및 ORB 가설 구현](docs/E4_STRATEGY.md)
- [위험·주문·포트폴리오](docs/RISK_EXECUTION.md)
- [백테스트·Forward·검증 게이트](docs/VALIDATION.md)
- [E5 보수적 손절·익절 체결 연구 정책](docs/E5_PROTECTION.md)
- **[E5.4 데이터 공백/무결성 감사·비용 스트레스 검증](docs/E5_ROBUSTNESS.md)**
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

[E3 상세 구현·남은 과제](docs/E3_SIMULATION.md) · [PR #17](https://github.com/ByeonDoHyeon06/invest-engine/pull/17) · [E3.2 운영 안전 PR #18](https://github.com/ByeonDoHyeon06/invest-engine/pull/18)

## E4 — Strategy SDK (검증 완료)

읽기 전용 시장 데이터 → FeatureRegistry → StrategySignal → Portfolio Allocation → **가상 주문 제안**의 독립 흐름을 추가했다. ORB는 검증되지 않은 첫 기준 가설이며, 모델이 주문을 직접 실행하지 않는다. 실제 브로커·모델 학습·과거 체결 시뮬레이터는 아직 없다.

```bash
PYTHONPATH=src python examples/e4_strategy_signals.py
python -m pytest -q tests/test_strategy_e4.py tests/test_orb_e4.py tests/test_allocation_e4.py tests/test_features_e4.py
```

[PR #21](https://github.com/ByeonDoHyeon06/invest-engine/pull/21) · [PR #22 가상 Fill 귀속](https://github.com/ByeonDoHyeon06/invest-engine/pull/22) · [E4 사양](docs/E4_STRATEGY.md)

### E4.3 전략별 가상 손익 귀속

E3의 합성 Fill을 여러 전략의 가상 포지션·취득원가·실현손익으로 귀속하고 실제 E3 합성 잔고와 수량을 감사한다. **이 장부는 아직 메모리 내 재생 가능한 연구용 계산이며**, 신호/주문/귀속 티켓의 통합 영속화와 백테스트 체결 모델은 E5 범위다. 실거래 기능은 여전히 없다.

## E5 offline research CLI (PR #23 + #24)

입력은 API 키가 아닌 자체 데이터/명시적인 거래세션/전략·위험 설정이다. `invest-engine backtest --config <run.json>`으로 `report.json`, `manifest.json`, `equity.jsonl`, `decisions.jsonl`, `fills.jsonl`을 만들 수 있다. [E5_EXPERIMENT.md](docs/E5_EXPERIMENT.md) 참조. **실행 가능한 stop/target/gap model 및 실거래는 지원하지 않는다.**

### E5.5 연구용 환율 보고
[Point-in-Time FX 연구 보고](docs/E5_FX_REPORTING.md)는 선택적 기준 통화 환산 기능입니다. 실제 환전·거래 수수료·시장별 기업행동 데이터가 검증되었다는 뜻이 아닙니다.
