"""E5.4 audit and assumption-sensitivity golden/regression cases."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path

import pytest

from invest_engine.cli import main
from invest_engine.core.replay import canonical_bytes
from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import InstrumentId, Market
from invest_engine.research.audit import (inspect_dataset, source_tree_sha256,
                                          verify_exported_artifacts)
from invest_engine.research.experiment import run_experiment
from invest_engine.research.stress import CostScenario, run_cost_stress
from test_experiment_e5 import make_spec

T = datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc)
STEP = timedelta(minutes=1)
INST = InstrumentId(Market.KR, 'KRX', 'E5-AUDIT', 'SYN', 'KRW')


def bars_for_audit() -> tuple[EventEnvelope, ...]:
    events = []
    for n in range(3):
        start = T + n * STEP
        bar = Bar(start, start + STEP, D('100'), D('101'), D('99'),
                  D('100'), D('100'), interval=STEP)
        events.append(EventEnvelope(str(n), 'market.bar', 'synthetic', INST,
                                    bar.end, bar.end, bar.end, n, bar))
    return tuple(events)


def test_audit_records_gaps_without_fabricating_ohlcv() -> None:
    calendar = StaticSessionCalendar((TradingSession(Market.KR, 'KRX', T, T+3*STEP),))
    full = inspect_dataset(bars_for_audit(), calendar)
    assert full.gap_count == 0
    assert full.bar_count == 3
    assert full.coverage[0].missing_intervals == 0
    assert 'PARTIAL_SESSION_COVERAGE' not in full.warnings
    partial = inspect_dataset((bars_for_audit()[0], bars_for_audit()[2]), calendar)
    assert partial.bar_count == 2
    assert partial.gap_count == 1
    assert partial.coverage[0].missing_intervals == 1
    assert 'BAR_GAPS_DETECTED' in partial.warnings
    assert partial.release_data_verified is False
    with pytest.raises(ValueError, match='overlapping'):
        inspect_dataset((bars_for_audit()[0], bars_for_audit()[0]), calendar)


def test_audit_refuses_unknown_session_and_coverage_is_per_interval() -> None:
    calendar = StaticSessionCalendar((TradingSession(Market.KR, 'KRX', T, T+3*STEP),))
    missing = replace(bars_for_audit()[0], payload=replace(
        bars_for_audit()[0].payload,
        start=T-timedelta(minutes=1), end=T,
    ))
    with pytest.raises(ValueError, match='outside'):
        inspect_dataset((missing,), calendar)
    one = inspect_dataset((bars_for_audit()[1],), calendar)
    assert 'PARTIAL_SESSION_COVERAGE' in one.warnings


def test_export_manifest_is_deterministic_and_detects_tampering(tmp_path: Path) -> None:
    spec = make_spec(tmp_path)
    first = run_experiment(spec)
    folder = tmp_path / 'report-out'
    manifest = json.loads((folder / 'manifest.json').read_text())
    audit = json.loads((folder / 'audit.json').read_text())
    assert verify_exported_artifacts(folder)
    assert len(manifest['code_tree_sha256']) == 64
    assert manifest['code_tree_sha256'] == source_tree_sha256()
    assert manifest['research_data_release_verified'] is False
    assert audit['release_data_verified'] is False
    assert 'CORPORATE_ACTIONS_AND_PRICE_ADJUSTMENT_UNVERIFIED' in audit['warnings']
    assert len(manifest['artifact_sha256']) == 5
    assert run_experiment(spec).manifest_sha256 == first.manifest_sha256
    (folder / 'fills.jsonl').write_bytes(b'TAMPER\n')
    with pytest.raises(ValueError, match='artifact mismatch'):
        verify_exported_artifacts(folder)


def test_cost_stress_invariant_data_and_original_output_untouched(tmp_path: Path) -> None:
    spec = make_spec(tmp_path)
    original = run_experiment(spec)
    original_report = (tmp_path / 'report-out/report.json').read_bytes()
    source_file = (tmp_path / 'bars.jsonl').read_bytes()
    result = run_cost_stress(spec)
    repeat = run_cost_stress(spec)
    assert result == repeat
    assert result.result_sha256 == repeat.result_sha256
    assert result.dataset_file_sha256 == hashlib.sha256(source_file).hexdigest()
    assert result.outcomes[0].run_sha256 == original.report.run_sha256
    assert len(result.outcomes) == 4
    assert 'INCONCLUSIVE_NO_TRADES' in result.warnings
    assert (tmp_path / 'report-out/report.json').read_bytes() == original_report
    assert (tmp_path / 'bars.jsonl').read_bytes() == source_file
    assert all(case.net_pnl == (('KRW', D(0)),) for case in result.outcomes)


def test_stress_invalid_scenarios_and_live_refused(tmp_path: Path) -> None:
    config = make_spec(tmp_path)
    with pytest.raises(ValueError, match='base assumptions'):
        run_cost_stress(config, (CostScenario('modified'),))
    with pytest.raises(ValueError, match='duplicate'):
        run_cost_stress(config, (CostScenario('baseline'), CostScenario('baseline')))
    with pytest.raises(ValueError, match=r'positive|within|\(0,1\]'):
        CostScenario('bad', participation_scale=D('0'))
    raw = json.loads(config.read_text())
    raw['mode'] = 'LIVE'
    config.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match='only offline'):
        run_cost_stress(config)


def test_stress_cli_outputs_scenarios_without_changing_baseline(tmp_path: Path,
                                                                  capsys: pytest.CaptureFixture[str]) -> None:
    path = make_spec(tmp_path)
    out = tmp_path / 'research' / 'stress.json'
    assert main(['stress', '--config', str(path), '--output', str(out)]) == 0
    response = json.loads(capsys.readouterr().out)
    exported = json.loads(out.read_text())
    assert response['scenario_count'] == 4
    assert response['result_sha256'] == exported['result_sha256']
    assert exported['outcomes'][0]['name'] == 'baseline'
    assert exported['outcomes'][3]['name'] == 'joint_adverse'
    assert len({x['name'] for x in exported['outcomes']}) == 4


def test_actual_strategy_signal_affects_stress_costs(tmp_path: Path) -> None:
    """Use the existing ORB baseline instead of relying on a no-trade fixture."""
    path = make_spec(tmp_path)
    spec = json.loads(path.read_text())
    spec['strategy'] = {
        'id':'orb-long','version':'1.0.0',
        'parameters': {'interval':'PT1M','opening_kr':'PT5M','opening_us':'PT15M',
                       'prior_sessions':20, 'volume_multiplier':'1.5',
                       'target_fraction':'0.05','atr_period':14},
    }
    # Reuse known-safe synthetic breakout fixture semantics from E5.1 tests.
    events = []
    sessions = []
    for day in range(21):
        begin = T + timedelta(days=day)
        end = begin + timedelta(hours=1)
        sessions.append({'market':'KR', 'venue':'KRX', 'start':begin.isoformat(),
                         'end':end.isoformat()})
        for minute in range(7):
            start = begin + minute*STEP
            breakout = day == 20 and minute == 5
            after = day == 20 and minute == 6
            bar = Bar(start, start+STEP, D('99'),
                      D('105') if after else D('102') if breakout else D('100'),
                      D('95'), D('100') if after else D('101') if breakout else D('99'),
                      D('1000') if after else D('30') if breakout else D('10'), interval=STEP)
            events.append(EventEnvelope(f'orb:{day}:{minute}', 'market.bar', 'synthetic', INST,
                                        bar.end, bar.end, bar.end, len(events), bar))
    spec['sessions'] = sessions
    spec['account']['instruments'][0]['identifier'] = INST.identifier
    dataset = tmp_path/'bars.jsonl'
    dataset.write_bytes(b''.join(canonical_bytes(ev)+b'\n' for ev in events))
    spec['dataset']['sha256'] = hashlib.sha256(dataset.read_bytes()).hexdigest()
    path.write_text(json.dumps(spec))
    result = run_cost_stress(path)
    assert result.outcomes[0].entry_fills >= 1
    assert result.outcomes[0].net_pnl != result.outcomes[1].net_pnl or (
        result.outcomes[0].entry_fills != result.outcomes[1].entry_fills
    )
    assert all(case.run_sha256 for case in result.outcomes)


def test_stress_cannot_overwrite_input_config_or_dataset(tmp_path: Path) -> None:
    spec = make_spec(tmp_path)
    report = run_cost_stress(spec)
    from invest_engine.research.stress import export_stress

    original_config = spec.read_bytes()
    original_dataset = (tmp_path / 'bars.jsonl').read_bytes()
    for path in (spec, tmp_path / 'bars.jsonl'):
        with pytest.raises(ValueError, match='overwrite'):
            export_stress(report, path, config_file=spec)
    assert original_config == spec.read_bytes()
    assert original_dataset == (tmp_path / 'bars.jsonl').read_bytes()
