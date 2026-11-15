# 프로젝트 현황 및 재개 지점

**기준일:** 2026-11-15
**현재:** 설계/로드맵 초기화. 실거래 없음. 구현 시작 전.
**현재 Stage:** E0 Foundation (NEXT)
**실거래 승인 상태:** NOT AUTHORIZED

## 가장 먼저 할 일 (순서 고정)
1. ROADMAP.md E0를 읽고 E0 작업을 독립된 PR 크기로 분할한다.
2. src-layout Python 3.12+ 프로젝트·pytest·Ruff·mypy·CI 초기화.
3. DOMAIN.md에 따른 EventEnvelope, InstrumentId, Money, UTC Clock을 구현한다.
4. synthetic fixtures로 결정론적 이벤트 재생 테스트를 만든다.
5. E0 DoD 증거(테스트 로그/PR 링크)를 이 문서에 반영한다.

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

## 변경 기록
- 2026-11-15: 빈 저장소에서 비전/계획 문서 작성, E0 진입 예정.

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
