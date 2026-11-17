"""Point-in-time FX reporting adversarial fixtures; NEVER broker conversions."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.research.fx import (
    FxObservation, FxReportingPolicy, FxSeries, base_drawdown,
)
from invest_engine.research.report import EquityPoint

T = datetime(2026, 11, 17, 0, 0, tzinfo=timezone.utc)


def quote(name: str, rate: str, received: datetime, *, effective: datetime | None = None):
    effective = effective or received
    return FxObservation(name, "USD", "KRW", D(rate), effective,
                         received, received, "synthetic-test")


def test_causal_asof_fx_refuses_future_observations_and_staleness():
    series = FxSeries((quote("r1", "1300", T),
                       quote("r2", "1500", T + timedelta(minutes=3)),))
    rule = FxReportingPolicy("KRW", timedelta(minutes=4))
    point = EquityPoint(T + timedelta(minutes=1), (("KRW", D("100000")),
                                                   ("USD", D("100"))), True)
    value = series.value_at(point, rule)
    assert value.value == D("230000")
    assert value.source_observation_ids == ("r1",)
    newer = series.value_at(EquityPoint(T + timedelta(minutes=3),
                                       point.by_currency, True), rule)
    assert newer.value == D("250000")
    stale = series.value_at(EquityPoint(T + timedelta(minutes=8),
                                       point.by_currency, True), rule)
    assert stale.value is None
    assert stale.reason_codes == ("FX_MISSING_OR_STALE:USD",)
    assert base_drawdown((value, stale)) is None


def test_causal_fx_revision_effective_time_and_received_time():
    # New quote refers to an older market time, but cannot be observed until received.
    series = FxSeries((quote("a", "1200", T),
                       quote("b", "900", T + timedelta(minutes=4),
                             effective=T - timedelta(minutes=2))))
    rule = FxReportingPolicy("KRW", timedelta(minutes=10))
    point = EquityPoint(T + timedelta(minutes=2), (("USD", D("2")),), True)
    assert series.value_at(point, rule).value == D("2400")
    assert series.value_at(EquityPoint(T + timedelta(minutes=4),
                    point.by_currency, True), rule).value == D("1800")


def test_no_implicit_inverse_or_triangular_conversion():
    inverse = FxObservation("inv", "KRW", "USD", D("0.0007"), T, T, T, "synthetic")
    series = FxSeries((inverse,))
    point = EquityPoint(T, (("USD", D("100")),), True)
    result = series.value_at(point, FxReportingPolicy("KRW", timedelta(days=1)))
    assert not result.complete and result.value is None


def test_fx_invariants_duplicate_ids_and_nonfinite():
    one = quote("one", "1300", T)
    with pytest.raises(ValueError, match="duplicate"):
        FxSeries((one, one))
    with pytest.raises(ValueError, match="ordered"):
        FxSeries((quote("later", "1300", T + timedelta(seconds=1)), one))
    with pytest.raises(ValueError, match="positive"):
        quote("bad", "0", T)
    with pytest.raises(ValueError, match="finite"):
        quote("bad", "NaN", T)
    with pytest.raises(ValueError, match="observed"):
        FxObservation("future", "USD", "KRW", D("1300"), T, T,
                      T-timedelta(seconds=1), "synthetic")
    with pytest.raises(ValueError, match="nonnegative"):
        FxReportingPolicy("KRW", timedelta(seconds=-1))


def test_incomplete_market_mark_does_not_fake_converted_value():
    series = FxSeries((quote("one", "1300", T),))
    result = series.value_at(EquityPoint(T, (), False),
                             FxReportingPolicy("KRW", timedelta(minutes=5)))
    assert result.value is None and not result.complete
    assert "MARKET_VALUATION_INCOMPLETE" in result.reason_codes
