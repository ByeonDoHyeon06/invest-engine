"""Research-only ORB signal screens; no change to the original ORB or risk path."""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, localcontext

from invest_engine.domain.events import EventEnvelope, MarketPayload
from invest_engine.domain.primitives import Market, _decimal
from invest_engine.strategies.contracts import (
    StrategyContext, StrategyManifest, StrategySignal,
)
from invest_engine.strategies.orb import ORBLongStrategy, ORBParameters


@dataclass(frozen=True, slots=True)
class ORBScreen:
    once_per_week: bool = False
    minimum_range_bps: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if type(self.once_per_week) is not bool:
            raise ValueError("weekly cap must be boolean")
        _decimal(self.minimum_range_bps, field="minimum_range_bps")
        if self.minimum_range_bps < 0:
            raise ValueError("range hurdle must be nonnegative")
        if not self.once_per_week and not self.minimum_range_bps:
            raise ValueError("at least one screen is required")


class ScreenedORB:
    """Veto the first otherwise qualified ORB signal of each session.

    A veto consumes the base strategy's session signal; no later retry.
    Weekly cap counts emitted signals, not fills; zero fill is not a retry.
    Opening-range width is a volatility proxy, NOT expected return.
    """

    def __init__(self, params: ORBParameters, screen: ORBScreen) -> None:
        self.params = params
        self.screen = screen
        self._inner = ORBLongStrategy(params)
        self._weeks: set[tuple[str, str]] = set()
        name = f"orb-screen-w{int(screen.once_per_week)}-r{format(screen.minimum_range_bps, 'f')}"
        self._manifest = replace(self._inner.manifest, strategy_id=name)

    @property
    def manifest(self) -> StrategyManifest:
        return self._manifest

    def on_event(self, event: EventEnvelope[MarketPayload],
                 context: StrategyContext) -> tuple[StrategySignal, ...]:
        signals = self._inner.on_event(event, context)
        if not signals:
            return ()
        signal = signals[0]
        session = context.session
        assert session is not None
        year, week, _ = session.start.date().isocalendar()
        token = (signal.instrument.key, f"{year:04d}-W{week:02d}")
        if self.screen.once_per_week and token in self._weeks:
            return ()
        if self.screen.minimum_range_bps:
            opening = (self.params.opening_kr if signal.instrument.market is Market.KR
                       else self.params.opening_us)
            expected = tuple(session.start + self.params.timeframe * n
                             for n in range(opening // self.params.timeframe))
            bars = {x.bar.start: x.bar for x in context.bars_for(
                signal.instrument, self.params.timeframe)
                if x.session.start == session.start and x.bar.start in expected}
            if set(bars) != set(expected):
                return ()
            first = bars[expected[0]].open
            if first <= 0:
                return ()
            with localcontext() as ctx:
                ctx.prec = 64
                width = (max(x.high for x in bars.values()) -
                         min(x.low for x in bars.values()))
                if width * 10000 < first * self.screen.minimum_range_bps:
                    return ()
        if self.screen.once_per_week:
            self._weeks.add(token)
        reasons = signal.reason_codes
        if self.screen.once_per_week:
            reasons += ("WEEKLY_SIGNAL_CAP_PASSED",)
        if self.screen.minimum_range_bps:
            reasons += ("OPENING_RANGE_COST_PROXY_PASSED",)
        return (replace(signal, signal_id=f"{self.manifest.strategy_id}:{signal.signal_id}",
                        strategy_id=self.manifest.strategy_id,
                        strategy_version=self.manifest.version, reason_codes=reasons),)

    def snapshot(self) -> bytes:
        return json.dumps({"inner": json.loads(self._inner.snapshot()),
                           "weeks": sorted([list(x) for x in self._weeks])},
                          sort_keys=True, separators=(",", ":")).encode("utf-8")

    def restore(self, data: bytes) -> None:
        try:
            raw = json.loads(data)
            if not isinstance(raw, dict) or set(raw) != {"inner", "weeks"}:
                raise ValueError("invalid screened ORB snapshot")
            if not isinstance(raw["weeks"], list):
                raise ValueError("invalid weekly tokens")
            weeks: set[tuple[str, str]] = set()
            for row in raw["weeks"]:
                if (not isinstance(row, list) or len(row) != 2
                        or any(not isinstance(v, str) or not v for v in row)):
                    raise ValueError("invalid weekly token")
                year, week = row[1].split("-W")
                date.fromisocalendar(int(year), int(week), 1)
                if f"{int(year):04d}-W{int(week):02d}" != row[1]:
                    raise ValueError("noncanonical weekly token")
                weeks.add((row[0], row[1]))
            inner = ORBLongStrategy(self.params)
            inner.restore(json.dumps(raw["inner"], separators=(",", ":")).encode("utf-8"))
            canonical = json.dumps({"inner": json.loads(inner.snapshot()),
                                    "weeks": sorted([list(x) for x in weeks])},
                                   sort_keys=True, separators=(",", ":")).encode("utf-8")
            if canonical != data or (weeks and not self.screen.once_per_week):
                raise ValueError("noncanonical screened ORB snapshot")
            self._inner, self._weeks = inner, weeks
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid screened ORB snapshot") from exc
