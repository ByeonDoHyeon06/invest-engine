"""Adversarial, synthetic PIT universe/vintage/issuer data gate tests."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from invest_engine.core.codec import decode_event
from invest_engine.core.replay import canonical_bytes
from invest_engine.research.audit import verify_exported_artifacts
from invest_engine.research.experiment import run_experiment
from invest_engine.research.pit import (
    CorporateAction, CorporateActionCoverage, MarketVintage, PITEvidence,
    UniverseMembership,
)
from test_experiment_e5 import make_spec

T = datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)
KEY = "KR:KRX:SYN-E5"


def _iso(at: datetime) -> str:
    return at.isoformat()


def _records(events: tuple[object, ...]) -> list[dict[str, object]]:
    # Synthetic provider declarations; not independently verified historical data.
    records: list[dict[str, object]] = [
        {"kind": "membership", "instrument_key": KEY,
         "effective_from": _iso(T - timedelta(days=1)),
         "effective_until": _iso(T + timedelta(days=1)),
         "published_at": _iso(T - timedelta(days=2)),
         "received_at": _iso(T - timedelta(days=2)),
         "source": "synthetic-universe", "included": True},
        {"kind": "action_coverage", "instrument_key": KEY,
         "start": _iso(T - timedelta(minutes=1)), "end": _iso(T + timedelta(hours=1)),
         "published_at": _iso(T - timedelta(days=1)),
         "received_at": _iso(T - timedelta(days=1)),
         "source": "synthetic-action-calendar"},
    ]
    for item in events:
        event = item
        records.append({
            "kind": "vintage", "event_id": event.event_id,
            "payload_sha256": hashlib.sha256(canonical_bytes(event)).hexdigest(),
            "revision": "original", "published_at": _iso(event.available_at),
            "received_at": _iso(event.received_at), "source": "synthetic-bars",
        })
    return records


def _prepare(tmp_path: Path) -> tuple[Path, list[dict[str, object]]]:
    config_path = make_spec(tmp_path)
    events = tuple(decode_event(x) for x in (tmp_path / "bars.jsonl").read_bytes().splitlines())
    records = _records(events)
    _persist(tmp_path, config_path, records)
    return config_path, records


def _persist(tmp_path: Path, config_path: Path, records: list[dict[str, object]]) -> None:
    file = tmp_path / "pit.jsonl"
    file.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in records), encoding="utf-8")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["pit_evidence"] = {
        "records_jsonl": "pit.jsonl",
        "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
        "source": "synthetic-evidence", "license": "synthetic-test",
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")


def test_cli_gate_valid_synthetic_evidence_and_artifact_hashes(tmp_path: Path):
    path, _ = _prepare(tmp_path)
    result = run_experiment(path)
    assert result.report.event_count == 3
    output = tmp_path / "report-out"
    gate = json.loads((output / "pit_gate.json").read_text())
    manifest = json.loads((output / "manifest.json").read_text())
    assert gate["event_count"] == 3
    assert gate["instrument_count"] == 1
    assert gate["data_release_verified"] is False
    assert manifest["pit_data_release_verified"] is False
    assert manifest["pit_dataset_file_sha256"]
    assert manifest["pit_gate_checked_events"] == 3
    assert verify_exported_artifacts(output)
    first = run_experiment(path)
    assert first.manifest_sha256 == result.manifest_sha256
    (output / "pit_gate.json").write_text("{}")
    with pytest.raises(ValueError, match="artifact mismatch"):
        verify_exported_artifacts(output)


@pytest.mark.parametrize("field,change,error", [
    ("published_at", timedelta(minutes=1), "PIT_VINTAGE"),
    ("received_at", timedelta(minutes=1), "PIT_VINTAGE"),
])
def test_retroactive_revision_never_visible_at_past_bar(
    tmp_path: Path, field: str, change: timedelta, error: str,
):
    path, rows = _prepare(tmp_path)
    vintage = rows[2]
    vintage[field] = _iso(datetime.fromisoformat(str(vintage[field])) + change)
    if field == "published_at":
        vintage["received_at"] = vintage[field]
    _persist(tmp_path, path, rows)
    with pytest.raises(ValueError, match=error):
        run_experiment(path)
    assert not (tmp_path / "report-out" / "report.json").exists()


def test_survivorship_bias_future_membership_and_delisting(tmp_path: Path):
    path, rows = _prepare(tmp_path)
    rows[0]["received_at"] = _iso(T + timedelta(hours=2))
    rows[0]["published_at"] = rows[0]["received_at"]
    _persist(tmp_path, path, rows)
    with pytest.raises(ValueError, match="PIT_UNIVERSE"):
        run_experiment(path)

    rows[0]["received_at"] = _iso(T - timedelta(days=2))
    rows[0]["published_at"] = rows[0]["received_at"]
    rows.append({
        "kind": "corporate_action", "action_id": "delisted",
        "instrument_key": KEY, "action_type": "DELIST",
        "effective_at": _iso(T + timedelta(minutes=2)),
        "published_at": _iso(T - timedelta(days=1)),
        "received_at": _iso(T - timedelta(days=1)),
        "source": "synthetic-issuer",
    })
    _persist(tmp_path, path, rows)
    with pytest.raises(ValueError, match="UNMODELED_CORPORATE_ACTION"):
        run_experiment(path)


@pytest.mark.parametrize("action", ["SPLIT", "CASH_DIVIDEND", "MERGER", "SYMBOL_CHANGE"])
def test_all_unmodeled_actions_fail_closed(tmp_path: Path, action: str):
    path, rows = _prepare(tmp_path)
    rows.append({
        "kind": "corporate_action", "action_id": "event-1",
        "instrument_key": KEY, "action_type": action,
        "effective_at": _iso(T + timedelta(minutes=1)),
        "published_at": _iso(T - timedelta(hours=1)),
        "received_at": _iso(T - timedelta(hours=1)),
        "source": "synthetic-issuer",
    })
    _persist(tmp_path, path, rows)
    with pytest.raises(ValueError, match="UNMODELED_CORPORATE_ACTION"):
        run_experiment(path)


def test_missing_action_coverage_and_wrong_bar_checksum(tmp_path: Path):
    path, rows = _prepare(tmp_path)
    rows.pop(1)
    _persist(tmp_path, path, rows)
    with pytest.raises(ValueError, match="PIT_ACTION_COVERAGE"):
        run_experiment(path)
    rows = _prepare(tmp_path)[1]
    rows[2]["payload_sha256"] = "f" * 64
    _persist(tmp_path, path, rows)
    with pytest.raises(ValueError, match="PIT_VINTAGE"):
        run_experiment(path)


def test_evidence_hash_and_record_schema_reject_tamper(tmp_path: Path):
    path, rows = _prepare(tmp_path)
    (tmp_path / "pit.jsonl").write_text("{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        run_experiment(path)
    rows[1]["unexpected"] = "extra"
    _persist(tmp_path, path, rows)
    with pytest.raises(ValueError, match="record fields"):
        run_experiment(path)


def test_empty_and_ambiguous_memberships_rejected():
    membership = UniverseMembership(KEY, T, T+timedelta(days=1), T, T, "synthetic", True)
    coverage = CorporateActionCoverage(KEY, T, T+timedelta(days=1), T, T, "synthetic")
    with pytest.raises(ValueError, match="overlapping universe"):
        PITEvidence((membership, membership), (), (), ())
    with pytest.raises(ValueError, match="overlapping action coverage"):
        PITEvidence((membership,), (), (), (coverage, coverage))
    with pytest.raises(ValueError, match="duplicate market vintage"):
        old = MarketVintage("x", "0"*64, "v1", T, T, "synthetic")
        PITEvidence((), (old, old), (), ())
    with pytest.raises(ValueError, match="unknown corporate action type"):
        CorporateAction("x", KEY, "TOTALLY_UNKNOWN", T, T, T, "synthetic")


def test_vintage_must_exist_for_every_market_event(tmp_path: Path):
    path, rows = _prepare(tmp_path)
    rows.pop()
    _persist(tmp_path, path, rows)
    with pytest.raises(ValueError, match="PIT_VINTAGE"):
        run_experiment(path)


def test_legacy_run_remains_valid_and_unattested(tmp_path: Path):
    path = make_spec(tmp_path)
    run_experiment(path)
    manifest = json.loads((tmp_path / "report-out" / "manifest.json").read_text())
    assert "PIT_EVIDENCE_NOT_SUPPLIED" in manifest["warnings"]
    assert manifest["pit_evidence_sha256"] is None
    assert verify_exported_artifacts(tmp_path / "report-out")
