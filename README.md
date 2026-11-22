# Invest Engine

**Engine first. Evidence before trading.**

독립적인 KR/US 주식 **연구·시뮬레이션 엔진**입니다. 시장 이벤트, 시간·데이터 원천, 전략, 가상 위험·체결·원장, 반복 가능한 백테스트 및 통제된 연구 검증을 분리합니다.

> **현재 구현 상태 (2026-11-22, main):** E0–E4 코어/가상 거래 기반 및 E5/E6 오프라인 연구 기능 일부가 구현되어 있습니다. E5/G1·E6/G2 최종 승인, E6.7 통합 SDK, E7 실시간 Paper는 **미완료**입니다. 실계좌 주문/거래 API는 지원하지 않습니다. 실행 가능한 저수준 API와 **향후 E6.7 SDK 설계 예제는 별도**입니다.

## 빠른 시작 — 현재 구현된 오프라인 기능

```bash
python -m pip install -e ".[dev,data]"
python -m pytest -q
ruff check .
mypy src

# 합성 이벤트 재현성 검증
invest-engine replay-synthetic --count 500 --market KR
```

E5 실행은 `invest-engine backtest --config <E5 JSON config>`로 수행합니다. 입력은 **검증된 로컬 정규화 이벤트 JSONL과 명시적인 비용/전략/데이터 해시**를 요구합니다. 현재 실행 계약은 [E5 experiment](docs/E5_EXPERIMENT.md)를 참고하세요. 이 명령은 증권사에 주문하지 않습니다.

## 문서 위치

| 찾는 것 | 정식 위치 |
|---|---|
| 전체 문서 찾아보기 | [문서 안내](docs/README.md) |
| 현재 개발 상태 / 승인 게이트 | [STATUS](docs/STATUS.md) |
| 단계별 향후 작업 | [ROADMAP](docs/ROADMAP.md) |
| **내부 계약 / 현재 E1·E5·E6 정규화 경계** | [ENGINE_IO](docs/ENGINE_IO.md) |
| **E6.7 통합 SDK 설계 (미구현)** | [통합 설계](docs/E6_7_UNIFIED_SDK.md) · [23개 사용 예제](docs/E6_7_SDK_EXAMPLES.md) |
| **백테스트 결과·데이터 검증 기록·실험 보존 정책** | [Research evidence](evidence/README.md) |
| 아키텍처·트레이딩 책임 경계 | [ARCHITECTURE](docs/ARCHITECTURE.md) · [VALIDATION](docs/VALIDATION.md) |
| 변경 결정 이력 | [ADR index](docs/adr/README.md) |
| 과거 긴 README 개발 기록 | [보관본](docs/archive/README_LEGACY.md) |

## 경계 및 원칙

- 동일한 정규화 이벤트·설정·버전은 결정론적으로 재생하며, 원본 출처·PIT·달력·기업행동·통화·비용 가정의 불확실성을 숨기지 않습니다.
- Historical/Paper는 **가상** 계좌·체결만 의미합니다. Evaluate/Session의 향후 결과는 **실행되지 않은 제안**입니다. 실제 증권사 API/주문/계좌 권위/키/재조정은 **독립된 외부 실행 애플리케이션**의 책임입니다.
- Research 후보는 비용·비교 기준·미관측 구간·기록된 차단 사유를 통해 검증되며 자동으로 거래 전략으로 승격되지 않습니다.
- 시장 시세 원본, API 키, 개인 계좌/거래 로그 등은 Git에 저장하지 않습니다. 공개 가능한 **집계 결과와 근거**는 `evidence/`, 상세 E5 산출물은 권한 확인 후 비공개 보존 영역에 기록합니다.
- 테스트 통과나 과거 백테스트 수익은 실거래 성과 보증이나 E5/E6 승인 조건을 대체하지 않습니다.

> Codex 및 병렬 개발: PR #66/#69는 다종목 코어를 별도로 수정 중입니다. 저장소 정리 변경사항과 겹치는 `ROADMAP`/`STATUS`/`AGENTS`는 이 정리 PR에서 덮어쓰지 않습니다. 각 PR은 최신 기준에서 재검증한 후 순서대로 병합해야 합니다.
