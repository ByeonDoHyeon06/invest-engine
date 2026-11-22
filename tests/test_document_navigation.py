"""Navigation and compatibility-link invariants for the curated documentation entry points."""
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


def test_main_document_navigation_links_resolve() -> None:
    for path in (ROOT / "README.md", ROOT / "docs/README.md", ROOT / "evidence/README.md"):
        for link in _local_links(path):
            assert link.exists(), f"broken reference in {path.relative_to(ROOT)}: {link}"


def test_archived_report_aliases_resolve_to_canonical_evidence() -> None:
    aliases = [p for p in (ROOT / "docs").glob("*.md")
               if p.read_text(encoding="utf-8").startswith("# Archived:")]
    assert aliases, "expected historic PR compatibility pointers"
    for alias in aliases:
        targets = _local_links(alias)
        assert len(targets) == 1
        target = targets[0]
        assert target.is_file(), f"missing archived report: {target}"
        assert (ROOT / "evidence") in target.parents
        assert target.read_text(encoding="utf-8").startswith("# ")
