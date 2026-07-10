"""Self-check for generate.merge_ledger — run with: python3 test/test_ledger.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from generate import merge_ledger, dedup_consecutive


def act(first, last="", km=5.0, t=1000, dev="Watch", typ="Run"):
    return {
        "athlete": {"firstname": first, "lastname": last},
        "type": typ,
        "distance": km * 1000,
        "moving_time": t,
        "elapsed_time": t,
        "total_elevation_gain": 10,
        "device_name": dev,
    }


def test_empty_ledger_bootstraps_everything():
    fresh = [act("A"), act("B"), act("C")]
    merged, missed = merge_ledger([], fresh, "2026-07-06T10:00")
    assert len(merged) == 3
    assert not missed
    assert all(e["ingested_at"] == "2026-07-06T10:00" for e in merged)


def test_anchor_found_appends_only_new():
    ledger = [
        {**act("C"), "ingested_at": "T0"},
        {**act("B"), "ingested_at": "T0"},
        {**act("A"), "ingested_at": "T0"},
    ]
    fresh = [act("E"), act("D"), act("C"), act("B"), act("A")]
    merged, missed = merge_ledger(ledger, fresh, "T1")
    assert not missed
    assert len(merged) == 5
    assert [m["athlete"]["firstname"] for m in merged] == ["E", "D", "C", "B", "A"]
    assert merged[0]["ingested_at"] == "T1"
    assert merged[2]["ingested_at"] == "T0"  # pre-existing entry untouched


def test_anchor_missing_falls_back_to_full_append():
    ledger = [
        {**act("Z"), "ingested_at": "T0"},
        {**act("Y"), "ingested_at": "T0"},
        {**act("X"), "ingested_at": "T0"},
    ]
    fresh = [act("New1"), act("New2")]  # anchor nowhere to be found
    merged, missed = merge_ledger(ledger, fresh, "T1")
    assert missed
    assert len(merged) == 5
    assert [m["athlete"]["firstname"] for m in merged[:2]] == ["New1", "New2"]


def test_anchor_missing_does_not_duplicate_known_activities():
    # e.g. an anchored activity was edited/deleted on Strava, breaking the
    # anchor match, even though most of the fresh fetch overlaps the ledger.
    ledger = [
        {**act("C"), "ingested_at": "T0"},
        {**act("B"), "ingested_at": "T0"},
        {**act("A"), "ingested_at": "T0"},
    ]
    fresh = [act("New1"), act("New2"), act("C"), act("B")]  # A deleted/edited on Strava
    merged, missed = merge_ledger(ledger, fresh, "T1")
    assert missed
    assert len(merged) == 5  # New1, New2 + C, B, A once each — not duplicated
    assert [m["athlete"]["firstname"] for m in merged] == ["New1", "New2", "C", "B", "A"]


def test_dedup_consecutive_collapses_same_batch_same_athlete():
    a = {**act("A", km=4.1127), "name": "Morning Run", "ingested_at": "2026-07-09T08:48"}
    b = {**act("A", km=4.1215), "name": "Morning Run", "ingested_at": "2026-07-09T08:48"}
    clean = dedup_consecutive([b, a])
    assert len(clean) == 1
    assert clean[0]["distance"] == 4121.5


def test_dedup_consecutive_keeps_separate_batches_and_athletes():
    a1 = {**act("A"), "name": "Morning Run", "ingested_at": "2026-07-08T08:00"}
    a2 = {**act("A"), "name": "Morning Run", "ingested_at": "2026-07-09T08:00"}
    b1 = {**act("B"), "name": "Morning Run", "ingested_at": "2026-07-09T08:00"}
    clean = dedup_consecutive([a1, a2, b1])
    assert len(clean) == 3


def test_dedup_consecutive_requires_adjacency_not_just_same_batch():
    # A's two runs are in the same batch but another athlete's activity was
    # uploaded in between — not list-adjacent, so they must NOT merge.
    a1 = {**act("A", km=4.1127), "name": "Morning Run", "ingested_at": "2026-07-09T08:48"}
    b1 = {**act("B"), "name": "Morning Run", "ingested_at": "2026-07-09T08:48"}
    a2 = {**act("A", km=4.1215), "name": "Morning Run", "ingested_at": "2026-07-09T08:48"}
    clean = dedup_consecutive([a1, b1, a2])
    assert len(clean) == 3


if __name__ == "__main__":
    test_empty_ledger_bootstraps_everything()
    test_anchor_found_appends_only_new()
    test_anchor_missing_falls_back_to_full_append()
    test_anchor_missing_does_not_duplicate_known_activities()
    test_dedup_consecutive_collapses_same_batch_same_athlete()
    test_dedup_consecutive_keeps_separate_batches_and_athletes()
    test_dedup_consecutive_requires_adjacency_not_just_same_batch()
    print("All ledger tests passed.")
