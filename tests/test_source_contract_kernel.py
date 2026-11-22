"""Value-only E1/E5 source identity compatibility tests; no IO/strategy execution."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from invest_engine.contracts.source import (
    HistoricalSourceIdentity,
    from_e1_manifest,
    from_e5_dataset,
)
from invest_engine.data.datasets import (
    AdjustmentPolicy, DataCompleteness, DatasetManifest, DatasetSpec,
)
from invest_engine.domain.primitives import Market


def test_e1_dataset_identity_is_explicitly_parquet() -> None:
    start = datetime(2022, 1, 1, tzinfo=timezone.utc)
    spec = DatasetSpec(
        dataset_id="synthetic-test-01", provider="fake",
        license_id="synthetic", market=Market.US, event_kind="bar",
        coverage_start=start, coverage_end=start + timedelta(days=2),
        calendar_version="toy-calendar", adjustment=AdjustmentPolicy.RAW,
        completeness=DataCompleteness.UNVERIFIED,
    )
    m = DatasetManifest(spec, 3, 3, "a" * 64, "b" * 64)
    a, b = from_e1_manifest(m), from_e1_manifest(m)
    assert a == b
    assert a.digest == b.digest
    assert a.format == "e1-normalized-parquet"
    assert a.content_sha256 == "b" * 64
    assert a.volume_unit == "UNKNOWN"
    assert a.portable_values()["dataset_id"] == "synthetic-test-01"


def test_e5_tape_identity_keeps_format_and_volume_provenance_distinct() -> None:
    first = {"events_jsonl": "a.jsonl", "source": "fake", "license": "synthetic",
             "sha256": "b" * 64, "volume_unit": "SHARES"}
    a = from_e5_dataset(first)
    assert a.format == "e5-canonical-jsonl"
    assert a.digest == from_e5_dataset(dict(reversed(list(first.items())))).digest
    assert a.digest != from_e5_dataset({**first, "volume_unit": "TICK_COUNT"}).digest
    assert a.digest != from_e5_dataset({**first, "source": "other"}).digest
    assert a.content_sha256 == "b" * 64
    assert a.dataset_id is None
    assert "events_jsonl" not in a.portable_values()  # no absolute path leaks


def test_incompatible_formats_are_not_silently_collapsed() -> None:
    values = {"events_jsonl": "tape.jsonl", "source": "fake",
              "license": "synthetic", "sha256": "b" * 64}
    e5 = from_e5_dataset(values)
    with pytest.raises(ValueError, match="E1 package"):
        HistoricalSourceIdentity(
            format="e1-normalized-parquet", provider="fake", license_id="synthetic",
            content_sha256="b" * 64, volume_unit="UNKNOWN",
        )
    assert e5.format == "e5-canonical-jsonl"


def test_reject_fake_checksum_and_ambient_fields() -> None:
    value = {"events_jsonl": "tape.jsonl", "source": "fake",
             "license": "synthetic", "sha256": "b" * 64}
    with pytest.raises(ValueError, match="key set"):
        from_e5_dataset({**value, "broker_api_key": "prohibited"})
    with pytest.raises(ValueError, match="checksum"):
        from_e5_dataset({**value, "sha256": "bad"})
    with pytest.raises(ValueError, match="volume"):
        from_e5_dataset({**value, "volume_unit": "guessed"})
