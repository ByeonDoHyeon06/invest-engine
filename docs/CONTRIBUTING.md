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

## 문서·실험 증거 관리 (2026-11-22)

- 신규 설계 문서가 필요하기 전에 [docs/README](README.md)에서 **현재 정식 문서**를 찾고 기존 문서에 통합합니다. SDK 관련 문서는 [E6.7 통합 스펙](E6_7_UNIFIED_SDK.md)과 [예제집](E6_7_SDK_EXAMPLES.md)으로 관리합니다.
- 실험 프로토콜·실제 실행·기각·부적격 데이터의 근거는 **[evidence/](../evidence/README.md)** 로 이동합니다. `docs/`의 Archived 안내 파일은 병렬 PR의 과거 링크를 보존하기 위한 임시 호환성 안내입니다.
- 공유 가능한 집계 결과는 기계 판독형 `evidence/records/` 에 추가하고 `python scripts/check_evidence_records.py`로 검증합니다. 원시 시세·거래 로그·개인 계좌·자격 증명은 공개 Git에 두지 않습니다.
- E5의 `manifest.json`과 산출물 해시는 기존 실행기의 계약입니다. 상세 파일 장기 보존이 허용된다면 **명시적으로** `scripts/preserve_run_evidence.py --include-traces`를 사용하여 승인된 비공개 저장소에 보존합니다. 테스트용 수익률을 실제·미관측 근거로 승격하지 않습니다.
- 병렬 개발에서는 **독립 브랜치/PR 단위로 작업**하고 현재 진행 중인 PR의 파일 소유 범위를 검토합니다. 특히 #66/#69의 `ROADMAP`, `STATUS`, `AGENTS` 및 다종목 런타임은 별도 검토·순차 병합하고 무단으로 덮어쓰지 않습니다.
