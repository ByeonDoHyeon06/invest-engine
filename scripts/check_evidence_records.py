"""Validate public, aggregate-only research evidence records without external packages.

This checks repository metadata shape, NOT historical market truth or data rights.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "evidence" / "records"
REQUIRED = frozenset({
    "schema_version", "study_id", "kind", "source_report",
    "source_report_original_git_blob_sha", "workflow_url", "pr_url",
    "reported_at", "data_basis", "data_retained_in_repository",
    "data_rights_certified", "historical_pit_certified",
    "executable_prices_certified", "real_broker_fees_verified",
    "accounts_are_independent", "compounded_portfolio_returns",
    "currency", "modeled_costs", "windows", "arms",
    "net_pnl_by_model", "conclusion", "release_gates",
})
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
ID = re.compile(r"[a-z0-9][a-z0-9-]{2,99}\Z")
DATE = re.compile(r"20\d{2}-\d{2}-\d{2}\Z")


def validate_record(value: object, *, root: Path = ROOT) -> str:
    if not isinstance(value, dict) or set(value) != REQUIRED:
        raise ValueError("evidence record shape mismatch")
    if value["schema_version"] != "evidence-summary-v1" or value["kind"] != "historical_research_summary":
        raise ValueError("unexpected evidence record version/kind")
    identifier = value["study_id"]
    if not isinstance(identifier, str) or not ID.fullmatch(identifier):
        raise ValueError("unsafe study id")
    if not isinstance(value["reported_at"], str) or not DATE.fullmatch(value["reported_at"]):
        raise ValueError("invalid reported date")
    if not isinstance(value["source_report_original_git_blob_sha"], str) or not SHA1.fullmatch(value["source_report_original_git_blob_sha"]):
        raise ValueError("invalid original report git blob sha")
    filename = value["source_report"]
    if not isinstance(filename, str) or not filename.startswith("evidence/reports/") or "/" in filename[len("evidence/reports/"):]:
        raise ValueError("source report must be archived report")
    if not (root / filename).is_file():
        raise ValueError("linked archived report missing")
    for key in ("workflow_url", "pr_url"):
        v = value[key]
        if not isinstance(v, str) or not v.startswith("https://github.com/ByeonDoHyeon06/invest-engine/"):
            raise ValueError("invalid repository evidence URL")
    for key in ("data_basis", "conclusion", "currency"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError("missing study metadata")
    if value["currency"] != "USD" or value["modeled_costs"] != ["base", "stress"]:
        raise ValueError("unrecognized currencies/cost modeling")
    safety = ("data_retained_in_repository", "data_rights_certified",
              "historical_pit_certified", "executable_prices_certified",
              "real_broker_fees_verified", "compounded_portfolio_returns")
    if any(value[k] is not False for k in safety) or value["accounts_are_independent"] is not True:
        raise ValueError("public evidence cannot claim unverified rights, execution or compounded returns")
    gates = value["release_gates"]
    if not isinstance(gates, dict) or set(gates) != {"e5_g1", "e6_g2", "paper", "real_orders"}:
        raise ValueError("release gates incomplete")
    if any(flag is not False for flag in gates.values()):
        raise ValueError("aggregates cannot authorize release or actual orders")
    for key in ("windows", "arms"):
        group = value[key]
        if not isinstance(group, dict) or not group:
            raise ValueError("missing window/arm counts")
        if any(not isinstance(n, int) or isinstance(n, bool) or n < 0 for n in group.values()):
            raise ValueError("counts must be nonnegative integers")
        if "planned" in group and "completed" in group and group["completed"] > group["planned"]:
            raise ValueError("completed count greater than planned")
        if "planned" in group and "eligible" in group and group["eligible"] > group["planned"]:
            raise ValueError("eligible count greater than planned")
    pnls = value["net_pnl_by_model"]
    if pnls is not None:
        if not isinstance(pnls, dict) or not pnls:
            raise ValueError("invalid model profit aggregates")
        for cases in pnls.values():
            if not isinstance(cases, dict) or set(cases) != {"base", "stress"}:
                raise ValueError("cost scenarios incomplete")
            for amount in cases.values():
                if not isinstance(amount, str):
                    raise ValueError("currency amounts must be Decimal strings")
                try:
                    n = Decimal(amount)
                except InvalidOperation as err:
                    raise ValueError("invalid Decimal amount") from err
                if not n.is_finite():
                    raise ValueError("non-finite performance amount")
    return identifier


def validate_all(*, root: Path = ROOT) -> tuple[str, ...]:
    records = sorted((root / "evidence" / "records").glob("*.json"))
    if not records:
        raise ValueError("no public evidence records")
    ids = [validate_record(json.loads(p.read_text(encoding="utf-8")), root=root) for p in records]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate study identity")
    for path, identifier in zip(records, ids, strict=True):
        if path.stem != identifier:
            raise ValueError("record filename does not match study identity")
    return tuple(ids)


if __name__ == "__main__":
    records = validate_all()
    print("Verified", len(records), "aggregate evidence records (not economic certification)")
