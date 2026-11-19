"""Versioned, offline US regulatory cost sensitivity on a fixed fill tape.

SRO assessments are sourced rates, not a verified retail brokerage invoice.
This module intentionally does not mutate the original replay/ledger or claim
that a changed fee policy would preserve order sizes or actual fills.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP, localcontext
from zoneinfo import ZoneInfo

from invest_engine.domain.events import Bar, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import AssetClass, Market, _decimal
from invest_engine.research.report import BacktestReport, FillTrace, sha256

D = Decimal
CENT = D("0.01")
ET = ZoneInfo("America/New_York")


@dataclass(frozen=True, slots=True)
class USRegulatorySchedule:
    start: date
    end_exclusive: date
    sec_rate: Decimal
    taf_per_share: Decimal
    taf_cap_per_trade: Decimal
    source_urls: tuple[str, ...]
    version: str

    def __post_init__(self) -> None:
        if (type(self.start) is not date or type(self.end_exclusive) is not date
                or self.start >= self.end_exclusive or not self.version.strip()
                or not self.source_urls or any(not url.startswith("https://")
                                              for url in self.source_urls)):
            raise ValueError("INVALID_REGULATORY_SCHEDULE")
        for name in ("sec_rate", "taf_per_share", "taf_cap_per_trade"):
            if _decimal(getattr(self, name), field=name) < 0:
                raise ValueError("NEGATIVE_REGULATORY_RATE")
        if self.sec_rate >= 1:
            raise ValueError("INVALID_SEC_RATE")
        if self.taf_per_share > 0 and self.taf_cap_per_trade <= 0:
            raise ValueError("INVALID_TAF_CAP")

    def covers(self, charge_date: date) -> bool:
        return self.start <= charge_date < self.end_exclusive


# Intersection of SEC 2022 adjustment and 2022 FINRA equity TAF period.
# No extrapolation into January 2023 (the TAF rate changed).
US_2022 = USRegulatorySchedule(
    date(2022, 5, 14), date(2023, 1, 1), D("0.00002290"),
    D("0.000130"), D("6.49"),
    ("https://www.sec.gov/newsroom/press-releases/2022-60",
     "https://www.sec.gov/newsroom/press-releases/2023-15",
     "https://www.govinfo.gov/content/pkg/FR-2020-10-20/pdf/2020-23141.pdf"),
    "us-covered-equity-2022-v1",
)


@dataclass(frozen=True, slots=True)
class FeeAssumption:
    """Explicit scenario, not actual broker commission or rounding.

    Commission rounded half-up per executed order, optional minimum applied
    once per order. SEC rounded upward per order; TAF capped/rounded upward
    per distinct modeled execution (trade proxy). Neither convention has
    been certified as a retail pass-through. No fee waiver assumed.
    """
    commission_rate: Decimal
    commission_minimum: Decimal = D("0")
    version: str = "fixed-fill-assumed-pass-through-v1"

    def __post_init__(self) -> None:
        if (not self.version.strip() or not
                0 <= _decimal(self.commission_rate, field="commission_rate") < 1
                or _decimal(self.commission_minimum, field="commission_minimum") < 0
                or self.commission_minimum != self.commission_minimum.quantize(CENT)):
            raise ValueError("INVALID_FEE_ASSUMPTION")


@dataclass(frozen=True, slots=True)
class OrderCost:
    intent_id: str
    side: str
    assumed_charge_date: date
    executions: int
    gross: Decimal
    quantity: Decimal
    original_cost: Decimal
    commission: Decimal
    sec_fee: Decimal
    taf: Decimal

    @property
    def cost(self) -> Decimal:
        return self.commission + self.sec_fee + self.taf


@dataclass(frozen=True, slots=True)
class FixedFillCostAudit:
    source_run_sha256: str
    policy_sha256: str
    orders: tuple[OrderCost, ...]
    original_total: Decimal
    repriced_total: Decimal
    original_net_pnl: Decimal
    fixed_fill_net_pnl: Decimal
    audit_sha256: str
    broker_verified: bool = False
    charge_date_verified: bool = False
    replayed_with_cost_policy: bool = False


def _ceil_cent(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_CEILING)


def audit_us_fixed_fills(
    report: BacktestReport, events: tuple[EventEnvelope[MarketPayload], ...],
    assumption: FeeAssumption, *, schedule: USRegulatorySchedule = US_2022,
) -> FixedFillCostAudit:
    """Reprice the observed simulated US equity/ETF tape, not the replay.

    Charge date is explicitly approximated as the ET market bar's trading
    date. Reject missing/out-of-period dates, duplicate fill identities,
    unsupported assets/FX/multi-instrument input and order spanning dates.
    The result excludes actual broker financing, income taxes and FX.
    """
    if not events or len(events) != report.event_count:
        raise ValueError("FEE_AUDIT_EVENT_COUNT_MISMATCH")
    inst = events[0].instrument_id
    if (inst is None or inst.market is not Market.US or inst.currency != "USD"
            or inst.asset_class not in (AssetClass.EQUITY, AssetClass.ETF)
            or any(e.instrument_id != inst or not isinstance(e.payload, Bar) for e in events)
            or tuple(c for c, _ in report.by_currency_start) != ("USD",)
            or tuple(c for c, _ in report.net_pnl) != ("USD",)
            or report.terminal_settlements or report.fx_base_currency is not None):
        raise ValueError("FEE_AUDIT_REQUIRES_SINGLE_USD_EQUITY_OR_ETF")
    # Bind the audit to the actual report input identity, not merely count.
    from invest_engine.core.replay import canonical_bytes

    if sha256(tuple(canonical_bytes(e).hex() for e in events)) != report.dataset_sha256:
        raise ValueError("FEE_AUDIT_DATASET_MISMATCH")
    dates: dict[str, date] = {}
    for event in events:
        bar = event.payload
        assert isinstance(bar, Bar)
        if event.event_id in dates:
            raise ValueError("FEE_AUDIT_DUPLICATE_EVENT")
        day = bar.start.astimezone(ET).date()
        if not schedule.covers(day):
            raise ValueError("FEE_AUDIT_UNCOVERED_CHARGE_DATE")
        dates[event.event_id] = day
    grouped: dict[str, list[tuple[FillTrace, date]]] = {}
    seen: set[str] = set()
    for fill in report.fills:
        if fill.execution_id in seen or not fill.execution_id or not fill.intent_id:
            raise ValueError("FEE_AUDIT_DUPLICATE_OR_INVALID_FILL")
        seen.add(fill.execution_id)
        if (fill.side not in ("BUY", "SELL") or fill.market_event_id not in dates
                or _decimal(fill.quantity, field="quantity") <= 0
                or fill.quantity != fill.quantity.to_integral_value()
                or _decimal(fill.price, field="price") <= 0
                or _decimal(fill.fee, field="fee") < 0
                or _decimal(fill.tax, field="tax") < 0):
            raise ValueError("FEE_AUDIT_INVALID_FILL")
        grouped.setdefault(fill.intent_id, []).append((fill, dates[fill.market_event_id]))
    orders: list[OrderCost] = []
    with localcontext() as ctx:
        ctx.prec = 64
        for intent_id, records in sorted(grouped.items()):
            sides = {fill.side for fill, _ in records}
            days = {day for _, day in records}
            if len(sides) != 1 or len(days) != 1:
                raise ValueError("FEE_AUDIT_AMBIGUOUS_ORDER")
            side, day = next(iter(sides)), next(iter(days))
            gross = sum((f.price * f.quantity for f, _ in records), D(0))
            qty = sum((f.quantity for f, _ in records), D(0))
            commission = max(assumption.commission_minimum,
                             (gross * assumption.commission_rate).quantize(
                                 CENT, rounding=ROUND_HALF_UP))
            sec = D(0)
            taf = D(0)
            if side == "SELL":
                sec = _ceil_cent(gross * schedule.sec_rate)
                taf = sum((_ceil_cent(min(f.quantity * schedule.taf_per_share,
                                         schedule.taf_cap_per_trade))
                           for f, _ in records), D(0))
            original = sum((f.fee + f.tax for f, _ in records), D(0))
            orders.append(OrderCost(intent_id, side, day, len(records), gross, qty,
                                    original, commission, sec, taf))
        before = sum((o.original_cost for o in orders), D(0))
        if before != (dict(report.total_fees).get("USD", D(0))
                      + dict(report.total_taxes).get("USD", D(0))):
            raise ValueError("FEE_AUDIT_LEDGER_TOTAL_MISMATCH")
        after = sum((o.cost for o in orders), D(0))
        pnl = dict(report.net_pnl)["USD"]
        adjusted = pnl + before - after
        # Report serializer has datetime support, but not date; pin dates
        # explicitly (ISO) rather than altering legacy canonical serialization.
        policy_hash = sha256((schedule.version, schedule.start.isoformat(),
                              schedule.end_exclusive.isoformat(), schedule.sec_rate,
                              schedule.taf_per_share, schedule.taf_cap_per_trade,
                              schedule.source_urls, assumption))
        order_identity = tuple((o.intent_id, o.side, o.assumed_charge_date.isoformat(),
                                o.executions, o.gross, o.quantity, o.original_cost,
                                o.commission, o.sec_fee, o.taf) for o in orders)
        digest = sha256((report.run_sha256, policy_hash, order_identity,
                         before, after, pnl, adjusted))
        return FixedFillCostAudit(report.run_sha256, policy_hash, tuple(orders),
                                  before, after, pnl, adjusted, digest)
