from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO

from invest_engine.cli import main


def test_synthetic_cli_is_deterministic() -> None:
    first = StringIO()
    second = StringIO()
    with redirect_stdout(first):
        assert main(["replay-synthetic", "--count", "500", "--market", "KR"]) == 0
    with redirect_stdout(second):
        assert main(["replay-synthetic", "--count", "500", "--market", "KR"]) == 0
    assert first.getvalue() == second.getvalue()
    report = json.loads(first.getvalue())
    assert report["count"] == 500
    assert len(report["state_hash"]) == 64
