"""Provider-neutral raw records and historical data capability contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Mapping, Protocol

from invest_engine.domain.errors import InvalidEvent, UnsupportedData
from invest_engine.domain.primitives import InstrumentId, Market, utc_datetime

SUPPORTED_KINDS = frozenset({"trade", "quote", "book", "bar", "status"})


@dataclass(frozen=True, slots=True)
class RawMarketRecord:
    """Provider adapter output: explicit event identity, timing and raw payload.

    Payload values are copied to avoid the producer mutating a buffered event.
    The normalizer accepts only schema-defined keys and strictly typed values.
    """

    event_id: str
    source: str
    kind: str
    instrument_id: InstrumentId | None
    event_time: datetime
    available_at: datetime
    received_at: datetime
    ingest_ordinal: int
    payload: Mapping[str, object]
    source_sequence: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in SUPPORTED_KINDS:
            raise UnsupportedData(f"unsupported raw data kind: {self.kind}")
        if not isinstance(self.payload, Mapping):
            raise InvalidEvent("raw payload must be a mapping")
        object.__setattr__(self, "payload", dict(self.payload))
        for field_name in ("event_time", "available_at", "received_at"):
            object.__setattr__(
                self, field_name, utc_datetime(getattr(self, field_name), field=field_name)
            )


@dataclass(frozen=True, slots=True)
class DataRequest:
    market: Market
    event_kind: str
    start: datetime
    end: datetime
    resolution: timedelta | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.market, Market):
            raise InvalidEvent("invalid market")
        if self.event_kind not in SUPPORTED_KINDS:
            raise UnsupportedData("unsupported requested data kind")
        object.__setattr__(self, "start", utc_datetime(self.start, field="request.start"))
        object.__setattr__(self, "end", utc_datetime(self.end, field="request.end"))
        if self.end <= self.start:
            raise InvalidEvent("end must be after start")
        if self.event_kind != "bar" and self.resolution is not None:
            raise InvalidEvent("resolution is only valid for bar requests")
        if self.resolution is not None and self.resolution <= timedelta(0):
            raise InvalidEvent("resolution must be positive")


@dataclass(frozen=True, slots=True)
class DataCapability:
    market: Market
    event_kind: str
    resolutions: frozenset[timedelta] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.market, Market) or self.event_kind not in SUPPORTED_KINDS:
            raise InvalidEvent("invalid data capability")
        if self.event_kind != "bar" and self.resolutions:
            raise InvalidEvent("only bar capabilities may list resolutions")
        if any(step <= timedelta(0) for step in self.resolutions):
            raise InvalidEvent("resolutions must be positive")

    def supports(self, request: DataRequest) -> bool:
        return (
            self.market == request.market
            and self.event_kind == request.event_kind
            and (
                request.resolution is None
                or (request.event_kind == "bar" and request.resolution in self.resolutions)
            )
        )


class HistoricalDataProvider(Protocol):
    """Read-only historical provider. Streaming uses a separate E7 interface."""

    def capabilities(self) -> frozenset[DataCapability]: ...

    def iter_records(self, request: DataRequest) -> Iterable[RawMarketRecord]: ...


def require_capability(provider: HistoricalDataProvider, request: DataRequest) -> None:
    if not any(item.supports(request) for item in provider.capabilities()):
        raise UnsupportedData(
            f"provider cannot serve {request.market.value}/{request.event_kind}/"
            f"{request.resolution}"
        )
