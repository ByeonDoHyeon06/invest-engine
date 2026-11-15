"""A simulated monotonic UTC clock with optional injected market calendar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from invest_engine.domain.errors import InvalidEvent, UnsupportedData
from invest_engine.domain.primitives import Market, utc_datetime


class MarketCalendar(Protocol):
    """Exchange-specific open/closed logic belongs to an injected provider (E1)."""

    def is_open(self, market: Market, at: datetime) -> bool: ...


@dataclass(slots=True)
class ReplayClock:
    now: datetime
    calendar: MarketCalendar | None = None

    def __post_init__(self) -> None:
        self.now = utc_datetime(self.now, field="clock.now")

    def advance_to(self, instant: datetime) -> None:
        candidate = utc_datetime(instant, field="clock.advance_to")
        if candidate < self.now:
            raise InvalidEvent("replay clock cannot go backwards")
        self.now = candidate

    def is_market_open(self, market: Market) -> bool:
        if self.calendar is None:
            raise UnsupportedData("market calendar not provided")
        return self.calendar.is_open(market, self.now)
