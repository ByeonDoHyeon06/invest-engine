# 개발·리뷰·문서 갱신 규칙

## 작업을 시작할 때
1. README → docs/STATUS.md → docs/ROADMAP.md → 관련 설계 문서/ADR 순서로 읽는다.
2. STATUS에 기록된 단일 Next task를 먼저 수행한다. 계획되지 않은 확장보다 기존 미완료·실패 CI를 우선한다.
3. 작업은 작은 Issue/PR 단위로 구현한다. 목표, 범위, 테스트, DoD를 PR에 기록.
4. 주요 변경이 기존 계약을 뒤집으면 ADR을 새로 작성하고, 로드맵/상태 문서를 갱신한다.

## 개발 운영
- Python >=3.12, src-layout 패키지, 타입 검사/formatter/pytest 기반(툴 버전은 E0에서 고정).
- Domain/Core/Strategy/Risk는 브로커 API와 네트워크를 호출하지 않는다.
- 실거래 기능은 기본 거부. Live 테스트/장애 시나리오가 없는 코드는 Live 경로에 병합하지 않는다.
- 공개 저장소에 API 키·개인 계좌정보·토스 유료/제한 데이터·비밀정보를 포함하지 않는다.
- 테스트 입력은 합성 또는 배포 권한 확인한 fixtures만 사용한다.
- 새로운 데이터나 Feature는 timezone/available-at/schema/source/quality 정책을 정의한다.

## PR Template
- Goal / Epic(E#) / Linked issue
- Implementation and deliberate exclusions
- Invariant changes / migration / ADR link
- Verification commands and expected/actual result
- Data source and license impact
- Safety impact (paper/live)
- Docs updated (STATUS / ROADMAP / relevant spec)
- Follow-up scope

## Definition of Done
- 요구 계약 문서와 타입 구현 일치
- Unit/property/replay/integration/failure 테스트 추가 및 통과
- 미래 데이터 접근, 주문 중복, 통화 혼합, 상태 복구 등 중요 불변식 위반 없음
- CI green, 리뷰 지적 해결, Status 다음 작업 기록
- 사용자 승인 없이 Live 모드 활성화하지 않음

## 검증 불가 경우
실제 API 접근이나 데이터가 없어 확인 못한 작업은 UNVERIFIED로 두고 synthetic test/contract stub와 남은 검증 계획을 적는다. 실행하지 않은 테스트를 성공했다고 쓰지 않는다.
