# Invest Engine — document guide

이 저장소는 **실제 코드**, **현재 유효한 설계/규칙**, **과거 실험 근거**, **결정 이력**을 구분합니다. 코어 소스 또는 GitHub Actions 기록이 없는 “완료” 주장은 피합니다.

## 읽는 순서

| 목적 | 문서 | 역할 |
|---|---|---|
| 무엇이 구현됐나? | [STATUS](STATUS.md) | 현재 상태와 미완료 게이트 |
| 지금 무엇을 작업하나? | [ROADMAP](ROADMAP.md) | 작업 단계, 의존성, 승인 조건 |
| 엔진은 어떻게 나뉘나? | [ARCHITECTURE](ARCHITECTURE.md) | 설계 및 외부 주문 경계 |
| **현재 데이터/실행/결과 내부 타입 경계** | [ENGINE_IO](ENGINE_IO.md) | E1→E5→E6를 연결하는 단일 참조 |
| 통합 SDK의 향후 모양 | [E6.7 spec](milestones/e6.7/E6_7_UNIFIED_SDK.md) · [23 examples](milestones/e6.7/E6_7_SDK_EXAMPLES.md) | **제안**, 아직 실행 코드 아님 |
| 전략 코드와 검증 기준 | [E4 Strategy](milestones/e4/E4_STRATEGY.md) · [E5 Backtest](milestones/e5/E5_BACKTEST.md) · [Validation](VALIDATION.md) | 현재 기능과 검증 |
| 과거 성과와 실패 실험 | [Evidence index](../evidence/README.md) | 버전된 실험 기록, 데이터 감사와 원문 |
| 설계 결정 근거 | [ADR directory](adr/README.md) | 결정 이력. 최신 스펙으로 재검토 |

## 문서 작성 원칙

- **기능 명세는 해당 도메인의 기존 정식 문서에** 추가합니다. 하나의 새 기능마다 임시 `docs/E*.md`를 계속 만들지 않습니다.
- **실험 계획·가설·실행 결과·비용 스트레스·결측 및 기각 근거는 [evidence/](../evidence/README.md)** 에 저장합니다. 시장 데이터 원본·개인 계좌 기록은 Git에 넣지 않습니다.
- **로드맵은 향후 체크리스트, STATUS는 현재 상태**를 표시합니다. 과거 실행 로그는 evidence로 옮기고 링크만 남기는 것이 목표입니다. 병렬 PR #66/#69가 종료되기 전에는 두 문서를 대규모로 정리하지 않습니다.
- **ADR은 결정 이력**이며 최신 구현 계약의 복제본이 아닙니다. 서로 충돌하면 현재 코드/검증 및 최신 승인된 정식 문서를 우선 확인합니다.
- 원래 경로의 짧은 `Archived` 안내는 과거 링크용 **호환 포인터**입니다. 중복된 보고서가 아닙니다. 병렬 PR이 끝난 뒤 링크를 완전히 이관하고 제거할 수 있습니다.
- 문서/실험 인용에는 **PR 또는 commit, CI run, 데이터 원천/라이선스, 사용한 비용 가정, 부적격 사례, 기간, 원본 해시의 종류**를 명시합니다. 모르는 값은 추측하지 않습니다.

## 보존/실행

E5의 `run_experiment()`는 `manifest.json`과 산출물의 SHA-256을 기록합니다. 공개 집계 기록은 [evidence/records](../evidence/records), 권한을 확인한 비공개 원본 보관은 `scripts/preserve_run_evidence.py`를 이용합니다. 기본은 **manifest와 해시만**, `--include-traces`는 법적/기술적 보관 권한 확인 후에만 사용합니다. 아카이브는 자동 업로드 또는 실거래 권한을 갖지 않습니다.

현재 코드는 E6.7 예제의 `Engine()`을 구현하지 않았습니다. 검증 가능한 API와 미래 설계를 반드시 구분하세요.
