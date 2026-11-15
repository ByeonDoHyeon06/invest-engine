# ADR-0003: Personal-first, broker-independent, SaaS deferred

- Date: 2026-11-15
- Status: Accepted

## Context
사용자는 토스증권 API 키를 보유하나 당장 상시 수동 운영이 어렵다. 상용 자동매매 SaaS는 고객 자격증명·데이터 계약·금융 규제·다중 사용자 운영 부담이 크다.

## Decision
V1은 단일 사용자 headless 연구/모의매매 엔진. Toss는 E8의 외부 BrokerAdapter로 두고 코어는 API 키 없이 작동한다. GUI/SaaS/제3자 계좌 관리/시세 재배포는 기본 범위 밖. 상용화 전에 계약 및 법률 전문가 검토.

## Alternatives
처음부터 multi-tenant SaaS, Toss-only 모놀리스, GUI 우선 개발.

## Consequences
초기 범위가 작아지고 검증에 집중할 수 있다. BrokerProtocol, AccountId, Strategy/Experiment versioning은 미래 확장이 가능한 일반 모델로 설계하되 불필요한 멀티테넌시는 구현하지 않는다.

## Revisit
충분한 엔진 검증과 상용 데이터/브로커 권한·규제 검토가 확보되고 사업모델이 별도 승인되었을 때.
