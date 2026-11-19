"""E6.2 durable offline journal tests, all fixtures synthetic."""
from dataclasses import replace
import sqlite3

import pytest

from invest_engine.research.research_journal import ResearchJournal
from invest_engine.research.report import sha256
from test_research_candidates_e6 import DAY, arm, plan


def record_matrix(journal, p, split, names):
    for name in names:
        for cost in p.costs:
            journal.record(p.plan_id, arm(p, split, name, cost))


def test_durable_lifecycle_reopens_and_rejects_holdout_reuse(tmp_path):
    path = tmp_path / "research.db"
    p = plan()
    with ResearchJournal(path) as journal:
        first = journal.register(p)
        assert journal.register(p) == first
        with pytest.raises(ValueError, match="PLAN_ID_ALREADY_REGISTERED"):
            journal.register(replace(p, registered_at=p.registered_at-DAY))
        with pytest.raises(ValueError, match="TEST_REQUIRES_LOCKED"):
            journal.record(p.plan_id, arm(p, "test", "alpha", "base"))
        record_matrix(journal, p, "validation", ("no-trade", "buy-hold", "alpha", "beta"))
        locked = journal.lock_validation(p.plan_id)
        assert locked.locked_candidate == "alpha"
    with ResearchJournal(path) as journal:
        assert journal.get(p.plan_id) == locked
        with pytest.raises(ValueError, match="HOLDOUT_ALREADY_RESERVED"):
            journal.register(replace(p, plan_id="different"))
        with pytest.raises(ValueError, match="TEST_MATRIX_INCOMPLETE"):
            journal.finalize_test(p.plan_id)
        record_matrix(journal, p, "test", ("no-trade", "buy-hold", "alpha"))
        final = journal.finalize_test(p.plan_id)
        assert final.final_assessment.status == "RESEARCH_PASS"
    with ResearchJournal(path) as journal:
        assert journal.get(p.plan_id) == final
        with pytest.raises(ValueError, match="HOLDOUT_ALREADY_FINALIZED"):
            journal.finalize_test(p.plan_id)


def test_overlap_claim_blocks_new_training_even_with_new_dataset_hash(tmp_path):
    p = plan()
    windows = tuple(replace(w, start=w.start+20*DAY, end=w.end+20*DAY,
                            data_sha256=sha256(w.window_id)) for w in p.windows)
    other = replace(p, plan_id="other", windows=windows)
    with ResearchJournal(tmp_path / "db") as journal:
        journal.register(p)
        with pytest.raises(ValueError, match="HOLDOUT_ALREADY_RESERVED"):
            journal.register(other)


def test_idempotent_retransmission_and_failed_transaction_do_not_append(tmp_path):
    path = tmp_path / "db"
    p = plan()
    a = arm(p, "validation", "alpha", "base")
    with ResearchJournal(path) as journal:
        journal.register(p)
        saved = journal.record(p.plan_id, a)
        assert journal.record(p.plan_id, a) == saved
        with pytest.raises(ValueError, match="RUN_IDENTITY_REUSED"):
            journal.record(p.plan_id, replace(a, net_pnl=a.net_pnl+1))
        assert journal.get(p.plan_id) == saved
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM research_events").fetchone()[0] == 2


@pytest.mark.parametrize("sql", [
    "UPDATE research_events SET body=X'7B7D' WHERE seq=1",
    "DELETE FROM research_events WHERE seq=2",
    "UPDATE research_head SET digest='invalid' WHERE singleton=1",
])
def test_corrupted_body_truncation_or_head_is_detected(tmp_path, sql):
    path = tmp_path / "db"
    p = plan()
    with ResearchJournal(path) as journal:
        journal.register(p)
        journal.record(p.plan_id, arm(p, "validation", "alpha", "base"))
    with sqlite3.connect(path) as db:
        db.execute(sql)
    with ResearchJournal(path) as journal, pytest.raises(ValueError, match="RESEARCH_"):
        journal.get(p.plan_id)


def test_two_connections_do_not_overwrite_evidence(tmp_path):
    path = tmp_path / "db"
    p = plan()
    with ResearchJournal(path) as a, ResearchJournal(path) as b:
        a.register(p)
        a.record(p.plan_id, arm(p, "validation", "alpha", "base"))
        b.record(p.plan_id, arm(p, "validation", "alpha", "stress"))
        assert len(a.get(p.plan_id).evidence) == 2
        assert a.get(p.plan_id) == b.get(p.plan_id)
