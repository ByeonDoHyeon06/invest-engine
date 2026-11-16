# 전략 플러그인 및 적응형 학습 설계

## 기본 계약
Core는 특정 매매법을 모른다. 전략은 시장데이터/특성값/읽기전용 포트폴리오 상태를 읽어 StrategySignal만 만든다. 주문·위험 정책은 변경 불가.

StrategyManifest: id, version, artifact hash, supported markets/assets, required event types/resolutions, features, warmup, parameters, state schema. Strategy.on_event(event, context) → Signal[] 또는 NoAction. Strategy.snapshot/restore로 재시작 지원.

DataRequirements: type, timeframe(optional), symbols, session, warmup, staleness threshold. 누락된 데이터에 대해 가격·체결을 만들어내지 않고 fail closed. Tick/1m/30m은 전략이 선택하며 Core는 특정 분봉을 강제하지 않는다.

StrategySignal: signal_id, strategy/version, instrument, as_of, expiration, desired direction, target exposure, proposed stop, reason codes, feature snapshot. Allocator는 여러 전략의 신호를 하나의 계좌 주문 목표로 정리하고, Pretrade Risk가 주문을 승인/거부한다.

## ORB_LONG_V1 — 최초 연구 기준선
검증되지 않은 가설이며 실거래 규칙 확정이 아니다.

| 항목 | KR 최초 실험값 | US 최초 실험값 |
| --- | --- | --- |
| session | 정규장 | 정규장 |
| opening range | 5분 | 15분 |
| signal input | 확정 1분봉 | 확정 1분봉 |
| entry proposal | 범위 고점 종가 돌파 | 범위 고점 종가 돌파 |
| volume filter | 과거 20 거래일 동일 시간대 중앙값의 1.5배 | 동일 |
| exclusion | gap/stale/넓은 spread/거래정지 | 동일 |
| proposed risk | 계획 손절 거리, ATR/시초 범위 | 동일 |
| exit proposals | 손절·보유시간·장마감 | 동일 |

봉 종료 뒤 신호 계산. 동일 봉의 과거 시가로 매수시키지 않는다. US 15분과 KR 5분은 검증 전 초기 설정. ORB, No Trade, EMA Pullback과 간단한 기준 포트폴리오를 비교한다.

## Feature Engine
- Technical: EMA, ATR, RSI, VWAP, 거래량 비율/변동성
- Microstructure: spread, depth, fill/slippage 모델(호가 데이터 있을 때만)
- Fundamental: 재무건전성, 성장성, 공시 이벤트, 기업행동
- Macro: 금리, 환율, 시장 지수, 변동성
- Feature마다 required inputs, warmup, version, available_at, missing policy.
- incremental vs batch parity 및 Feature DAG 캐시 (instrument/timeframe/params/data version/as-of).

## Market Intelligence
MarketRegime: TRENDING, RANGING, VOLATILE, UNCERTAIN + confidence, model version, valid_until.
초기에는 규칙 기반 분류, 이후 HMM/ML은 검증 데이터가 충분할 때 연구.
불확실한 경우 거래하지 않는 것이 정상 결과.

Fundamental Intelligence: 국내 OpenDART, 미국 SEC EDGAR. 재무제표·실적·공시의 실제 발표시각 및 정정 버전으로 Point-in-Time 조회. 분봉 단타에서는 무조건 매수점수가 아니라 이벤트 위험·적격성·종목 필터로 우선 검증.

Predictive Intelligence: 단기 수익률 분포, 변동성, 신호 품질, 유동성/체결 비용을 예측 후보로 연구. ML score 자체에는 주문권한이 없다. 모델의 confidence는 별도 calibration 전 확률로 해석 금지.

## 자기 개선 파이프라인
Research는 Production과 분리. 후보 상태:
PROPOSED → BACKTESTED → VALIDATED → SHADOW → PAPER_APPROVED → LIVE_ELIGIBLE → LIVE/RETIRED

L1 매매결과 분석 → L2 시장상태별 전략선택 → L3 파라미터 후보 탐색 → L4 모델 재학습/드리프트 → L5 새 전략 가설 생성. L5는 무승인 라이브 적용 금지. 연구와 자동실험 결과는 immutable artifact + code SHA + 데이터 hash + 검증 보고서에 저장한다.

## 전략 선택 원칙
최근 며칠 수익률 1등 전략을 자동 채택하지 않는다. 미관측 기간/시장별 안정성, 비용, 위험, 표본수, 시장상태, 필요데이터 충족 여부를 모두 검증한다. 동일 종목에 여러 전략이 진입을 요구하면 Exposure Allocator가 합산 위험을 제한한다.

**E4:** 전략 인터페이스·ORB/No-trade 기준선. **E6:** Regime/실험 후보 파이프라인. **E9:** Fundamental/고도화 ML 확장.

## E4 실제 구현 계약 (PR #21)

- [E4_STRATEGY.md](E4_STRATEGY.md): `StrategyManifest`, `DataRequirement`, readonly `StrategyContext`, `StrategySignal`, `NoTradeStrategy`, ORB baseline, FeatureRegistry, target allocator, synthetic OrderIntent planner.
- **E4 설계 명세가 곧 실거래 전략의 입증이 아니다**. ORB의 5m/15m 및 ×1.5 거래량 필터는 백테스트 전 연구 가설.
- 목표 할당은 fill별 전략 손익 장부가 아니므로, 정확한 전략별 기여도와 포지션 귀속은 후속 설계가 필요하다.

## E4 verified implementation (2026-11-16)

PR #21: typed Strategy SDK, NoTrade, ORB, as-of technical FeatureRegistry, target allocator. PR #22: immutable AttributionTicket + VirtualLedger shares/acquisition fees/proportional sells/realized P&L with idempotent synthetic Fill replay and E3 aggregate position audit. CI 43857703057 (Python 3.12/3.13 each 191 passed).

**Not implemented:** durable E2→E4→E3 strategy/decision journal, autonomous fill simulation, backtest reports (E5), research ML (E6), any broker orders (E8). Python strategies are trusted plugins only, not isolated sandboxed code.
