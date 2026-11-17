"""Deterministic E5 research input/output audit; no external provider attestation.

This module verifies *internal* consistency and content hashes. It cannot
establish whether a source is licensed, point-in-time adjusted, or complete.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from invest_engine.data.calendar import StaticSessionCalendar
from invest_engine.domain.events import Bar, BarKind, EventEnvelope, MarketPayload
from invest_engine.research.report import canonical_json


@dataclass(frozen=True, slots=True)
class BarCoverage:
    instrument_key: str
    interval_microseconds: int
    session_start: str
    observed_bars: int
    missing_intervals: int
    first_start: str
    last_end: str


@dataclass(frozen=True, slots=True)
class ResearchAudit:
    event_count: int
    bar_count: int
    coverage: tuple[BarCoverage, ...]
    gap_count: int
    warnings: tuple[str, ...]
    release_data_verified: bool = False


def source_tree_sha256() -> str:
    """Hash installed Python sources. This is NOT proof of a matching Git SHA."""
    package = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for file in sorted(package.rglob('*.py')):
        rel = file.relative_to(package).as_posix()
        blob = file.read_bytes()
        digest.update(rel.encode('utf-8') + b'\0')
        digest.update(len(blob).to_bytes(8, 'big') + blob)
    return digest.hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_dataset(
    events: tuple[EventEnvelope[MarketPayload], ...], calendar: StaticSessionCalendar,
) -> ResearchAudit:
    """Look for intra-session bar gaps, keeping different intervals separated.

    The dataset may intentionally contain a partial session. Such a range is
    explicitly flagged instead of filled with synthetic OHLCV prices.
    """
    groups: dict[tuple[str, int, str], list[Bar]] = {}
    bounds: dict[tuple[str, int, str], tuple[datetime, datetime]] = {}
    total = 0
    for event in events:
        bar = event.payload
        if not isinstance(bar, Bar) or bar.kind is not BarKind.TIME:
            continue
        if event.instrument_id is None:
            raise ValueError('bar requires instrument identity')
        session = calendar.session_for(event.instrument_id, bar.start)
        if session is None or bar.end > session.end:
            raise ValueError('bar lies outside declared historical sessions')
        step = bar.interval // timedelta(microseconds=1)
        key = (event.instrument_id.key, step, session.start.isoformat())
        groups.setdefault(key, []).append(bar)
        bounds[key] = (session.start, session.end)
        total += 1
    coverage: list[BarCoverage] = []
    gap_count = 0
    partial = False
    for (instrument, interval, start), series in sorted(groups.items()):
        series.sort(key=lambda bar: bar.start)
        missing = 0
        for left, right in zip(series, series[1:], strict=False):
            if left.end > right.start:
                raise ValueError('overlapping / duplicate bars in a session')
            gap = right.start - left.end
            if gap > timedelta(0):
                gap_count += 1
                missing += max(1, int(gap // timedelta(microseconds=interval)))
        session_begin, session_end = bounds[(instrument, interval, start)]
        if series[0].start != session_begin or series[-1].end != session_end:
            partial = True
        coverage.append(BarCoverage(instrument, interval, start, len(series), missing,
                                    series[0].start.isoformat(), series[-1].end.isoformat()))
    warnings = [
        'SOURCE_LICENSE_NOT_INDEPENDENTLY_VERIFIED',
        'CORPORATE_ACTIONS_AND_PRICE_ADJUSTMENT_UNVERIFIED',
        'POINT_IN_TIME_UNIVERSE_NOT_VERIFIED',
        'MARKET_SPECIFIC_FEES_TAX_AND_FX_NOT_VERIFIED',
        'CALENDAR_SOURCE_NOT_INDEPENDENTLY_VERIFIED',
    ]
    if gap_count:
        warnings.append('BAR_GAPS_DETECTED')
    if partial:
        warnings.append('PARTIAL_SESSION_COVERAGE')
    if total == 0:
        warnings.append('NO_TIME_BARS_IN_DATASET')
    return ResearchAudit(len(events), total, tuple(coverage), gap_count, tuple(warnings))


def verify_exported_artifacts(directory: Path) -> bool:
    """Verify file-level checksums (not cryptographic producer authenticity)."""
    import json

    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    hashes = manifest.get('artifact_sha256')
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError('manifest lacks E5.4 artifact integrity record')
    for name, expected in hashes.items():
        if (name not in {'report.json', 'decisions.jsonl', 'fills.jsonl',
                         'equity.jsonl', 'audit.json'} or
                not isinstance(expected, str) or len(expected) != 64):
            raise ValueError('invalid artifact checksum entry')
        file = directory / name
        if not file.is_file() or file_sha256(file) != expected:
            raise ValueError(f'artifact mismatch: {name}')
    return True


def audit_hash(audit: ResearchAudit) -> str:
    return hashlib.sha256(canonical_json(audit)).hexdigest()
