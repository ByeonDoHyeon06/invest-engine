# 프로젝트 현황 및 재개 지점

**기준일:** 2026-11-15
**현재:** E0 VERIFIED; E1.1 #12 merged; E1.2 #13 merged. E1.3 Parquet/manifest 검증 중 (PR #14), 실거래 기능 없음.
**현재 Stage:** [E1 — Issue #2](https://github.com/ByeonDoHyeon06/invest-engine/issues/2) (IN PROGRESS: E1.3 PR #14, E1.1/E1.2 VERIFIED). E0 VERIFIED + MERGED.
**실거래 승인 상태:** NOT AUTHORIZED

## 완료된 E0와 다음 실행 지점 (2026-11-15)

- E0 Epic: https://github.com/ByeonDoHyeon06/invest-engine/issues/1 (CLOSED)
- 병합 PR: https://github.com/ByeonDoHyeon06/invest-engine/pull/11
- Squash merge: https://github.com/ByeonDoHyeon06/invest-engine/commit/aae7bf7838c0abe8eeea6363461a358cb70db974
- **검증된 구현:** Python 패키지/CLI, InstrumentId·Money·Price·Quantity, MarketEvent 타입, UTC Clock, deterministic synthetic Replay, 기본 secret guard.
- **GitHub CI:** https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43708153842 — Python 3.12 및 3.13 **각 37 passed**; Ruff / mypy / credential guard 통과.
- E0 범위: **계좌/주문/위험·거래전략/백테스트 없음**. Replay는 이벤트의 일관된 해시를 검증할 뿐 실제 체결 시뮬레이터가 아님.
- 로컬: Python 3.13에서 36 passed + Hypothesis 미설치로 1 skipped. CI는 Hypothesis 포함 37 passed.
- **진행 중:** [PR #12](https://github.com/ByeonDoHyeon06/invest-engine/pull/12) — DataProvider/Normalizer/Quality/PIT 계약. GitHub CI [run 43712325371](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43712325371): Python 3.12/3.13 Ruff/mypy/pytest/secret guard 전부 통과; PR #12 merged (13cb52d).
- **검증 완료:** [PR #13](https://github.com/ByeonDoHyeon06/invest-engine/pull/13), squash [1d8756c](https://github.com/ByeonDoHyeon06/invest-engine/commit/1d8756c6ae13fffdb79d39ecf33fdc0f9d443611). [GitHub CI 43713285009](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43713285009): Python 3.12/3.13 Ruff/mypy/pytest/secret guard 통과. 로컬 66 passed, 1 skipped(로컬 Hypothesis 미설치).
- **진행 중:** [PR #14](https://github.com/ByeonDoHyeon06/invest-engine/pull/14) — 데이터셋 Manifest/라이선스/sha256, 원본·정규화 Parquet 저장, 수정 버전/결측 정책 및 Round-trip 테스트. 로컬 73 passed, 3 skipped (Hypothesis 및 pyarrow 미설치); **CI 미통과 시 완료로 표기 금지.**
- **다음 단일 작업:** PR #14의 Python 3.12/3.13 CI·테스트/타입 오류 수정, 검증 후 병합. E1 전체 게이트 통과 시 Issue #2 종료 및 E2 진입.
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
