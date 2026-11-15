from __future__ import annotations

import pytest

from invest_engine.domain.primitives import InstrumentId, Market


@pytest.fixture
def kr_instrument() -> InstrumentId:
    return InstrumentId(
        market=Market.KR,
        venue="KRX",
        identifier="KR-SYN-0001",
        symbol="005930",
        currency="KRW",
    )


@pytest.fixture
def us_instrument() -> InstrumentId:
    return InstrumentId(
        market=Market.US,
        venue="XNAS",
        identifier="US-SYN-0001",
        symbol="AAPL",
        currency="USD",
    )
