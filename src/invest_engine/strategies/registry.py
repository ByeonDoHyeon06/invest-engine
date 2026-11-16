"""Strategy plugin registry with immutable identity and duplicate protection."""
from __future__ import annotations

from invest_engine.strategies.contracts import Strategy


class StrategyRegistry:
    def __init__(self, strategies: tuple[Strategy, ...] = ()) -> None:
        self._plugins: dict[tuple[str, str], Strategy] = {}
        for strategy in strategies:
            self.register(strategy)

    def register(self, strategy: Strategy) -> None:
        key = (strategy.manifest.strategy_id, strategy.manifest.version)
        if key in self._plugins:
            raise ValueError("duplicate strategy id/version")
        self._plugins[key] = strategy

    def get(self, strategy_id: str, version: str) -> Strategy:
        try:
            return self._plugins[(strategy_id, version)]
        except KeyError as exc:
            raise KeyError("unknown strategy id/version") from exc

    def manifests(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self._plugins))
