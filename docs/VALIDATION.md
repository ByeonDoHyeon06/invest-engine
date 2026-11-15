# 검증 방법 — Backtesting / Forward / Live Gates

엔진의 **논리·회계 정확성**과 전략의 **시장 성과**는 별도 평가한다. 백테스트 수익으로 실거래 수익을 보장할 수 없다.

## 검증 레벨
1. Unit/property: 가격·시간·수량·통화·주문 상태 불변식.
2. Deterministic replay: 같은 코드/입력/설정/시드/이벤트 순서 → 같은 state hash.
3. Historical backtest: 당시 이용 가능한 데이터만 사용, 거래비용과 체결가정 반영.
4. Walk-forward/untouched OOS: 기간 분리, 여러 종목/시장 상태 확인.
5. Stress: 지연, 결측, 수수료/스프레드/슬리피지 증가, 갭, 폭락.
6. Paper/Shadow: 실시간 입력과 가상 주문을 몇 주 이상 감시.
7. Restricted Live: 별도 GO 승인과 주문 안전성 검증.

## Look-ahead 방지
- 전략이 보는 Feature는 available_at <= decision_clock이어야 한다.
- 09:35 종가에서 신호가 생겼으면 같은 봉의 09:34 시가로 매매했다고 처리하지 않는다.
- 과거 발표된 재무/경제 지표는 최초 공개 시점과 revision(vintage)을 보존한다.
- 연구 시점의 상장 종목만 사용하는 survivorship bias, adjusted/unadjusted price 혼동, leakage 방지.
- 학습/검증/test의 시간 순서를 보존한다. 테스트셋을 반복 참고하여 튜닝했다면 새 독립 검증 기간이 필요하다.

## 보수적 바 기반 체결 모델
OHLCV만 있을 때:
- 신호를 만든 봉이 완전히 종료된 뒤의 첫 유효 거래 시점부터 주문 평가.
- 지정가가 고/저가 범위에 포함되더라도 확실히 체결된 것으로 가정하지 않으며 볼륨 참여상한/지연/대기 가능성 검토.
- 같은 봉에서 stop과 target이 모두 터치되면 봉 내부 순서를 알 수 없으므로 보수적인 순서로 가정하고 별도 민감도 실험.
- 갭으로 손절가 통과하면 불리한 가격을 고려. 가격 보장 없음.
- 슬리피지, spread, 수수료·세금·환율·거래시장 세션을 별도로 파라미터화한다.
- Tick+Quote를 확보할 경우 더 정교한 모델로 교체할 수 있으나 호가 대기열을 완벽 재현한다고 주장하지 않는다.

## Experiment Manifest
experiment_id, code SHA, strategy version, dataset hash/source/license, instrument universe as-of, start/end/timezone/calendar version, fill/fee/slippage version, random seed, feature versions, config SHA, trade logs, metric set, pass/fail & reviewer.

## 핵심 성능 지표
Net Return/PNL, Max Drawdown, Profit Factor, Expectancy, trade count, turnover, exposure, average holding, cost/share, tail loss, rejected/partial fill ratio, market regime별 성과, 시뮬레이션/forward fill 괴리.
특정 승률·연수익률 한 가지 숫자로 성공 여부를 판단하지 않는다. 거래수가 적으면 불확실성을 명시하고 무리한 결론을 내리지 않는다.

## Forward Test
- KR/US 각각 최소 20 거래일을 관찰하는 것을 첫 체크포인트로 삼는다. 통계적 충분성은 별도 판단.
- 동일한 전략/설정/위험 정책 버전을 고정하고 관찰; 바꾸면 새 실험으로 기록.
- 재연결, 중복 fill, 부분체결, 거래정지, 주문 복구, 달러/원화 분리 테스트.
- Shadow 후보는 Production에 주문을 내지 못한다.
- 상태 복원과 수동 중단 Runbook, 경고 로그 검증 후 실거래 후보로 넘긴다.

## 릴리스 Gate
| Gate | DoD |
| --- | --- |
| G0 (E0~E3) | 합성 테스트, 결정론, 주문·자금 불변식 증명 |
| G1 (E4~E5) | 전략 결과 재현, no look-ahead, 비용·체결 모델의 합리적 가정 명시 |
| G2 (E6) | 미관측 데이터/다중 비용/시장환경 검증, 선택 편향·과적합 평가 |
| G3 (E7) | 양국 실시간 Paper, 장애복구·데이터품질·모니터링 확인 |
| G4 (E8) | 인간 운영자 명시 승인, API·보안·규정 검토, 소액/종목제한 실거래 검증 |

게이트 미통과 시 출시하지 않고 연구/테스트 단계로 되돌린다. 실거래 기능은 처음부터 비활성화.

## 목표 CLI 스케치 (아직 미구현)
    invest-engine backtest --experiment configs/experiments/orb-kr.yaml
    invest-engine validate --experiment <id>
    invest-engine replay --manifest <id>
    invest-engine paper --config configs/paper.yaml

테스트 증거는 GitHub PR 또는 로그/산출물 SHA로 연결하고 docs/STATUS.md를 업데이트한다.
