# ADR-0002: Resolution-agnostic typed events and point-in-time

- Date: 2026-11-15
- Status: Accepted

## Context
초기 1분 OHLCV에 코어를 묶으면 Tick, 호가, 30분봉, 재무·공시·거시 데이터에 대응하기 위해 엔진을 다시 작성해야 한다.

## Decision
TradeTick/QuoteTick/OrderBook/Bar/MarketStatus/FundamentalFact/DocumentEvent 등을 별도 타입으로 수용한다. 시간봉은 선택 가능한 Aggregator 출력이며 Strategy Manifest가 요구 주기와 Feature를 선언한다. 모든 이벤트는 event_time/available_at/received_at을 구분하며, 전략은 당시 이용 가능한 정보만 볼 수 있다.

## Alternatives
1분봉 고정(간단하지만 범용성 없음), 전 입력을 Tick으로 변환(원본 하위해상도 복원이 불가능하여 허위정보 생성), 비정형 dict-only 이벤트(타입 안정성 저하).

## Consequences
데이터 검증·시계열 정렬이 복잡해지나 전략 선택 폭과 정확성이 높아진다. 불충분한 입력은 Unsupported/NoTrade로 명시. 다운샘플링은 가능하나 상향 해상도 복원은 불허.

## Revisit
더 많은 자산군/데이터 유형이 필요하거나 거래소별 이벤트 시간 의미가 달라질 때 버전이 있는 새 타입을 추가한다.
