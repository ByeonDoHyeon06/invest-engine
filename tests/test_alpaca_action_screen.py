"""Fail-closed economic-date classification of retrospective provider actions."""
from datetime import date
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from alpaca_raw_minute_pilot import classify_actions  # noqa: E402

FIRST = date(2022, 9, 1)
LAST = date(2022, 10, 31)


def action(ex="2022-08-25", record="2022-08-25", pay="2022-08-26", **changes):
    return {"symbol": "TSLA", "currency": "USD", "cusip": "SYNTHETIC", "foreign": False, "ex_date": ex,
            "record_date": record, "payable_date": pay, **changes}


def check(record, kind="forward_splits"):
    return classify_actions({kind: [record]}, "TSLA", FIRST, LAST)[0]["classification"]


def test_wholly_outside_window_and_processing_date_not_economic():
    assert check(action(process_date="2022-09-01")) == "OUTSIDE_WINDOW"
    assert check(action("2022-11-03", "2022-11-04", "2022-11-05")) == "OUTSIDE_WINDOW"


def test_overlap_inclusive_and_entitlement_payment_crossing():
    assert check(action(pay="2022-09-01")) == "INTERSECTS_WINDOW"
    assert check(action("2022-08-30", "2022-08-31", "2022-11-02"), "cash_dividends") == "INTERSECTS_WINDOW"
    assert check(action(effective_date="2022-10-31")) == "INTERSECTS_WINDOW"


def test_unknown_missing_and_identity_fail_closed():
    assert check(action(), "name_changes") == "UNRESOLVED"
    assert check(action(ex=None)) == "UNRESOLVED"
    assert check(action(currency="KRW")) == "UNRESOLVED"
    assert check(action(symbol="OTHER")) == "UNRESOLVED"
    with pytest.raises(ValueError, match="UNVERIFIABLE"):
        classify_actions({"cash_dividends": None}, "TSLA", FIRST, LAST)
    assert classify_actions({}, "TSLA", FIRST, LAST) == []


def test_optional_currency_is_not_imputed_and_due_bill_interval_is_checked():
    record = action()
    del record["currency"]
    output = classify_actions({"forward_splits": [record]}, "TSLA", FIRST, LAST)[0]
    assert output["classification"] == "OUTSIDE_WINDOW"
    assert output["currency_basis"] == "UNSPECIFIED_DATE_ONLY"
    assert check(action(currency=None, pay="2022-09-01")) == "INTERSECTS_WINDOW"
    assert check(action(currency=None, foreign=True)) == "UNRESOLVED"
    assert check(action(currency=None, cusip="")) == "UNRESOLVED"
    assert check(action(due_bill_on_date="2022-09-01")) == "UNRESOLVED"
    assert check(action(due_bill_on_date="2022-08-30",
                        due_bill_off_date="2022-09-02")) == "INTERSECTS_WINDOW"
