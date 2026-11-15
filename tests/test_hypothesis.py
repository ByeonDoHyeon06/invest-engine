"""Optional property tests; CI installs Hypothesis while isolated hosts may lack it."""

from __future__ import annotations

from decimal import Decimal

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, strategies as st  # noqa: E402

from invest_engine.domain.primitives import Money  # noqa: E402


@given(
    st.decimals(min_value="-1000000", max_value="1000000", allow_nan=False, allow_infinity=False, places=6),
    st.decimals(min_value="-1000000", max_value="1000000", allow_nan=False, allow_infinity=False, places=6),
)
def test_money_add_and_subtract_is_exact(a: Decimal, b: Decimal) -> None:
    first, second = Money(a, "USD"), Money(b, "USD")
    assert (first + second - second).amount == a
