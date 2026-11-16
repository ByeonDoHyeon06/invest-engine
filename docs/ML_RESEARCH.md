# Machine Learning Research Contract — 주식 예측의 실제 목표와 검증

**Status:** PROPOSED v0.1 / E6 research scope. **E3의 필수 구현 대상이 아니다.**

## 1. 왜 이 문서를 작성했는가

참고: CodingApple, '(칼럼) 딥러닝 초보들이 흔히하는 실수 : 주식가격 예측 AI'  
https://codingapple.com/unit/deep-learning-stock-price-ai/

핵심 경고는 타당하다. 주가 수준을 예측했더니 실제 가격에 가까운 그래프를 얻는다고 해서 미래 거래에서 비용 차감 후 수익이 있다는 증거가 되지 않는다. 특히 단순히 이전 종가를 다음 종가로 반환하는 persistence baseline도 훌륭한 가격 예측처럼 보일 수 있다.

아래는 글의 주장과 우리 설계의 구분:
- 채택: 무학습 기준선 비교, 미래 미관측 데이터 검증, return/방향성/신호 성과 등 목표 후보 실험, 가격·거래량 외 정보 활용, transformation 비교.
- 보완: return 또는 buy/sell로 라벨을 바꿔도 overfitting/leakage가 자동 해결되지 않는다.
- 보완: differencing/return transformation이 정상성(stationarity)을 보장하지 않는다.
- 보완: ARIMA/LSTM/Transformer/LightGBM 중 어느 하나가 우월하다고 사전 결정하지 않는다.
- 보완: 분류 정확도/MAE·RMSE만으로 거래가치 판단 금지. 위험·체결·시장별 순수익/거래수까지 평가.

검증 참고:
- https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- https://scikit-learn.org/stable/modules/generated/sklearn.dummy.DummyRegressor.html
- https://scikit-learn.org/stable/modules/generated/sklearn.dummy.DummyClassifier.html

## 2. Prediction은 Trading Signal과 다르다

    DataEvent / FundamentalEvent / MacroEvent
         ↓ PIT + feature DAG
    FeatureSnapshot (t, instruments, feature values + available_at)
         ↓
    Predictor (versioned, no broker/account-write access)
         ↓
    PredictionResult (target/horizon/value/uncertainty/abstain)
         ↓
    Strategy (could ignore model)
         ↓
    StrategySignal → Allocator → Risk → Execution

Prediction은 ORDER/BUI/SELL 같은 브로커 명령을 반환하지 않는다. 데이터 quality에 문제가 있거나 모델이 OOD(out of distribution) 신호를 감지하면 ABSTAIN.

## 3. 예측 대상(Target) 후보
1. **Forward return**: t 시점에 결정된 실행 가능 시작가격과 t+h 시점의 가격 변동률; 가격수준보다 먼저 실험.
2. **Direction**: 비용·스프레드를 고려한 임계치 초과 상승/하락/중립(3-class가 단순 2-class보다 합리적인 상황 고려).
3. **Signal success**: 특정 전략의 진입 신호가 지정한 risk/reward와 horizon에서 충분한 순 기대값을 가졌는가.
4. **Volatility distribution**: 다음 h기간의 변동성·tail loss.
5. **Expected execution cost**: 시장/호가 상태 기반 스프레드·슬리피지 예상.

각 target은 horizon, label availability, fill assumption, fee, no-trade threshold를 사전 선언해야 하며, 서로 다른 horizon 결과를 같은 숫자로 비교하지 않는다.

## 4. AI 모델 입력 계약 (제안)

    PredictRequest:
      request_id / schema_version
      instrument_id, as_of (UTC), horizon (예: PT5M)
      target_id / target_definition_version
      feature_snapshot_id / feature_set_version
      model_artifact_id (immutable)
      data_health, session_context

FeatureSnapshot:
      feature_name, feature_version, as_of,
      available_at, numeric value + unit,
      missing_flag, raw_event_ids, source_license

ML 입력에 원시 가격뿐 아니라 returns, log returns, normalized volume,
ATR/realized volatility, market/sector return, spread(있을 때만),
발표 이후에 이용 가능한 earnings/disclosure features를 구성할 수 있다.
Feature는 필수가 아니며 **실제 구할 수 있는 데이터와 비용 효과**로 선택한다.

**예시 응답(가상의 값, 실제 모델 결과 아님):**

    {
      "schema_version": "0.1-draft",
      "request_id": "pred-001",
      "as_of": "2026-11-16T01:00:00Z",
      "target": {"id":"return","horizon":"PT5M"},
      "prediction": {"expected_return":"0.0012","lower":"-0.0060","upper":"0.0080"},
      "calibrated_probability_positive": null,
      "uncertainty_model": "research-interval-v1",
      "model_artifact_id": "candidate-v1",
      "feature_snapshot_id": "feature-001",
      "action": "ABSTAIN",
      "reason_codes": ["NOT_VALIDATED_FOR_LIVE"]
    }

위 숫자는 예시이며 모델 신뢰도나 주식 향후 수익률 예측이 아니다. null은 검증된 probability가 없음을 의미한다. 분류 확률을 반환하는 모델만 calibration 검증 후 확률값을 표시한다.

## 5. 데이터 누출 방지
- Dataset: 전체 기간/종목을 기준으로 train/validation/untouched holdout을 시간 순서로 나눔.
- 표준화(scaling), 결측 대체, 특성 선택, target threshold/tuning은 **train 데이터만**으로 fit. validation으로 후보 선택, 최종 holdout은 마지막 평가 용도.
- Label 구간(t,t+h]이 겹치는 train/test 샘플은 purge/embargo 또는 안전한 gap 정책 적용.
- 스케일러가 미래 관측을 사용하거나, 재무 정정치를 최초 공시 전 Feature로 쓰는 leakage 금지.
- 거래 비용·세금·spread·지정가 주문 미체결 가능성과 수량 한도 반영.
- 데이터 미확보/이벤트 없을 때 자동 forward fill 금지.
- 전략과 모델 비교 시 데이터 subset·종목 유니버스·체결 가정/시간·비용을 가급적 동일하게 통제.
- TimeSeriesSplit은 출발점이지만 horizon-overlap을 자동 완전히 제거해 주지는 않는다.

## 6. Baselines first
**복잡한 모델을 채택하기 전 다음 기준을 반드시 비교:**
- Price persistence: 다음 가격 = 관측 시점 현재 가격.
- Return zero: 다음 구간 수익률 = 0.
- DummyRegressor/DummyClassifier: 무학습 평균·다수 클래스 등.
- Rule-based ORB/EMA(전략 기준선; E4), No Trade (거래 안 함).
- 시장에 따라 유효한 buy-and-hold/지수 기준선: 단타 전략과 비교 시 거래 가능성·노출 기간을 함께 보정.

모델 성과:
- 통계: MAE/RMSE (목표가 continuous일 때), directional metrics, Brier score/calibration (분류 확률일 때).
- 경제: 비용 차감 expectancy, PnL, drawdown, tail loss, turnover, fill ratio, exposure.
- 안정성: KR/US, 종목, 유동성, 레짐, 계절/시간대, spread/slippage stress.
- 신뢰구간/표본수: 적은 거래 수라면 성공/실패 대신 INCONCLUSIVE.

## 7. Research loop와 Production gate
PROPOSED → BACKTESTED → OOS_VERIFIED → SHADOW → PAPER → (사용자 명시 승인) LIVE_ELIGIBLE.
Candidate는 source/code/config/data/feature/model version, training cutoff, release timestamp, validation record를 포함하는 immutable artifact.
연구 모델은 risk hard limits를 수정하거나 브로커 주문 명령을 생성할 수 없으며, 자기 수정 코드가 운영 프로세스를 덮어쓰지 못하게 한다.

## 8. 개발 적용 순서
- E3: 외부 공개 I/O와 Event/Command/Result 계약 고정. **학습 기능 구현 안 함**.
- E4: StrategySignal과 Feature snapshot 계약 + no-model ORB/EMA baseline.
- E5: 비용 반영된 시계열 Replay/Backtest, baseline 측정.
- E6: PredictionResult/target/feature store, 단순 통계/ML 후보 실험, walk-forward/holdout.
- E7: 검증된 후보의 실시간 Shadow/Paper 검증.
- E8+: 승인된 설정/모델 아티팩트만 제한적 Live에 연동. 우선순위는 위험·실행 정확성이며 수익 보장 없음.
