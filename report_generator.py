"""Statistics computation engine for Strava club activities."""
from datetime import datetime, timezone, timedelta
from collections import defaultdict


def compute_stats(activities: list, members: list = None, name_map: dict = None, uc_map: dict = None) -> dict:
    """
    Compute all statistics from club activities.
    members: optional member list (for building Strava profile links).
    """
    # Build name -> athlete id map from members (if available)
    member_map = {}
    if members:
        for m in members:
            key = f"{m.get('firstname', '')} {m.get('lastname', '')}".strip().lower()
            if m.get("id"):
                member_map[key] = m["id"]
    if not activities:
        return {}

    total_km = 0.0
    total_elev = 0.0
    athlete_km: dict       = defaultdict(float)
    athlete_elev: dict     = defaultdict(float)
    athlete_time: dict     = defaultdict(float)
    athlete_speeds: dict   = defaultdict(list)
    athlete_count_acts: dict = defaultdict(int)
    athlete_longest: dict  = defaultdict(float)
    athlete_id: dict = {}
    athlete_ebike_acts: dict = defaultdict(int)
    athlete_devices: dict = defaultdict(set)

    # Stats excluding e-bike runs — used for awards
    award_km: dict        = defaultdict(float)
    award_elev: dict      = defaultdict(float)
    award_time: dict      = defaultdict(float)
    award_speeds: dict    = defaultdict(list)
    award_count_acts: dict = defaultdict(int)
    award_longest: dict   = defaultdict(float)

    # Climber — only runs with >= 8 m+/km (real hills)
    climber_run_elev: dict = defaultdict(float)
    climber_run_km: dict   = defaultdict(float)

    for act in activities:
        athlete = act.get("athlete", {})
        fname = athlete.get("firstname", "?")
        lname = athlete.get("lastname", "")
        name = f"{fname} {lname}".strip()
        dist_km = act.get("distance", 0) / 1000
        elev = act.get("total_elevation_gain", 0)
        time_s = act.get("moving_time", 0)
        speed = (act.get("distance", 0) / time_s) if time_s > 0 else 0
        is_ebike = act.get("type") == "EBikeRide"
        if name not in athlete_id and name in member_map:
            athlete_id[name] = member_map[name]
        if name_map:
            name = name_map.get(name.lower().strip(), name)

        dev = act.get("device_name", "")

        total_km += dist_km
        total_elev += elev
        athlete_km[name]         += dist_km
        athlete_elev[name]       += elev
        athlete_time[name]       += time_s
        athlete_count_acts[name] += 1
        if is_ebike:
            athlete_ebike_acts[name] += 1
        if dist_km > athlete_longest[name]:
            athlete_longest[name] = dist_km
        if speed > 0 and dist_km > 0.5:
            athlete_speeds[name].append(speed)
        if dev:
            athlete_devices[name].add(dev)

        if not is_ebike:
            award_km[name]         += dist_km
            award_elev[name]       += elev
            award_time[name]       += time_s
            award_count_acts[name] += 1
            if dist_km > award_longest[name]:
                award_longest[name] = dist_km
            if speed > 0 and dist_km > 0.5:
                award_speeds[name].append(speed)
            if dist_km >= 5 and dist_km > 0 and (elev / dist_km) >= 8:
                climber_run_elev[name] += elev
                climber_run_km[name]   += dist_km

    def top(d, reverse=True):
        return sorted(d.items(), key=lambda x: x[1], reverse=reverse)

    avg_speeds = {
        name: sum(s) / len(s)
        for name, s in athlete_speeds.items() if s
    }

    award_avg_speeds = {
        name: sum(s) / len(s)
        for name, s in award_speeds.items() if s
    }

    def fmt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h {m}m"

    def spd_kmh(ms: float) -> str:
        return f"{ms * 3.6:.1f} km/h"

    # Device stats — count unique runners per device
    device_athlete_count: dict = defaultdict(int)
    for _name, devs in athlete_devices.items():
        for dev in devs:
            device_athlete_count[dev] += 1

    def _device_sort(item):
        d, c = item
        dl = d.lower()
        if "strava" in dl:
            return (3, 0, dl)
        if "rouvy" in dl:
            return (2, 0, dl)
        if "zwift" in dl:
            return (1, 0, dl)
        return (0, -c, dl)

    device_stats = [
        {"device": d, "count": c}
        for d, c in sorted(device_athlete_count.items(), key=_device_sort)
        if d
    ]

    km_rank = top(athlete_km)

    # Award rankings — non-ebike activities only
    award_km_rank    = top(award_km)
    award_elev_rank  = top(award_elev)
    award_time_rank  = top(award_time)
    award_fast_rank  = top(award_avg_speeds)
    award_long_rank  = top(award_longest)

    # Leaderboard — all runners sorted by km
    leader_km = km_rank[0][1] if km_rank else 0
    leaderboard = []
    for name, km in km_rank:
        gap = leader_km - km
        total_acts = athlete_count_acts[name]
        ebike_acts = athlete_ebike_acts[name]
        mostly_ebike = total_acts > 0 and (ebike_acts / total_acts) > 0.5
        leaderboard.append({
            "name": name,
            "athlete_id": athlete_id.get(name),
            "km": round(km, 1),
            "elev": round(athlete_elev[name]),
            "time": fmt_time(athlete_time[name]),
            "time_s": int(athlete_time[name]),
            "acts": athlete_count_acts[name],
            "avg_speed": spd_kmh(avg_speeds[name]) if name in avg_speeds else "–",
            "avg_speed_ms": round(avg_speeds[name], 4) if name in avg_speeds else 0,
            "longest": round(athlete_longest[name], 1),
            "gap": f"–{gap:.1f}" if gap > 0 else "leader",
            "ebike": mostly_ebike,
            "elev_per_km": round(athlete_elev[name] / km, 1) if km > 0 else None,
            "unit":    uc_map.get(name, {}).get("unit", "")    if uc_map else "",
            "company": uc_map.get(name, {}).get("company", "") if uc_map else "",
        })

    # Add zero-row entries for members with no activities this period
    active_names = {r["name"] for r in leaderboard}
    if members:
        for m in members:
            name = f"{m.get('firstname', '')} {m.get('lastname', '')}".strip()
            if name_map:
                name = name_map.get(name.lower().strip(), name)
            if name and name not in active_names:
                leaderboard.append({
                    "name": name,
                    "athlete_id": member_map.get(name),
                    "km": 0.0,
                    "elev": 0,
                    "time": "0h 0m",
                    "time_s": 0,
                    "acts": 0,
                    "avg_speed": "–",
                    "avg_speed_ms": 0,
                    "longest": 0.0,
                    "gap": f"–{leader_km:.1f}" if leader_km > 0 else "leader",
                    "ebike": False,
                    "elev_per_km": None,
                    "unit":    uc_map.get(name, {}).get("unit", "")    if uc_map else "",
                    "company": uc_map.get(name, {}).get("company", "") if uc_map else "",
                })

    def award(rank, val_fn):
        if not rank:
            return None
        name, val = rank[0]
        return {"name": name, "athlete_id": athlete_id.get(name), "value": val_fn(val)}

    # Fun stats
    virtual_counts: dict = defaultdict(int)
    ebike_counts: dict   = defaultdict(int)
    break_time: dict     = defaultdict(float)

    for act in activities:
        athlete = act.get("athlete", {})
        fname = athlete.get("firstname", "?")
        lname = athlete.get("lastname", "")
        name  = f"{fname} {lname}".strip()
        atype   = act.get("type", "")
        elapsed = act.get("elapsed_time", 0)
        moving  = act.get("moving_time", 0)

        if atype == "VirtualRide":
            virtual_counts[name] += 1
        if atype == "EBikeRide":
            ebike_counts[name] += 1
        break_time[name] += max(0, elapsed - moving)

    # Climber — avg m+/km from runs with >= 8 m+/km, at least 30 km total
    elev_per_km: dict = {}
    for name in climber_run_km:
        if climber_run_km[name] >= 30:
            elev_per_km[name] = climber_run_elev[name] / climber_run_km[name]

    break_rank   = top(break_time)
    climber_rank = top(elev_per_km)

    def fun(name, value):
        return {"name": name, "value": value}

    fun_stats = {
        "virtual": fun(
            top(virtual_counts)[0][0] if virtual_counts else None,
            f"{top(virtual_counts)[0][1]}x Zwift/Rouvy",
        ) if virtual_counts else None,

        "ebike": fun(
            top(ebike_counts)[0][0] if ebike_counts else None,
            f"{top(ebike_counts)[0][1]}x e-bike",
        ) if ebike_counts else None,

        "breaks": fun(
            break_rank[0][0],
            f"{int(break_rank[0][1]//60)} min of rest",
        ) if break_rank and break_rank[0][1] > 60 else None,
    }

    climber_award = None
    if climber_rank and climber_rank[0][1] > 5:
        name, val = climber_rank[0]
        climber_award = {"name": name, "athlete_id": athlete_id.get(name), "value": f"{val:.1f} m+/km"}

    # Flat runner — lowest m+/km, at least 50 km (non-ebike runs)
    flatrunner_rank = top(
        {n: award_elev[n] / award_km[n] for n in award_km if award_km[n] >= 50},
        reverse=False
    )
    flatrunner_award = None
    if flatrunner_rank:
        name, val = flatrunner_rank[0]
        flatrunner_award = {"name": name, "athlete_id": athlete_id.get(name), "value": f"{val:.1f} m+/km"}

    return {
        "total_km": total_km,
        "total_elev": total_elev,
        "run_count": len(activities),
        "athlete_count": len(members) if members else len(athlete_km),
        "leaderboard": leaderboard,
        "fun_stats": fun_stats,
        # Main awards — non-ebike activities only
        "king_km":     award(award_km_rank,    lambda v: f"{v:.1f} km"),
        "king_elev":   award(award_elev_rank,  lambda v: f"{v:,.0f} m elevation".replace(",", " ")),
        "marathoner":  award(award_time_rank,  lambda v: fmt_time(v)),
        "fastest":     award(award_fast_rank,  lambda v: spd_kmh(v)),
        "longest":     award(award_long_rank,  lambda v: f"{v:.1f} km"),
        "climber":     climber_award,
        "flatrunner":  flatrunner_award,
        "device_stats": device_stats,
    }
