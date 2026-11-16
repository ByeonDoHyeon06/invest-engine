"""Opening-range breakout signal *hypothesis*, not a validated trading system."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, localcontext
from statistics import median

from invest_engine.domain.events import Bar, BarKind, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import Market, _decimal
from invest_engine.features.registry import FeatureDefinition, FeatureKind
from invest_engine.strategies.contracts import (
    DataRequirement, SignalDirection, StrategyContext, StrategyManifest, StrategySignal,
)


@dataclass(frozen=True, slots=True)
class ORBParameters:
    timeframe: timedelta = timedelta(minutes=1)
    opening_kr: timedelta = timedelta(minutes=5)
    opening_us: timedelta = timedelta(minutes=15)
    prior_sessions: int = 20
    volume_multiplier: Decimal = Decimal("1.5")
    target_fraction: Decimal = Decimal("0.05")
    atr_period: int = 14

    def __post_init__(self) -> None:
        if self.timeframe <= timedelta(0) or self.opening_kr <= timedelta(0) or self.opening_us <= timedelta(0):
            raise ValueError("timeframes must be positive")
        if self.opening_kr % self.timeframe or self.opening_us % self.timeframe:
            raise ValueError("opening range must be an integer number of bars")
        if self.prior_sessions < 1 or self.atr_period < 1:
            raise ValueError("history periods must be positive")
        _decimal(self.volume_multiplier, field="volume_multiplier", positive=True)
        _decimal(self.target_fraction, field="target_fraction", positive=True)
        if self.target_fraction > 1:
            raise ValueError("target fraction > 1")


class ORBLongStrategy:
    """Requires 20 prior *distinct* sessions for matching-minute volume median.

    Signals once per session, on the first confirmed cross above the opening
    high after the range completes. No fill inference or brokerage permissions.
    """

    def __init__(self, params: ORBParameters = ORBParameters()) -> None:
        self.params = params
        self._last_signaled: set[tuple[str, str]] = set()
        self._manifest = StrategyManifest(
            "orb-long", "1.0.0", frozenset((Market.KR, Market.US)),
            (DataRequirement("market.bar", params.timeframe, warmup=params.atr_period+1),),
            (FeatureDefinition("atr", FeatureKind.ATR, params.timeframe, params.atr_period),),
        )

    @property
    def manifest(self) -> StrategyManifest:
        return self._manifest

    def on_event(self, event: EventEnvelope[MarketPayload],
                 context: StrategyContext) -> tuple[StrategySignal, ...]:
        if not isinstance(event.payload, Bar) or event.payload.kind is not BarKind.TIME:
            return ()
        inst, session = event.instrument_id, context.session
        if inst is None or session is None:
            return ()
        current = event.payload
        opening = self.params.opening_kr if inst.market is Market.KR else self.params.opening_us
        opening_end = session.start + opening
        if current.start < opening_end or context.as_of >= session.end:
            return ()
        token = (inst.key, session.start.isoformat())
        if token in self._last_signaled:
            return ()
        history = context.bars_for(inst, self.params.timeframe)
        today = [x for x in history if x.session.start == session.start]
        expected = [session.start + self.params.timeframe * n
                    for n in range(opening // self.params.timeframe)]
        open_bars = {x.bar.start: x.bar for x in today if x.bar.start in expected}
        if set(open_bars) != set(expected):
            return ()  # never interpolate opening gaps
        high = max(b.high for b in open_bars.values())
        low = min(b.low for b in open_bars.values())
        if current.close <= high:
            return ()
        # Causal breakout: previous adjacent finalized bar must have closed <= high.
        previous = next((x.bar for x in today if x.bar.end == current.start), None)
        if previous is None or previous.close > high:
            return ()
        # Historical same-minute volume: exclude the entire current session.
        offset = current.start - session.start
        past: dict[str, Decimal] = {}
        for bar in reversed(history):
            if bar.session.start >= session.start:
                continue
            if bar.bar.start - bar.session.start == offset:
                key = bar.session.start.isoformat()
                if key not in past:
                    past[key] = bar.bar.volume
            if len(past) >= self.params.prior_sessions:
                break
        if len(past) < self.params.prior_sessions:
            return ()
        with localcontext() as ctx:
            ctx.prec = 64
            benchmark = median(list(past.values()))
            if benchmark <= 0 or current.volume < benchmark * self.params.volume_multiplier:
                return ()
            atr = context.feature("atr")
            if atr is None or atr <= 0:
                return ()
            # The stop is a *plan*; the execution engine does not guarantee it.
            stop = max(low, current.close - atr * 2)
            if stop <= 0 or stop >= current.close:
                return ()
        expires_at = min(context.as_of + self.params.timeframe, session.end)
        if expires_at <= context.as_of:
            return ()
        signal = StrategySignal(
            f"orb:{inst.key}:{session.start.isoformat()}", self._manifest.strategy_id,
            self._manifest.version, inst, SignalDirection.LONG,
            self.params.target_fraction, context.as_of, expires_at,
            event.event_id, stop_price=stop,
            reason_codes=("OPENING_RANGE_BREAKOUT", "SAME_MINUTE_VOLUME_CONFIRMED"),
        )
        self._last_signaled.add(token)
        return (signal,)

    def snapshot(self) -> bytes:
        return json.dumps(sorted([list(pair) for pair in self._last_signaled]),
                          separators=(",", ":")).encode("utf-8")

    def restore(self, data: bytes) -> None:
        try:
            raw = json.loads(data)
            if not isinstance(raw, list) or any(
                not isinstance(row, list) or len(row) != 2
                or any(not isinstance(v, str) or not v for v in row)
                for row in raw
            ):
                raise ValueError("invalid ORB snapshot")
            tokens = {(row[0], row[1]) for row in raw}
            if len(tokens) != len(raw) or self.snapshot_schema(tokens) != data:
                raise ValueError("noncanonical ORB snapshot")
            self._last_signaled = tokens
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid ORB snapshot") from exc

    @staticmethod
    def snapshot_schema(tokens: set[tuple[str, str]]) -> bytes:
        return json.dumps(sorted([list(row) for row in tokens]),
                          separators=(",", ":")).encode("utf-8")
