from __future__ import annotations

from pathlib import Path


def test_no_broker_imports_or_live_credentials_in_core() -> None:
    root = Path(__file__).parents[1] / "src" / "invest_engine"
    for child in ("core", "domain"):
        for path in (root / child).glob("*.py"):
            content = path.read_text()
            assert "tossinvest" not in content
            assert "requests.post(" not in content
            assert "httpx." not in content
