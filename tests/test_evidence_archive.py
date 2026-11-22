"""Non-production evidence archive regression tests (no network or market data)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.check_evidence_records import validate_all, validate_record
from scripts.preserve_run_evidence import archive_run


def test_public_aggregate_records_are_valid_and_referenced() -> None:
    assert len(validate_all()) == 4


def test_public_records_do_not_promote_negative_evidence(tmp_path: Path) -> None:
    source = Path("evidence/records/e6-2023-frozen-replication-pr62.json")
    record = json.loads(source.read_text(encoding="utf-8"))
    record["release_gates"]["real_orders"] = True
    with pytest.raises(ValueError, match="authorize"):
        validate_record(record)
    record["release_gates"]["real_orders"] = False
    record["net_pnl_by_model"]["volume_control"]["stress"] = 0.0
    with pytest.raises(ValueError, match="Decimal strings"):
        validate_record(record)


def _fake_e5_run(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    artifact = source / "report.json"
    artifact.write_text('{"synthetic":true}\n', encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "e5-research-v1",
        "run_id": "toy-e5-001",
        "code_sha": "synthetic-test",
        "artifact_sha256": {"report.json": digest},
        "research_data_release_verified": False,
    }
    (source / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    return source


def test_archive_metadata_only_by_default_and_immutable(tmp_path: Path) -> None:
    source = _fake_e5_run(tmp_path)
    archived = archive_run(source, tmp_path / "private")
    assert (archived / "manifest.json").is_file()
    assert (archived / "receipt.json").is_file()
    assert not (archived / "report.json").exists()
    receipt = json.loads((archived / "receipt.json").read_text())
    assert receipt["detailed_artifacts_included"] is False
    assert receipt["production_authorized"] is False
    with pytest.raises(FileExistsError):
        archive_run(source, tmp_path / "private")


def test_archive_opt_in_detail_copy_and_hash_check(tmp_path: Path) -> None:
    source = _fake_e5_run(tmp_path)
    archived = archive_run(source, tmp_path / "private", include_traces=True)
    assert (archived / "report.json").read_bytes() == (source / "report.json").read_bytes()
    (source / "report.json").write_text("tampered")
    with pytest.raises(ValueError, match="changed"):
        archive_run(source, tmp_path / "another-private", include_traces=True)


def test_archive_rejects_unsafe_run_identifiers(tmp_path: Path) -> None:
    source = _fake_e5_run(tmp_path)
    manifest = json.loads((source / "manifest.json").read_text())
    manifest["run_id"] = "../escape"
    (source / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="unsafe E5 run id"):
        archive_run(source, tmp_path / "private")


def test_archive_rejects_untracked_destination_inside_repository() -> None:
    with pytest.raises(ValueError, match="git-ignored private root"):
        from scripts.preserve_run_evidence import _safe_private_root
        _safe_private_root(Path(__file__).resolve().parents[1] / "evidence" / "illegal")
