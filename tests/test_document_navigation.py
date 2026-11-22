"""Validate root navigation, milestone docs and archived evidence references."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\]\(([^)]+)\)")


def _local_links(path: Path) -> list[Path]:
    links: list[Path] = []
    for value in LINK.findall(path.read_text(encoding="utf-8")):
        target = value.split("#", 1)[0]
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        links.append((path.parent / target).resolve())
    return links


def test_root_documentation_links_resolve() -> None:
    for path in (ROOT / "README.md", ROOT / "docs/README.md",
                 ROOT / "docs/milestones/README.md", ROOT / "evidence/README.md"):
        for link in _local_links(path):
            assert link.exists(), f"broken reference in {path.relative_to(ROOT)}: {link}"


def test_all_milestone_markdown_links_resolve() -> None:
    for path in (ROOT / "docs/milestones").rglob("*.md"):
        for link in _local_links(path):
            assert link.exists(), f"broken milestone link in {path.relative_to(ROOT)}: {link}"


def test_legacy_reports_are_not_duplicated_in_docs() -> None:
    assert not list((ROOT / "docs").glob("ALPACA_*.md"))
    assert not list((ROOT / "docs").glob("E[56]_*.md"))
    for name in ("E6_PROFITABILITY_AUDIT.md", "E6_6_REDUCED_TURNOVER.md"):
        assert (ROOT / "evidence/reports" / name).is_file()
    for name in ("KRUS_80_DATASET.md", "ALPACA_AUTHORIZED_DATA_AUDIT.md"):
        assert (ROOT / "evidence/data" / name).is_file()
