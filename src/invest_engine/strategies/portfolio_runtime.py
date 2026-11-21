"""Fail-closed dispatcher for trusted universe-level research strategies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.events import EventEnvelope, MarketPayload
from invest_engine.domain.primitives import InstrumentId
from invest_engine.strategies.contracts import SignalDirection
from invest_engine.strategies.portfolio_contracts import (
    PortfolioSignalBatch,
    PortfolioStrategy,
    PortfolioStrategyContext,
    UniverseDecisionFrame,
    UniverseFrameOutcome,
    UniverseFrameStatus,
)
from invest_engine.strategies.universe import UniverseFrameCoordinator


@dataclass(frozen=True, slots=True)
class PortfolioEvaluation:
    frame_outcome: UniverseFrameOutcome
    batch: PortfolioSignalBatch | None = None
    reason_codes: tuple[str, ...] = ()


class PortfolioStrategyRunner:
    """Dispatch complete frames without owning allocation or trading state."""

    def __init__(
        self,
        strategy: PortfolioStrategy,
        coordinator: UniverseFrameCoordinator,
    ) -> None:
        self.strategy = strategy
        self.coordinator = coordinator
        self._halt_reason: str | None = None

    @property
    def halt_reason(self) -> str | None:
        return self._halt_reason or self.coordinator.halt_reason

    def accept(self, event: EventEnvelope[MarketPayload]) -> None:
        if self.halt_reason is not None:
            raise InvalidEvent(
                "portfolio strategy runner halted: restore by replay from trusted journal"
            )
        self.coordinator.accept(event)

    def invalidate_instrument_history(self, instrument: InstrumentId) -> None:
        self.coordinator.invalidate_instrument_history(instrument)

    def evaluate(self, as_of: datetime) -> PortfolioEvaluation:
        if self.halt_reason is not None:
            raise InvalidEvent(
                "portfolio strategy runner halted: restore by replay from trusted journal"
            )
        try:
            return self._evaluate(as_of)
        except Exception as exc:
            self._halt_reason = f"{type(exc).__name__}: {exc}"
            raise

    def _evaluate(self, as_of: datetime) -> PortfolioEvaluation:
        outcome = self.coordinator.finalize(as_of)
        if outcome.status is not UniverseFrameStatus.COMPLETE:
            return PortfolioEvaluation(outcome, reason_codes=outcome.reason_codes)
        if outcome.frame is None:
            raise InvalidEvent("complete universe outcome is missing its frame")

        context = PortfolioStrategyContext(
            outcome.as_of,
            outcome.frame,
            self.coordinator.observations,
        )
        batch = self.strategy.on_frame(outcome.frame, context)
        self._validate_batch(outcome.frame, batch)
        return PortfolioEvaluation(outcome, batch, batch.reason_codes)

    def _validate_batch(
        self,
        frame: UniverseDecisionFrame,
        batch: PortfolioSignalBatch,
    ) -> None:
        if not isinstance(batch, PortfolioSignalBatch):
            raise InvalidEvent("portfolio strategy batch has an invalid type")
        manifest = self.strategy.manifest
        if (
            batch.frame_id != frame.frame_id
            or batch.strategy_id != manifest.strategy_id
            or batch.strategy_version != manifest.version
            or batch.generated_at != frame.as_of
        ):
            raise InvalidEvent("portfolio strategy batch identity does not match frame")

        expected_keys = tuple(instrument.key for instrument in frame.instruments)
        actual_keys = tuple(signal.instrument.key for signal in batch.signals)
        if actual_keys != expected_keys:
            raise InvalidEvent(
                "portfolio strategy batch must cover the ordered universe exactly once"
            )

        for signal, trigger in zip(
            batch.signals,
            frame.trigger_bars,
            strict=True,
        ):
            if (
                signal.strategy_id != manifest.strategy_id
                or signal.strategy_version != manifest.version
                or signal.generated_at != frame.as_of
                or signal.trigger_event_id != trigger.event_id
                or signal.expires_at <= frame.as_of
            ):
                raise InvalidEvent(
                    "portfolio strategy batch child does not match frame context"
                )

        long_signals = tuple(
            signal
            for signal in batch.signals
            if signal.direction is SignalDirection.LONG
        )
        if len(long_signals) > manifest.max_long_positions:
            raise InvalidEvent(
                "portfolio strategy batch exceeds the LONG position limit"
            )
        gross_target = sum(
            (signal.target_fraction for signal in long_signals),
            Decimal(0),
        )
        if gross_target > manifest.max_gross_target_fraction:
            raise InvalidEvent(
                "portfolio strategy batch exceeds the gross target limit"
            )
