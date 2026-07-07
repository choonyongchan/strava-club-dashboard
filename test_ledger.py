"""Self-check for generate.merge_ledger — run with: python3 test_ledger.py"""
from generate import merge_ledger


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


if __name__ == "__main__":
    test_empty_ledger_bootstraps_everything()
    test_anchor_found_appends_only_new()
    test_anchor_missing_falls_back_to_full_append()
    test_anchor_missing_does_not_duplicate_known_activities()
    print("All ledger tests passed.")
