"""No-trade baseline for E4/E5 comparisons."""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

from invest_engine.domain.events import Bar, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import Market, _decimal
from invest_engine.strategies.contracts import (
    DataRequirement, SignalDirection, StrategyContext, StrategyManifest, StrategySignal,
)


class NoTradeStrategy:
    def __init__(self, requirement: DataRequirement) -> None:
        self._manifest = StrategyManifest(
            "no-trade", "1.0.0", frozenset((Market.KR, Market.US)), (requirement,)
        )

    @property
    def manifest(self) -> StrategyManifest:
        return self._manifest

    def on_event(self, event: EventEnvelope[MarketPayload],
                 context: StrategyContext) -> tuple[StrategySignal, ...]:
        return ()

    def snapshot(self) -> bytes:
        return b"{}"

    def restore(self, data: bytes) -> None:
        if data != b"{}":
            raise ValueError("invalid no-trade strategy snapshot")


class BuyHoldBaseline:
    """One initial limit-order proposal per instrument, then hold; no forced fill."""

    def __init__(self, interval: timedelta, target_fraction: Decimal,
                 stop_fraction: Decimal) -> None:
        self.params = (interval, target_fraction, stop_fraction)
        if not (0 < _decimal(target_fraction, field="target_fraction") <= 1
                and 0 < _decimal(stop_fraction, field="stop_fraction") < 1):
            raise ValueError("invalid buy-hold baseline fractions")
        self._manifest = StrategyManifest(
            "buy-hold-baseline", "1.0.0", frozenset((Market.KR, Market.US)),
            (DataRequirement("market.bar", interval),),
        )
        self._attempted: set[str] = set()

    @property
    def manifest(self) -> StrategyManifest:
        return self._manifest

    def on_event(self, event: EventEnvelope[MarketPayload],
                 context: StrategyContext) -> tuple[StrategySignal, ...]:
        instrument = event.instrument_id
        if (instrument is None or not isinstance(event.payload, Bar)
                or context.session is None or context.as_of >= context.session.end
                or instrument.key in self._attempted):
            return ()
        _, target, stop = self.params
        self._attempted.add(instrument.key)
        return (StrategySignal(
            "buy-hold:" + instrument.key, self.manifest.strategy_id, self.manifest.version,
            instrument, SignalDirection.LONG, target, context.as_of, context.session.end,
            event.event_id, stop_price=event.payload.close * (1 - stop),
            reason_codes=("INITIAL_ENTRY_AND_HOLD",),
        ),)

    def snapshot(self) -> bytes:
        return json.dumps(sorted(self._attempted), separators=(",", ":")).encode()

    def restore(self, data: bytes) -> None:
        value = json.loads(data)
        if (not isinstance(value, list) or not all(isinstance(x, str) and x for x in value)
                or sorted(set(value)) != value
                or json.dumps(value, separators=(",", ":")).encode() != data):
            raise ValueError("invalid buy-hold snapshot")
        self._attempted = set(value)
