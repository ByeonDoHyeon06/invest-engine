# ADR-0004: Controlled self-improvement, no unsupervised live mutation

- Date: 2026-11-15
- Status: Accepted

## Context
사용자는 성과 기반 전략 자동 개선, 시장 레짐 판단, 재무제표·공시 분석, ML과 자동 가설 생성까지 확장하고자 한다. 검증하지 않은 후보를 라이브에 즉시 투입하는 것은 과적합과 손실 위험을 키운다.

## Decision
Research Runtime(실험/학습/후보 평가)과 Trading Runtime(운영 주문)을 분리한다. Strategy artifacts는 immutable 버전/데이터 해시/검증 결과를 가진다. 후보는 Backtest → OOS → Shadow → Paper → 명시적 Live 승인 단계로 승격. AI/Research는 Risk hard limit, 브로커 키, 운영 코드, LIVE 활성화 권한이 없다. No Trade 및 롤백을 1급 동작으로 취급한다.

## Alternatives
학습 직후 자동 라이브 전략 교체, LLM 직접 주문, 모델이 위험한도까지 스스로 변경.

## Consequences
실험·검증 시간이 추가되지만 사고 조사/재현/롤백 가능. 성과 악화시 종전 전략 유지 또는 중지 가능. 연구 자동화는 가능하되 실거래 전략 수정은 별도 승인.

## Revisit
전략 후보 성과가 장기간 검증되고 승인형 자동 배포의 통제 체계가 설계·감사되어 별도 운영자 결정을 받았을 때.
