"""Standalone checks for generate.build_grouped_data / build_daily_history.
Run: python test/test_build_grouped_data.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from collections import defaultdict

import generate


def _act(name, km=5.0, elev=0, moving_time=1800, ingested_at=None, atype="Run"):
    fname, lname = name.split(" ", 1)
    act = {"athlete": {"firstname": fname, "lastname": lname}, "distance": km * 1000,
           "moving_time": moving_time, "elapsed_time": moving_time,
           "total_elevation_gain": elev, "type": atype}
    if ingested_at:
        act["ingested_at"] = ingested_at
    return act


def test_group_split():
    uc_map = {
        "SAR FORTY": {"unit": "40SAR", "company": "Hercules"},
        "SAR FORTYONE": {"unit": "41SAR", "company": "Glory"},
        "SAB EIGHT": {"unit": "8SAB", "company": "Comd Office"},
        "NOUNIT RUNNER": {"unit": "", "company": ""},
    }
    acts = [_act("SAR FORTY"), _act("SAR FORTYONE"), _act("SAB EIGHT"), _act("NOUNIT RUNNER")]
    members = [{"firstname": n.split()[0], "lastname": n.split()[1]} for n in uc_map]

    result = generate.build_grouped_data(acts, members, "test", name_map=None, uc_map=uc_map)

    assert {"all", "nsf", "nsmen"} <= result.keys()

    all_names = {r["name"] for r in result["all"]["leaderboard"]}
    assert all_names == set(uc_map.keys()), all_names

    nsf_names = {r["name"] for r in result["nsf"]["leaderboard"]}
    assert nsf_names == {"SAR FORTY"}, nsf_names

    nsmen_names = {r["name"] for r in result["nsmen"]["leaderboard"]}
    assert nsmen_names == {"SAR FORTYONE", "SAB EIGHT"}, nsmen_names

    # unlabelled runner appears only in 'all'
    assert "NOUNIT RUNNER" not in nsf_names and "NOUNIT RUNNER" not in nsmen_names

    print("OK: build_grouped_data splits units correctly")


def test_totals_match_manual_sum():
    """Per-athlete km/elev/time/acts/longest in the leaderboard must equal a
    plain re-sum of the source activities — for all, nsf and nsmen alike."""
    uc_map = {
        "SAR FORTY": {"unit": "40SAR", "company": "Hercules"},
        "SAR FORTYONE": {"unit": "41SAR", "company": "Glory"},
    }
    acts = [
        _act("SAR FORTY", km=5.0, elev=50, moving_time=1500),
        _act("SAR FORTY", km=8.2, elev=90, moving_time=2400),
        _act("SAR FORTY", km=2.0, elev=10, moving_time=600),
        _act("SAR FORTYONE", km=10.0, elev=120, moving_time=3000),
    ]
    members = [{"firstname": "SAR", "lastname": "FORTY"}, {"firstname": "SAR", "lastname": "FORTYONE"}]

    result = generate.build_grouped_data(acts, members, "test", name_map=None, uc_map=uc_map)

    # manual re-sum straight from the source activities, independent of compute_stats
    manual_km, manual_elev, manual_time, manual_acts, manual_longest = (
        defaultdict(float), defaultdict(float), defaultdict(float), defaultdict(int), defaultdict(float))
    for a in acts:
        name = f"{a['athlete']['firstname']} {a['athlete']['lastname']}"
        km = a["distance"] / 1000
        manual_km[name] += km
        manual_elev[name] += a["total_elevation_gain"]
        manual_time[name] += a["moving_time"]
        manual_acts[name] += 1
        manual_longest[name] = max(manual_longest[name], km)

    for group in ("all", "nsf", "nsmen"):
        for row in result[group]["leaderboard"]:
            name = row["name"]
            if manual_acts[name] == 0:
                continue  # zero-row entry for a member with no activity in this group
            assert row["km"] == round(manual_km[name], 1), (group, name, row["km"], manual_km[name])
            assert row["elev"] == round(manual_elev[name]), (group, name, row["elev"], manual_elev[name])
            assert row["time_s"] == int(manual_time[name]), (group, name, row["time_s"], manual_time[name])
            assert row["acts"] == manual_acts[name], (group, name, row["acts"], manual_acts[name])
            assert row["longest"] == round(manual_longest[name], 1), (group, name, row["longest"], manual_longest[name])

    # aggregate totals must equal the sum of the leaderboard rows shown
    for group in ("all", "nsf", "nsmen"):
        lb = result[group]["leaderboard"]
        assert round(result[group]["total_km"], 1) == round(sum(r["km"] for r in lb), 1), group
        assert round(result[group]["total_elev"]) == round(sum(r["elev"] for r in lb)), group

    print("OK: leaderboard totals match a manual re-sum of source activities")


def test_group_membership_is_disjoint_and_subset():
    """Every athlete is in at most one of nsf/nsmen, and each group's totals
    never exceed the 'all' bucket's totals."""
    uc_map = {
        "A ONE": {"unit": "40SAR", "company": "C1"},
        "B TWO": {"unit": "41SAR", "company": "C2"},
        "C THREE": {"unit": "8SAB", "company": "C3"},
        "D FOUR": {"unit": "OTHERUNIT", "company": "C4"},
    }
    acts = [_act(n, km=3.0) for n in uc_map]
    members = [{"firstname": n.split()[0], "lastname": n.split()[1]} for n in uc_map]

    result = generate.build_grouped_data(acts, members, "test", name_map=None, uc_map=uc_map)
    nsf_names = {r["name"] for r in result["nsf"]["leaderboard"]}
    nsmen_names = {r["name"] for r in result["nsmen"]["leaderboard"]}

    assert nsf_names.isdisjoint(nsmen_names), (nsf_names, nsmen_names)
    assert (nsf_names | nsmen_names) <= {r["name"] for r in result["all"]["leaderboard"]}
    assert result["nsf"]["total_km"] <= result["all"]["total_km"]
    assert result["nsmen"]["total_km"] <= result["all"]["total_km"]
    assert result["nsf"]["total_km"] + result["nsmen"]["total_km"] <= result["all"]["total_km"] + 1e-9

    print("OK: nsf/nsmen membership is disjoint and totals never exceed 'all'")


def test_build_daily_history_is_cumulative():
    """Each historical date's stats must only include activities ingested by
    that date (strictly cumulative, no leakage from later dates)."""
    uc_map = {"A ONE": {"unit": "40SAR", "company": "C1"}}
    ledger = [
        _act("A ONE", km=3.0, ingested_at="2026-06-01T09:00"),
        _act("A ONE", km=4.0, ingested_at="2026-06-01T18:00"),
        _act("A ONE", km=5.0, ingested_at="2026-06-03T09:00"),
    ]
    members = [{"firstname": "A", "lastname": "ONE"}]

    history = generate.build_daily_history(ledger, members, name_map=None, uc_map=uc_map)

    assert set(history.keys()) == {"2026-06-01", "2026-06-03"}, history.keys()

    day1 = history["2026-06-01"]["all"]["leaderboard"][0]
    assert day1["km"] == round(3.0 + 4.0, 1), day1
    assert day1["acts"] == 2, day1

    day3 = history["2026-06-03"]["all"]["leaderboard"][0]
    assert day3["km"] == round(3.0 + 4.0 + 5.0, 1), day3
    assert day3["acts"] == 3, day3

    # nsf bucket must be cumulative too, and consistent with 'all' for this single-athlete case
    assert history["2026-06-01"]["nsf"]["leaderboard"][0]["km"] == day1["km"]
    assert history["2026-06-03"]["nsf"]["leaderboard"][0]["km"] == day3["km"]

    print("OK: build_daily_history is strictly cumulative per date")


def test_against_real_clean_ledger():
    """Load the actual production clean ledger (if present) and independently
    re-sum per-athlete km straight from the raw entries, comparing against
    both build_grouped_data('today') and every date in build_daily_history()."""
    ledger = generate.load_ledger(generate.CLEAN_LEDGER_PATH)
    if not ledger:
        print("SKIP: no src/ledger-clean.json found")
        return

    name_map, uc_map = generate.load_nominal_roll()
    members = []  # zero-row entries aren't needed for this check

    def manual_km_by_name(subset):
        totals = defaultdict(float)
        for a in subset:
            ath = a.get("athlete", {})
            name = generate._resolve_name(
                f"{ath.get('firstname', '?')} {ath.get('lastname', '')}".strip(), name_map)
            totals[name] += a.get("distance", 0) / 1000
        return totals

    # 'today' (full ledger) must match a plain re-sum
    today = generate.build_grouped_data(ledger, members, "today", name_map, uc_map)
    manual_today = manual_km_by_name(ledger)
    for row in today["all"]["leaderboard"]:
        expected = round(manual_today.get(row["name"], 0.0), 1)
        assert row["km"] == expected, (row["name"], row["km"], expected)
    assert len(today["all"]["leaderboard"]) == len(manual_today)

    # every historical date must match a re-sum of entries ingested by that date
    history = generate.build_daily_history(ledger, members, name_map, uc_map)
    checked_dates = 0
    for date_str, snap in history.items():
        subset = [a for a in ledger if a.get("ingested_at", "")[:10] <= date_str]
        manual = manual_km_by_name(subset)
        for row in snap["all"]["leaderboard"]:
            expected = round(manual.get(row["name"], 0.0), 1)
            assert row["km"] == expected, (date_str, row["name"], row["km"], expected)
        assert len(snap["all"]["leaderboard"]) == len(manual)
        checked_dates += 1

    print(f"OK: real clean ledger totals verified for 'today' and {checked_dates} historical dates")


def demo():
    test_group_split()
    test_totals_match_manual_sum()
    test_group_membership_is_disjoint_and_subset()
    test_build_daily_history_is_cumulative()
    test_against_real_clean_ledger()


if __name__ == "__main__":
    demo()
