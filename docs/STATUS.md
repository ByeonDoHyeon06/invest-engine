# 프로젝트 현황 및 재개 지점

**기준일:** 2026-11-15
**현재:** E0 코드 초안 구현, Draft PR #11 리뷰/CI 검증 중. 실거래 기능 없음.
**현재 Stage:** [E0 Foundation — Issue #1](https://github.com/ByeonDoHyeon06/invest-engine/issues/1) (IN REVIEW, NOT DONE)
**실거래 승인 상태:** NOT AUTHORIZED

## E0 재개 지점 / 다음 작업 (2026-11-15)

- 구현 브랜치: `feat/e0-foundation-contracts`
- Draft PR: https://github.com/ByeonDoHyeon06/invest-engine/pull/11
- 코드 최초 반영 커밋: `643605f532003a56a046a9d83b94b04206c1ca1d`
- 로컬 결과: Python 3.13에서 `PYTHONPATH=src python -m pytest -q` → **36 passed, 1 skipped** (Hypothesis 미설치). `compileall`, offline editable install, synthetic CLI 1000 events 실행 확인.
- **미검증:** Ruff / mypy / Hypothesis가 로컬 네트워크 제한으로 설치 불가. GitHub Actions 결과 확인 필요. Python 3.12 런타임은 CI에서 확인.
- **다음 단일 작업:** PR #11의 GitHub CI 실패 항목 분석/수정 → 통과 확인 → 안전성 리뷰 → 병합 → E0 DoD 갱신.
- **E1은 PR #11이 검증·병합되기 전 착수 금지.**
- LIVE: NOT AUTHORIZED, Adapter/Order submission 없음.

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
- 2026-11-15: 빈 저장소에서 비전/계획 문서 작성, E0 진입 예정.
- 2026-11-15: E0 도메인/이벤트/결정론적 replay 코드·CLI·테스트·CI 초안, Draft PR #11 (로컬 36 passed, 1 skipped).

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
