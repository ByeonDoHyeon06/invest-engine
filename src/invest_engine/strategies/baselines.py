"""No-trade baseline for E4/E5 comparisons."""
from __future__ import annotations

from invest_engine.domain.events import EventEnvelope, MarketPayload
from invest_engine.domain.primitives import Market
from invest_engine.strategies.contracts import (
    DataRequirement, StrategyContext, StrategyManifest, StrategySignal,
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
