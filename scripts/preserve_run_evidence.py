"""Immutable, local-only retention of E5 RunExperiment output artifacts.

This command never downloads data, submits orders or uploads any artifact. Full
artifacts may contain licensed data or private investment research. The caller
is responsible for allowed retention; preserve privately and never commit them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

CANONICAL_FILES = frozenset({
    "report.json", "audit.json", "pit_gate.json",
    "decisions.jsonl", "fills.jsonl", "equity.jsonl", "fx_equity.jsonl",
})
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _safe_private_root(dest: Path) -> None:
    """Refuse accidental copies into tracked repository paths."""
    here = Path(__file__).resolve().parents[1]
    resolved = dest.resolve()
    if resolved == here or here in resolved.parents:
        rel = resolved.relative_to(here)
        if not rel.parts or rel.parts[0] not in {"artifacts", "experiments", "reports", "data"}:
            raise ValueError("archive destination inside repo must use a git-ignored private root")
    if resolved.is_symlink():
        raise ValueError("archive destination may not be a symlink")


def archive_run(run_dir: Path, private_root: Path, *, include_traces: bool = False) -> Path:
    """Copy a verified snapshot; no overwrite and no network. Return archive directory.

    Default stores E5 manifest and checksums only (not trade traces/report).
    With explicit rights check, include_traces=True preserves all verified
    per-order artifacts too; only canonical E5 files are allowed.
    """
    run = run_dir.resolve(strict=True)
    dest = private_root.resolve()
    _safe_private_root(dest)
    m = run / "manifest.json"
    if m.is_symlink() or not m.is_file():
        raise ValueError("E5 manifest missing or symlinked")
    payload = m.read_bytes()
    manifest = json.loads(payload)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "e5-research-v1":
        raise ValueError("E5 manifest schema mismatch")
    rid = manifest.get("run_id")
    if not isinstance(rid, str) or not SAFE_ID.fullmatch(rid) or rid in {".", ".."}:
        raise ValueError("unsafe E5 run id")
    artifacts = manifest.get("artifact_sha256")
    if not isinstance(artifacts, dict) or not artifacts or not set(artifacts) <= CANONICAL_FILES:
        raise ValueError("unexpected E5 artifact set")
    for name, want in artifacts.items():
        if not isinstance(want, str) or not SHA256.fullmatch(want):
            raise ValueError("artifact hash missing or malformed")
        src = run / name
        if src.is_symlink() or not src.is_file() or _sha(src) != want:
            raise ValueError("missing or changed E5 artifact: " + name)
    mh = hashlib.sha256(payload).hexdigest()
    final = dest / rid / mh
    if final.exists():
        raise FileExistsError("immutable experiment archive already exists")
    (dest / rid).mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=dest / rid))
    try:
        (stage / "manifest.json").write_bytes(payload)
        copied = {"manifest.json": mh}
        if include_traces:
            for name, checksum in sorted(artifacts.items()):
                shutil.copyfile(run / name, stage / name)
                if _sha(stage / name) != checksum:
                    raise ValueError("archive copy mismatch")
                copied[name] = checksum
        receipt = {
            "schema_version": "private-e5-archive-v1",
            "run_id": rid,
            "source_manifest_sha256": mh,
            "artifacts_in_original_run": dict(sorted(artifacts.items())),
            "files_retained": copied,
            "detailed_artifacts_included": include_traces,
            "actual_data_provenance_certified": False,
            "production_authorized": False,
        }
        (stage / "receipt.json").write_text(
            json.dumps(receipt, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if final.exists():
            raise FileExistsError("concurrent archive already exists")
        os.rename(stage, final)
        return final
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main() -> int:
    parser = argparse.ArgumentParser(description="Privately preserve an E5 run; no upload")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument(
        "--include-traces", action="store_true",
        help="copy private report and trade traces too; verify retention/data rights first",
    )
    args = parser.parse_args()
    path = archive_run(args.run_dir, args.private_root, include_traces=args.include_traces)
    print("Immutable local archive:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
