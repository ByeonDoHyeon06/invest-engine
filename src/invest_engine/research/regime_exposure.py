"""E6.4b: observed-bar exposure and entry-cohort attribution.

This is diagnostic accounting, not a second portfolio ledger. The E5
average-cost realized PnL is allocated by FIFO entry *quantity* cohorts;
this is not FIFO tax-lot PnL or attribution of causal alpha.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from decimal import ROUND_DOWN, Decimal, localcontext

from invest_engine.data.calendar import StaticSessionCalendar
from invest_engine.domain.events import Bar, EventEnvelope, MarketPayload
from invest_engine.research.evaluation import MINUTE, EvaluationWindow, validate_window
from invest_engine.research.regime import RegimePolicy, Trend, Volatility, classify_regime
from invest_engine.research.regime_study import attribute_regimes
from invest_engine.research.report import BacktestReport, sha256

D = Decimal
Key = tuple[Trend, Volatility]


@dataclass(frozen=True, slots=True)
class RegimeExposure:
    trend: Trend
    volatility: Volatility
    observed_minutes: int = 0
    exposed_open_minutes: int = 0
    open_share_minutes: Decimal = D(0)
    entry_quantity: Decimal = D(0)
    closed_entry_quantity: Decimal = D(0)
    remaining_entry_quantity: Decimal = D(0)
    allocated_realized_pnl: Decimal = D(0)

    @property
    def exposure_fraction(self) -> Decimal | None:
        if not self.observed_minutes:
            return None
        with localcontext() as ctx:
            ctx.prec = 64
            return D(self.exposed_open_minutes)/self.observed_minutes


@dataclass(frozen=True, slots=True)
class RegimeExposureStudy:
    run_sha256: str
    report_sha256: str
    policy_sha256: str
    dataset_sha256: str
    currency: str
    rows: tuple[RegimeExposure, ...]
    evaluation_minutes: int
    ending_quantity: Decimal
    attribution: str = "average-cost-realized-pnl-fifo-quantity-cohorts-v1"
    exposure_basis: str = "quantity-at-start-of-observed-regular-minute-v1"

    @property
    def digest(self) -> str:
        return sha256(self)


def study_regime_exposure(
    report: BacktestReport, events: tuple[EventEnvelope[MarketPayload], ...],
    calendar: StaticSessionCalendar, window: EvaluationWindow, policy: RegimePolicy,
) -> RegimeExposureStudy:
    """All evaluated minutes, including no fills and unknown regimes.

    No warmup exposure, overnight elapsed minutes or inferred intrabar times.
    Inventory is reconstructed solely from the strict no-corporate-action
    report's ordered fills, initially zero. Opening quantity excludes current
    bar fills. Exit PnL is the E5 average-cost figure, allocated in proportion
    to FIFO-matched quantities, at the original fill's Decimal exponent with
    deterministic remainder to the last cohort. Not an independent PnL model.
    """
    if policy.interval != MINUTE:
        raise ValueError("REGIME_EXPOSURE_REQUIRES_MINUTE_POLICY")
    # Reconcile totals and validate event/fill identities before attribution.
    base = attribute_regimes(report, events, calendar, window, policy)
    coverage = validate_window(events, calendar, window)
    inst = events[0].instrument_id
    assert inst is not None
    eval_events = events[coverage.warmup_bars:]
    index = {e.event_id: i for i, e in enumerate(eval_events)}
    if len(report.decisions) != len(events) or any(
            d.event_id != e.event_id for d, e in zip(report.decisions, events, strict=True)):
        raise ValueError("REGIME_EXPOSURE_DECISION_TAPE_MISMATCH")
    if any(d.fills for d in report.decisions[:coverage.warmup_bars]):
        raise ValueError("REGIME_EXPOSURE_WARMUP_FILLS")
    documented = tuple((d.event_id, fill_id)
                       for d in report.decisions[coverage.warmup_bars:] for fill_id in d.fills)
    if documented != tuple((f.market_event_id, f.execution_id) for f in report.fills):
        raise ValueError("REGIME_EXPOSURE_FILL_ORDER_MISMATCH")

    fills = iter(report.fills)
    pending = next(fills, None)
    rows: dict[Key, RegimeExposure] = {}
    cohorts: deque[tuple[Key, Decimal]] = deque()
    quantity = D(0)
    buy_total = D(0)
    sell_total = D(0)
    actual_pnl = dict(report.realized_exit_pnl).get(inst.currency, D(0))
    prefill = dict(base.classifications)

    def get(key: Key) -> RegimeExposure:
        return rows.get(key, RegimeExposure(*key))

    with localcontext() as ctx:
        ctx.prec = 64
        for i, event in enumerate(eval_events):
            bar = event.payload
            assert isinstance(bar, Bar)
            # Strict E5 tape is already exact/ordered. Only previous bars in
            # the lookback can contribute to this as-of classification.
            absolute = coverage.warmup_bars+i
            history = events[max(0, absolute-(policy.lookback_returns+1)):absolute]
            obs = classify_regime(history, inst, calendar, bar.start, policy)
            if event.event_id in prefill and prefill[event.event_id] != obs:
                raise ValueError("REGIME_EXPOSURE_CLASSIFICATION_MISMATCH")
            key = (obs.trend, obs.volatility)
            row = get(key)
            rows[key] = replace(row, observed_minutes=row.observed_minutes+1,
                                exposed_open_minutes=row.exposed_open_minutes+int(quantity > 0),
                                open_share_minutes=row.open_share_minutes+quantity)
            while pending is not None and pending.market_event_id == event.event_id:
                fill = pending
                if fill.side == "BUY":
                    quantity += fill.quantity
                    buy_total += fill.quantity
                    cohorts.append((key, fill.quantity))
                    row = get(key)
                    rows[key] = replace(row, entry_quantity=row.entry_quantity+fill.quantity)
                else:
                    if fill.quantity > quantity:
                        raise ValueError("REGIME_EXPOSURE_SHORT_OR_MISSING_ENTRY")
                    remaining = fill.quantity
                    pnl_remaining = fill.realized_pnl
                    exponent = fill.realized_pnl.as_tuple().exponent
                    assert isinstance(exponent, int)
                    quantum = D(1).scaleb(exponent)
                    while remaining > 0:
                        if not cohorts:
                            raise ValueError("REGIME_EXPOSURE_COHORT_UNDERFLOW")
                        origin, held = cohorts.popleft()
                        closed = min(remaining, held)
                        portion = (pnl_remaining if closed == remaining else
                                   (fill.realized_pnl*closed/fill.quantity).quantize(
                                       quantum, rounding=ROUND_DOWN))
                        row = get(origin)
                        rows[origin] = replace(row,
                            closed_entry_quantity=row.closed_entry_quantity+closed,
                            allocated_realized_pnl=row.allocated_realized_pnl+portion)
                        remaining -= closed
                        pnl_remaining -= portion
                        if held > closed:
                            cohorts.appendleft((origin, held-closed))
                    quantity -= fill.quantity
                    sell_total += fill.quantity
                pending = next(fills, None)
            if pending is not None and index[pending.market_event_id] <= i:
                raise ValueError("REGIME_EXPOSURE_FILL_ORDER_MISMATCH")
        if pending is not None:
            raise ValueError("REGIME_EXPOSURE_UNCONSUMED_FILLS")
        for key, held in cohorts:
            row = get(key)
            rows[key] = replace(row, remaining_entry_quantity=row.remaining_entry_quantity+held)
        ordered = tuple(rows[key] for key in sorted(rows, key=lambda x: (x[0].value, x[1].value)))
        if (sum(row.observed_minutes for row in ordered) != coverage.evaluation_bars
                or any(not 0 <= row.exposed_open_minutes <= row.observed_minutes
                       or row.entry_quantity != row.closed_entry_quantity+row.remaining_entry_quantity
                       for row in ordered)
                or sum((row.entry_quantity for row in ordered), D(0)) != buy_total
                or sum((row.closed_entry_quantity for row in ordered), D(0)) != sell_total
                or sum((row.remaining_entry_quantity for row in ordered), D(0)) != quantity
                or sum((row.allocated_realized_pnl for row in ordered), D(0)) != actual_pnl):
            raise ValueError("REGIME_EXPOSURE_RECONCILIATION_FAILED")
    return RegimeExposureStudy(report.run_sha256, base.report_sha256, policy.digest,
                               base.dataset_sha256, inst.currency, ordered,
                               coverage.evaluation_bars, quantity)
