# 프로젝트 현황 및 재개 지점

**기준일:** 2026-11-16
**현재:** E0/E1 VERIFIED. E2 구현·CI 통과(PR #15), 문서 동기화 및 병합 대기. 실제 주문·전략·계좌 없음.
**현재 Stage:** [E2 — Issue #3](https://github.com/ByeonDoHyeon06/invest-engine/issues/3) (CODE VERIFIED; PR #15 MERGE PENDING). Next after merge: E3 Issue #4.
**실거래 승인 상태:** NOT AUTHORIZED

## 완료된 E0/E1와 다음 실행 지점 (2026-11-15)

- E0 Epic: https://github.com/ByeonDoHyeon06/invest-engine/issues/1 (CLOSED)
- 병합 PR: https://github.com/ByeonDoHyeon06/invest-engine/pull/11
- Squash merge: https://github.com/ByeonDoHyeon06/invest-engine/commit/aae7bf7838c0abe8eeea6363461a358cb70db974
- **검증된 구현:** Python 패키지/CLI, InstrumentId·Money·Price·Quantity, MarketEvent 타입, UTC Clock, deterministic synthetic Replay, 기본 secret guard.
- **GitHub CI:** https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43708153842 — Python 3.12 및 3.13 **각 37 passed**; Ruff / mypy / credential guard 통과.
- E0 범위: **계좌/주문/위험·거래전략/백테스트 없음**. Replay는 이벤트의 일관된 해시를 검증할 뿐 실제 체결 시뮬레이터가 아님.
- 로컬: Python 3.13에서 36 passed + Hypothesis 미설치로 1 skipped. CI는 Hypothesis 포함 37 passed.
- **검증 완료:** [PR #12](https://github.com/ByeonDoHyeon06/invest-engine/pull/12) — DataProvider/Normalizer/Quality/PIT 계약. GitHub CI [run 43712325371](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43712325371): Python 3.12/3.13 Ruff/mypy/pytest/secret guard 전부 통과; PR #12 merged (13cb52d).
- **검증 완료:** [PR #13](https://github.com/ByeonDoHyeon06/invest-engine/pull/13), squash [1d8756c](https://github.com/ByeonDoHyeon06/invest-engine/commit/1d8756c6ae13fffdb79d39ecf33fdc0f9d443611). [GitHub CI 43713285009](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43713285009): Python 3.12/3.13 Ruff/mypy/pytest/secret guard 통과. 로컬 66 passed, 1 skipped(로컬 Hypothesis 미설치).
- **검증 완료:** [PR #14](https://github.com/ByeonDoHyeon06/invest-engine/pull/14), squash [77e7aab](https://github.com/ByeonDoHyeon06/invest-engine/commit/77e7aab5fb9433edbe53f084d800e52dd051cae2). [CI 43714655109](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43714655109): Python 3.12/3.13 각각 76 passed + Ruff/mypy/secret guard. 로컬 73 passed, 3 skipped(로컬 의존성 미설치). Parquet 실제 저장/복원 테스트는 CI에서 실행됨.
- **E2 구현:** [PR #15](https://github.com/ByeonDoHyeon06/invest-engine/pull/15) immutable State/Reducer + pure observation routing, DAG scheduler skeleton, SQLite event journal/atomic checkpoints/restart verification, fail-closed halt.\n- **E2 CI:** [run 43834211614](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43834211614): Python 3.12/3.13 각각 99 passed + Ruff/mypy/secret guard. 로컬은 96 passed, 3 skipped (선택 라이브러리 미설치).\n- **다음 단일 작업:** PR #15 최종 문서-only CI 검증 후 병합·E2 Issue #3 종료. 이후 E3 Issue #4의 Portfolio/OrderIntent/SimBroker 계약을 작은 PR로 시작.
- 미래 개선 TODO: Decimal 자릿수/통화별 반올림 정책은 E3 money ledger 이전에 별도 ADR 결정. 단순 범위 제한된 속성 테스트를 모든 입력에 대한 임의 정밀도 보장으로 해석하지 말 것.
- LIVE: NOT AUTHORIZED, 브로커 주문 호출 경로 없음.

## 기술 선택 상태
| 주제 | 상태 | 출처 |
| --- | --- | --- |
| Event-driven deterministic core | 채택 | ADR-0001 |
| Resolution-agnostic market events | 채택 | ADR-0002 |
| Personal-first, broker-independent | 채택 | ADR-0003 |
| Research/Live 분리, 승인된 전략만 Live | 채택 | ADR-0004 |
| ORM/DB/메시징/모델 | 미확정 | 필요 시 ADR |
| 실제 토스 API 계약·Rate limit 상세 | 검증 필요 | INTEGRATIONS.md |
| 주문 실거래 허용 | 미승인 | E8 Gate |


## GitHub Epic 추적
- [E0 — Issue #1](https://github.com/ByeonDoHyeon06/invest-engine/issues/1)
- [E1 — Issue #2](https://github.com/ByeonDoHyeon06/invest-engine/issues/2)
- [E2 — Issue #3](https://github.com/ByeonDoHyeon06/invest-engine/issues/3)
- [E3 — Issue #4](https://github.com/ByeonDoHyeon06/invest-engine/issues/4)
- [E4 — Issue #5](https://github.com/ByeonDoHyeon06/invest-engine/issues/5)
- [E5 — Issue #6](https://github.com/ByeonDoHyeon06/invest-engine/issues/6)
- [E6 — Issue #7](https://github.com/ByeonDoHyeon06/invest-engine/issues/7)
- [E7 — Issue #8](https://github.com/ByeonDoHyeon06/invest-engine/issues/8)
- [E8 — Issue #9](https://github.com/ByeonDoHyeon06/invest-engine/issues/9)
- [E9 — Issue #10](https://github.com/ByeonDoHyeon06/invest-engine/issues/10)

## 변경 기록
- 2026-11-16: E2 코드 PR #15에서 통과(GitHub CI 43834211614). 문서/상태 반영 중, 병합 전. 라이브 기능 없음.
- 2026-11-15: E1.3 PR #14 squash merged (77e7aab), [CI 43714655109](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43714655109) Python 3.12/3.13 각각 76 passed. E1 전체 데이터 기반 검증, Issue #2 종료 및 E2 next.
- 2026-11-15: E1.3 PR #14 생성; immutable Parquet raw/normalized datasets, SHA256 및 provenance 명세. CI 검증 중.
- 2026-11-15: E1.2 PR #13 squash merged (1d8756c), GitHub CI 43713285009 양쪽 Python 버전 통과. E1.3 next.
- 2026-11-15: E1.2 PR #13 구현 중. 세션 기준 시간봉 재구성과 미국 DST/조기폐장 검증(로컬 66 passed + Hypothesis 미설치 1 skipped).
- 2026-11-15: E1.1 PR #12 squash merged (13cb52d), CI run 43712325371 양쪽 Python 버전 정상. E1.2가 다음 작업.
- 2026-11-15: E1.1 브랜치 feat/e1-ingestion-quality-pit 및 Draft PR #12 생성. 엄격한 공급자 원시데이터 정규화·feed quarantine·as-of 관측 경계 추가. 전체 E1은 미완료.
- 2026-11-15: 빈 저장소에서 비전/계획 문서 작성, E0 진입 예정.
- 2026-11-15: E0 도메인/이벤트/결정론적 replay 코드·CLI·테스트·CI 초안, Draft PR #11 (로컬 36 passed, 1 skipped).
- 2026-11-15: [CI run 43708332491](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43708332491)에서 Python 3.12/3.13 각 37 passed 및 Ruff/mypy/secret 검사 성공. E0 검증 통과.
- 2026-11-15: PR #11 squash merged (aae7bf7); Issue #1 closed. E1 Issue #2가 다음 작업.

## 회차 종료·재개 기록 템플릿
- 날짜:
- 현재 E단계:
- 완료된 PR/commit:
- 검증 커맨드·결과:
- 미완료 작업:
- 블로커:
- 다음 단일 작업:
- 변경된 ADR:
- 라이브 안전 상태:

**에이전트 및 개발자는 새 작업 시작 전 README → STATUS → ROADMAP → 관련 설계/ADR을 읽고, 끝날 때 STATUS를 갱신한다.**
