# ADR-0001: Engine-first, deterministic core

- Date: 2026-11-15
- Status: Accepted

## Context
제품 UI·SaaS보다 매매·회계·위험 정확성이 먼저다. Backtest/Forward/Live에서 로직 분리 시 테스트 결과가 실제 실행에 반영되지 못할 우려가 있다.

## Decision
이벤트 기반 Modular Monolith, side-effect 없는 reducer core + 비동기 I/O shell. Core는 상태→이벤트→새상태/명령 전이만 계산하고, 외부 IO와 브로커는 adapter로 처리한다. 주문/체결/계좌는 별도 책임으로 분리. 초기부터 CI·결정론 replay를 통과시킨 후 전략을 추가한다.

## Alternatives
시간봉 단일 반복 루프(간단하지만 확장/복구 취약), 초기에 microservices/Kafka 등(관리비 증가), 전략마다 별도 백테스트/실거래 코드(불일치).

## Consequences
초기 이벤트 계약 설계 비용이 들지만 장기적으로 백테스트/실거래 공통 로직과 재현성이 좋아진다. 실제 실행 환경의 비결정적 수신 순서는 기록된 이벤트/시간 정보로 관리한다.

## Revisit
실측된 처리량/지연 문제로 단일 writer가 병목임이 확인되거나 복수 계좌 병렬 처리가 명시적 요구가 될 때.
