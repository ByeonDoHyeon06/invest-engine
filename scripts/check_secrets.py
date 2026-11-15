"""Simple tracked-file secret guard. Add specialized scanners before live trading."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Conservative checks; this is not a comprehensive secret detection service.
_BLOCKED_FILES = re.compile(r"(^|/)(\.env(?:\..*)?|[^/]+\.(?:pem|p12|pfx|key))$")
_SIGNATURES = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:toss_)?(?:client_secret|api_secret|api_key)\s*[:=]\s*['\"][A-Za-z0-9_-]{24,}['\"]"),
]


def main() -> int:
    result = subprocess.run(
        ["git", "ls-files", "-z"], check=True, capture_output=True
    )
    problems: list[str] = []
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        rel = raw_path.decode("utf-8", errors="replace")
        if _BLOCKED_FILES.search(rel) and not rel.endswith(".env.example"):
            problems.append(f"blocked tracked file: {rel}")
            continue
        content = Path(rel).read_bytes() if Path(rel).is_file() else b""
        if b"\0" in content:
            continue
        text = content.decode("utf-8", errors="replace")
        if any(rx.search(text) for rx in _SIGNATURES):
            problems.append(f"potential credential material: {rel}")
    if problems:
        print("\n".join(problems))
        return 1
    print("Tracked-file credential guard: no matching patterns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
