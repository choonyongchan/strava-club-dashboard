"""
Generate a static index.html from current Strava club data.
Run locally or via GitHub Actions (hourly cron).

Usage:
  python3 src/generate.py
"""
import json, math, csv
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

import config
import strava_client, report_generator

# ---------------------------------------------------------------------------
# Nominal roll — maps Strava truncated names to full formal names
# ---------------------------------------------------------------------------

# Which units belong to which dashboard group tab.
UNIT_GROUPS = {"nsf": {"40SAR"}, "nsmen": {"41SAR", "8SAB"}}

def _all_truncations(strava_name: str):
    """Yield every possible API-truncated form by splitting at each word boundary."""
    parts = strava_name.lower().split()
    yield strava_name.lower()  # ponytail: exact match first — handles full names returned by API
    if len(parts) < 2:
        return
    for i in range(1, len(parts)):
        prefix = " ".join(parts[:i])
        yield f"{prefix} {parts[i][0]}."

def load_nominal_roll(path=None) -> tuple:
    """Returns (name_map, unit_company_map) from a single read of nominal_roll.csv.

    name_map: {truncated_strava_name: FULL_NAME}
    unit_company_map: {FULL_NAME: {unit, company}}
    """
    if path is None:
        path = Path(__file__).parent / "nominal_roll.csv"
    name_map = {}
    unit_company_map = {}
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                strava = row.get("STRAVA username", "").strip()
                full = row.get("Name", "").strip()
                if strava and full:
                    for key in _all_truncations(strava):
                        name_map[key] = full
                if full:
                    unit_company_map[full] = {
                        "unit":    row.get("Unit", "").strip(),
                        "company": row.get("Company", "").strip(),
                    }
    except FileNotFoundError:
        pass
    return name_map, unit_company_map

# ---------------------------------------------------------------------------
# Weather — Open-Meteo (no API key needed)
# ---------------------------------------------------------------------------

WEATHER_CODES = {
    0: ("☀️", "Clear"), 1: ("🌤️", "Mostly clear"), 2: ("⛅", "Partly cloudy"),
    3: ("☁️", "Overcast"), 45: ("🌫️", "Fog"), 48: ("🌫️", "Rime fog"),
    51: ("🌦️", "Light drizzle"), 53: ("🌦️", "Drizzle"), 55: ("🌧️", "Heavy drizzle"),
    61: ("🌧️", "Light rain"), 63: ("🌧️", "Rain"), 65: ("🌧️", "Heavy rain"),
    71: ("🌨️", "Light snow"), 73: ("🌨️", "Snow"), 75: ("❄️", "Heavy snow"),
    80: ("🌦️", "Light showers"), 81: ("🌧️", "Showers"), 82: ("⛈️", "Heavy showers"),
    95: ("⛈️", "Thunderstorm"), 96: ("⛈️", "Thunderstorm w/ hail"), 99: ("⛈️", "Severe storm"),
}

def fetch_weather() -> dict:
    """Fetch current weather from Open-Meteo API."""
    try:
        import requests
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={config.WEATHER_LAT}&longitude={config.WEATHER_LON}"
            "&current=temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m"
            f"&wind_speed_unit=kmh&timezone={config.TIMEZONE}"
        )
        r = requests.get(url, timeout=8)
        c = r.json()["current"]
        code = int(c.get("weather_code", 0))
        icon, desc = WEATHER_CODES.get(code, ("🌡️", ""))
        return {
            "icon": icon,
            "desc": desc,
            "temp": round(c.get("temperature_2m", 0)),
            "wind": round(c.get("wind_speed_10m", 0)),
            "ok": True,
        }
    except Exception:
        return {"ok": False}

# ---------------------------------------------------------------------------
# Timestamp in configured timezone
# ---------------------------------------------------------------------------

def _now_tz() -> datetime:
    """Return current time in configured timezone, falling back to UTC."""
    try:
        import pytz
        return datetime.now(pytz.timezone(config.TIMEZONE))
    except Exception:
        return datetime.now(timezone.utc)


def now_label() -> tuple:
    """Return (iso_str, human_label) in configured timezone."""
    now = _now_tz()
    iso = now.strftime("%Y-%m-%dT%H:%M")
    human = f"{now.day}.{now.month}.{now.year} {now.hour:02}:{now.minute:02}"
    return iso, human


def _resolve_name(raw_name: str, name_map: dict = None) -> str:
    return name_map.get(raw_name.lower().strip(), raw_name) if name_map else raw_name


def build_grouped_data(acts: list, members: list, label: str, name_map: dict = None, uc_map: dict = None) -> dict:
    """Split acts/members by UNIT_GROUPS, returning {'all': stats, 'nsf': stats, 'nsmen': stats}."""
    def unit_of(name):
        return (uc_map or {}).get(name, {}).get("unit", "")

    def act_name(a):
        ath = a.get("athlete", {})
        return _resolve_name(f"{ath.get('firstname', '?')} {ath.get('lastname', '')}".strip(), name_map)

    def member_name(m):
        return _resolve_name(f"{m.get('firstname', '')} {m.get('lastname', '')}".strip(), name_map)

    def stats_for(filtered_acts, filtered_members):
        s = report_generator.compute_stats(filtered_acts, members=filtered_members, name_map=name_map, uc_map=uc_map)
        s["label"] = label
        s["count"] = len(filtered_acts)
        return make_json_safe(s)

    result = {"all": stats_for(acts, members)}
    for group, units in UNIT_GROUPS.items():
        result[group] = stats_for(
            [a for a in acts if unit_of(act_name(a)) in units],
            [m for m in (members or []) if unit_of(member_name(m)) in units],
        )
    return result


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__CLUB_NAME__ – Strava Dashboard</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🏃</text></svg>">

<meta property="og:title"       content="__CLUB_NAME__ – Weekly Strava Report">
<meta property="og:description" content="Live cycling stats for __CLUB_NAME__ from Strava.">
<meta property="og:type"        content="website">

<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Inter', -apple-system, sans-serif;
  background: #f0f2f5;
  min-height: 100vh;
  color: #1c1c1e;
}
a { color: inherit; text-decoration: none; }

/* NAV */
nav {
  background: white;
  border-bottom: 1px solid #eee;
  padding: 0 20px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 10;
  box-shadow: 0 1px 3px rgba(0,0,0,.06);
}
.nav-logo { display: flex; align-items: center; gap: 10px; }
.nav-badge {
  background: #FC4C02; color: white;
  font-weight: 800; font-size: 1rem;
  padding: 3px 8px; border-radius: 4px;
  letter-spacing: -.5px;
}
.nav-title { font-weight: 700; font-size: .9rem; color: #555; }
.nav-link {
  background: #FC4C02; color: white;
  padding: 6px 14px; border-radius: 6px;
  font-size: .78rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: .05em;
  transition: background .15s;
}
.nav-link:hover { background: #e04400; }

/* WRAP */
.wrap { max-width: 1120px; margin: 0 auto; padding: 28px 20px 48px; }

/* HEADER */
.header { margin-bottom: 20px; }
.header-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.header h1 { font-size: 1.5rem; font-weight: 800; }
.header .sub {
  color: #888; font-size: .82rem; margin-top: 8px;
  display: flex; align-items: center; gap: 6px;
}
.dot { width: 7px; height: 7px; border-radius: 50%; background: #FC4C02; }
.weather-widget {
  background: white; border-radius: 10px;
  padding: 8px 14px; font-size: .82rem; color: #555;
  box-shadow: 0 1px 4px rgba(0,0,0,.07);
  white-space: nowrap; flex-shrink: 0;
  display: flex; align-items: center; gap: 6px;
}

/* GROUP TABS */
.group-tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }
.group-tab {
  padding: 7px 14px; border-radius: 8px;
  font-size: .82rem; font-weight: 600;
  border: 1.5px solid #ddd; background: white;
  color: #666; cursor: pointer; transition: all .15s;
  white-space: nowrap;
}
.group-tab.active { background: #FC4C02; color: white; border-color: #FC4C02; }
.group-tab:not(.active):hover { border-color: #bbb; color: #333; }
.breadcrumb { font-size: .78rem; color: #999; margin-bottom: 10px; }
.breadcrumb .crumb-group { font-weight: 700; color: #FC4C02; }
.breadcrumb .crumb-sub { font-weight: 600; color: #666; }

/* CONTROLS ROW */
.controls-row {
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px; margin-bottom: 18px; flex-wrap: wrap;
}
.toggle { display: flex; gap: 6px; flex-wrap: wrap; }
.tab {
  padding: 7px 14px; border-radius: 8px;
  font-size: .82rem; font-weight: 600;
  border: 1.5px solid #ddd; background: white;
  color: #666; cursor: pointer; transition: all .15s;
  white-space: nowrap;
}
.tab.active { background: #FC4C02; color: white; border-color: #FC4C02; }
.tab:not(.active):hover { border-color: #bbb; color: #333; }


/* TOTALS */
.totals { display: grid; grid-template-columns: repeat(4,1fr); gap: 10px; margin-bottom: 22px; }
.total-card {
  background: white; border-radius: 12px;
  padding: 16px 10px; text-align: center;
  box-shadow: 0 1px 4px rgba(0,0,0,.07);
}
.total-card .val { font-size: 1.55rem; font-weight: 800; color: #FC4C02; }
.total-card .lbl { font-size: .75rem; color: #777; margin-top: 3px; }

/* HISTORY — modal */
.history-wrap { position: relative; display: inline-block; }
.history-picker {
  display: none; position: fixed;
  top: 50%; left: 50%; transform: translate(-50%, -50%);
  background: white; border-radius: 18px;
  box-shadow: 0 16px 60px rgba(0,0,0,.25);
  padding: 20px; z-index: 200;
  width: 340px; max-width: calc(100vw - 32px);
  max-height: 80vh; overflow-y: auto;
}
.history-picker.open { display: block; }
.history-picker-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 14px;
}
.history-picker-title {
  font-size: .7rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .08em; color: #999; margin: 0;
}
.history-picker-close {
  background: none; border: none; cursor: pointer;
  font-size: 1.1rem; color: #bbb; padding: 2px 6px;
  border-radius: 6px; line-height: 1;
}
.history-picker-close:hover { background: #f5f5f5; color: #555; }
.hist-year-label {
  font-size: .72rem; font-weight: 700; color: #555;
  margin: 10px 0 6px; letter-spacing: .04em;
}
.hist-year-label:first-of-type { margin-top: 0; }
.hist-grid {
  display: grid; grid-template-columns: repeat(8, 1fr); gap: 4px;
}
.hist-cal-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 8px;
}
.hist-cal-month { font-size: .8rem; font-weight: 700; color: #333; }
.hist-cal-nav {
  background: none; border: none; cursor: pointer;
  font-size: 1rem; font-weight: 700; color: #777; padding: 2px 10px;
  border-radius: 6px; line-height: 1.4;
}
.hist-cal-nav:hover:not(:disabled) { background: #f5f5f5; color: #333; }
.hist-cal-nav:disabled { color: #ddd; cursor: default; }
.hist-cal-weekdays {
  display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px;
  margin-bottom: 4px;
}
.hist-cal-weekdays div {
  text-align: center; font-size: .62rem; font-weight: 700;
  color: #bbb; text-transform: uppercase;
}
.hist-cal-grid { grid-template-columns: repeat(7, 1fr); margin-bottom: 14px; }
.hist-cell {
  aspect-ratio: 1; border-radius: 6px; border: none;
  font-size: .7rem; font-weight: 700; cursor: default;
  display: flex; align-items: center; justify-content: center;
  transition: all .15s;
}
.hist-cell.has-data {
  background: #fff0eb; color: #FC4C02;
  cursor: pointer; border: 1.5px solid #ffd6c8;
}
.hist-cell.has-data:hover { background: #FC4C02; color: white; border-color: #FC4C02; }
.hist-cell.active { background: #FC4C02 !important; color: white !important; border-color: #FC4C02 !important; }
.hist-cell.active:hover { background: #e04300 !important; border-color: #e04300 !important; }
.hist-cell.current { background: #f5f5f5; color: #bbb; cursor: pointer; }
.hist-cell.current:hover { background: #eaeaea; color: #aaa; }
.hist-cell.empty { color: #e0e0e0; }

/* SECTION TITLE */
.section-title {
  font-size: .75rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: .08em;
  color: #999; margin-bottom: 10px;
}

/* AWARDS */
.awards { display: grid; grid-template-columns: repeat(4,1fr); gap: 10px; margin-bottom: 24px; }
@media(max-width:800px){ .awards { grid-template-columns: repeat(2,1fr); } }
@media(max-width:500px){ .awards { grid-template-columns: 1fr; } }
.award-card {
  background: white; border-radius: 12px;
  padding: 14px 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,.07);
  display: flex; align-items: center; gap: 12px;
  transition: box-shadow .15s;
}
.award-card:hover { box-shadow: 0 3px 12px rgba(0,0,0,.1); }
.award-emoji { font-size: 1.6rem; flex-shrink: 0; }
.award-title { font-size: .72rem; color: #888; text-transform: uppercase; letter-spacing: .06em; }
.award-name { font-weight: 700; font-size: .95rem; margin: 1px 0; }
.award-val { font-size: .83rem; font-weight: 600; color: #FC4C02; }
.award-val.muted { color: #888; }

/* FUN STATS */
.fun-cards { display: grid; grid-template-columns: repeat(3,1fr); gap: 10px; margin-bottom: 24px; }
@media(max-width:700px){ .fun-cards { grid-template-columns: 1fr; } }
.fun-card {
  background: #fffbf0; border: 1.5px solid #ffe8b0;
  border-radius: 12px; padding: 13px 16px;
  display: flex; align-items: center; gap: 12px;
}
.fun-emoji { font-size: 1.4rem; flex-shrink: 0; }
.fun-title { font-size: .72rem; color: #b07800; text-transform: uppercase; letter-spacing: .06em; }
.fun-name { font-weight: 700; font-size: .95rem; margin: 1px 0; }
.fun-val { font-size: .83rem; color: #666; }
.fun-desc { font-size: .78rem; color: #a07020; font-style: italic; margin-top: 3px; }

/* TABLE */
.table-wrap {
  background: white; border-radius: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,.07);
  margin-bottom: 24px;
  overflow: hidden;
}
table { width: 100%; border-collapse: collapse; font-size: .87rem; }
thead th {
  background: #fafafa; color: #777;
  font-size: .72rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: .06em;
  padding: 11px 16px; text-align: right;
  border-bottom: 1px solid #f0f0f0;
  white-space: nowrap;
}
thead th:first-child { text-align: center; }
thead th:nth-child(2) { text-align: left; }
tbody tr:not(:last-child) { border-bottom: 1px solid #f7f7f7; }
tbody tr:hover { background: #fafafa; }
tbody td { padding: 12px 16px; text-align: right; color: #555; white-space: nowrap; }
tbody td:first-child { text-align: center; width: 40px; color: #999; }
thead th:nth-child(10), thead th:nth-child(11), thead th:nth-child(12) { text-align: center; }
tbody td:nth-child(10), tbody td:nth-child(11), tbody td:nth-child(12) { text-align: center; }
tbody td:nth-child(2) { text-align: left; font-weight: 700; color: #1c1c1e; }
tbody td:nth-child(3), tbody td:nth-child(4) { text-align: left; font-size: .8rem; color: #777; }
.km-cell { font-weight: 800; color: #FC4C02; }
.gap-cell { font-size: .78rem; color: #999; }
.gap-cell.leader { color: #FC4C02; font-weight: 700; font-size: .82rem; }
thead th.sortable { cursor: pointer; user-select: none; }
thead th.sortable:hover { background: #f0f0f0; color: #444; }
thead th.sortable::after { content: ' ↓'; opacity: 0; }
thead th.sortable:hover::after { opacity: 0.3; }
thead th.sort-asc::after  { content: ' ↑'; opacity: 1 !important; color: #FC4C02; }
thead th.sort-desc::after { content: ' ↓'; opacity: 1 !important; color: #FC4C02; }

/* Mobile table — scroll + sticky first two columns */
@media(max-width:700px) {
  .table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; overflow-y: visible; }
  table { width: max-content; min-width: 100%; }
  thead th:first-child {
    position: sticky; left: 0; z-index: 3; background: #fafafa;
  }
  thead th:nth-child(2) {
    position: sticky; left: 40px; z-index: 3; background: #fafafa;
    box-shadow: 3px 0 8px rgba(0,0,0,.07);
  }
  tbody td:first-child {
    position: sticky; left: 0; background: white; z-index: 1;
  }
  tbody td:nth-child(2) {
    position: sticky; left: 40px; background: white; z-index: 1;
    box-shadow: 3px 0 8px rgba(0,0,0,.07);
    min-width: 110px;
  }
  tbody tr:hover td:first-child,
  tbody tr:hover td:nth-child(2) { background: #fafafa; }
  thead th, tbody td { padding: 11px 12px; font-size: .82rem; }
}

/* HISTORY — backdrop */
.hist-backdrop {
  display: none; position: fixed; inset: 0;
  background: rgba(0,0,0,.35);
  backdrop-filter: blur(2px); -webkit-backdrop-filter: blur(2px);
  z-index: 199;
}
.hist-backdrop.open { display: block; }
@media (max-width: 640px) {
  .hist-grid { grid-template-columns: repeat(9, 1fr); gap: 5px; }
  .hist-cell { font-size: .68rem; }
}

/* DEVICES */
.dev-chip {
  background: white; border-radius: 8px; padding: 7px 14px;
  box-shadow: 0 1px 4px rgba(0,0,0,.07);
  font-size: .82rem; display: flex; align-items: center; gap: 6px;
}
@media (min-width: 701px) {
  .dev-chip.dev-hidden { display: flex !important; }
  .dev-more-btn { display: none !important; }
}
.dev-chip.dev-hidden { display: none; }
.dev-chip.dev-hidden.dev-visible { display: flex; }
.dev-more-btn {
  background: none; border: 1.5px solid #ccc;
  border-radius: 8px; padding: 6px 14px;
  font-size: .8rem; color: #555; cursor: pointer;
  white-space: nowrap;
}
.dev-more-btn:hover { border-color: #999; color: #333; }

/* COLUMN FILTER MENU */
.th-filterable { cursor: pointer; user-select: none; }
.th-filterable:hover { background: #f0f0f0 !important; color: #444 !important; }
.th-filterable.filter-active { color: #FC4C02 !important; }
.filter-menu {
  position: fixed; background: white; border-radius: 10px;
  box-shadow: 0 6px 24px rgba(0,0,0,.14); border: 1px solid #eee;
  z-index: 100; min-width: 150px; padding: 4px 0; font-size: .83rem;
  max-height: 280px; overflow-y: auto;
}
.filter-menu-item {
  padding: 8px 16px; cursor: pointer; color: #444; white-space: nowrap;
}
.filter-menu-item:hover { background: #f5f5f5; }
.filter-menu-item.active { color: #FC4C02; font-weight: 700; }

/* GROUP RANKINGS */
.group-rankings { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
@media(max-width:600px){ .group-rankings { grid-template-columns: 1fr; } }

/* FOOTER */
.footer { text-align: center; color: #aaa; font-size: .75rem; margin-top: 8px; }
.footer a { color: #FC4C02; }
.footer a:hover { text-decoration: underline; }

/* EMPTY STATE */
.empty-state {
  background: white; border-radius: 16px;
  padding: 64px 40px 56px;
  box-shadow: 0 1px 4px rgba(0,0,0,.07);
  margin-bottom: 24px;
  text-align: center;
}
.empty-state h2 {
  font-size: 1.5rem; font-weight: 800; color: #1c1c1e;
  display: inline-flex; align-items: center; gap: 11px;
  margin-bottom: 14px;
}
.empty-state h2 .es-emoji { font-size: 1.9rem; line-height: 1; }
.empty-state p {
  font-size: .92rem; color: #888;
  max-width: 420px; margin: 0 auto;
  line-height: 1.75;
}
.empty-state .es-divider {
  width: 36px; height: 2px; background: #efefef;
  margin: 26px auto; border-radius: 2px;
}
.empty-state .es-action { font-size: .84rem; color: #aaa; }
.empty-state .es-action a { color: #FC4C02; font-weight: 600; cursor: pointer; }
.empty-state .es-action a:hover { text-decoration: underline; }
.empty-state .es-hint { font-size: .82rem; color: #aaa; margin-top: 10px; }

/* FADE */
.fade { animation: fadeUp .35s ease; }
@keyframes fadeUp { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:none} }

@media(max-width:700px){
  .header-top { flex-direction: column; align-items: flex-start; gap: 6px; }
  .header h1 { font-size: 1.35rem; }
  .weather-widget { display: none; }
  .controls-row { flex-direction: column; align-items: flex-start; gap: 8px; }
  .nav-title { display: none; }
}

@media(max-width:600px){
  .totals { grid-template-columns: repeat(2,1fr); }
  .total-card { padding: 12px 8px; }
  .total-card .val { font-size: 1.25rem; }
}
</style>
</head>
<body>

<nav>
  <div class="nav-logo">
    <span class="nav-badge">__CLUB_SHORT__</span>
    <span class="nav-title">__CLUB_NAME__</span>
  </div>
  <a href="https://www.strava.com/clubs/__CLUB_ID__" target="_blank" class="nav-link">Strava Club</a>
</nav>

<div class="wrap">
  <div class="header">
    <div class="header-top">
      <div>
        <h1>🏃__CLUB_NAME__</h1>
        <div class="sub">
          <span class="dot"></span>
          <span id="period-label"></span>
        </div>
      </div>
      __WEATHER__
    </div>
  </div>

  <div class="group-tabs">
    <button class="group-tab active" onclick="setGroup('all', this)">All</button>
    <button class="group-tab" onclick="setGroup('nsf', this)">NSF (test)</button>
    <button class="group-tab" onclick="setGroup('nsmen', this)">NSMen (test)</button>
  </div>
  <div class="breadcrumb" id="breadcrumb"></div>

  <div class="controls-row">
    <div class="toggle">
      <button class="tab active" onclick="showLeaderboard()" id="btn-leaderboard">🏆 Leaderboard</button>
      <button class="tab" onclick="showPrevWeek()" id="btn-7days" style="display:none">Last Week</button>
      <div class="history-wrap" id="history-wrap" style="display:none">
        <button class="tab" onclick="toggleHistoryPicker(event)" id="btn-history">📅 History</button>
        <div class="history-picker" id="history-picker">
          <div class="history-picker-header">
            <div class="history-picker-title">Pick a date</div>
            <button class="history-picker-close" onclick="closeHistoryPicker()" title="Close">✕</button>
          </div>
          <div id="history-picker-list"></div>
        </div>
      </div>
    </div>
  </div>
  <div class="hist-backdrop" id="hist-backdrop" onclick="closeHistoryPicker()"></div>

  <div id="empty-state" class="empty-state" style="display:none"></div>

  <div id="totals-section">
    <div class="totals" id="totals"></div>
  </div>

  <div id="awards-section">
    <div class="section-title">Awards</div>
    <div class="awards" id="awards"></div>
  </div>

  <div id="fun-section" style="display:none">
    <div class="section-title">Fun Stats 😄</div>
    <div class="fun-cards" id="fun-stats"></div>
  </div>

  <div id="device-section" style="display:none;margin-bottom:24px">
    <div class="section-title">Devices in the Club</div>
    <div id="devices" style="display:flex;gap:8px;flex-wrap:wrap"></div>
  </div>

  <div id="group-rankings-section" class="group-rankings">
    <div>
      <div class="section-title">Unit Rankings</div>
      <div class="table-wrap" id="unit-rankings"></div>
    </div>
    <div>
      <div class="section-title">Company Rankings</div>
      <div class="table-wrap" id="company-rankings"></div>
    </div>
  </div>

  <div id="leaderboard-section">
    <div class="section-title">Runner Leaderboard <span id="leaderboard-count" style="text-transform:none;letter-spacing:normal;color:#bbb;font-weight:400"></span></div>
    <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Runner</th>
          <th class="th-filterable" id="th-unit"    onclick="toggleFilterMenu('unit', this)">Unit ▾</th>
          <th class="th-filterable" id="th-company" onclick="toggleFilterMenu('company', this)">Company ▾</th>
          <th class="sortable sort-desc" data-key="km"           onclick="sortBy('km')">km</th>
          <th>Gap</th>
          <th class="sortable" data-key="elev"          onclick="sortBy('elev')">Elevation</th>
          <th class="sortable" data-key="elev_per_km"   onclick="sortBy('elev_per_km')">m+/km</th>
          <th class="sortable" data-key="time_s"        onclick="sortBy('time_s')">Time</th>
          <th class="sortable" data-key="acts"          onclick="sortBy('acts')">Runs</th>
          <th class="sortable" data-key="avg_speed_ms"  onclick="sortBy('avg_speed_ms')">Avg Speed</th>
          <th class="sortable" data-key="longest"       onclick="sortBy('longest')">Longest</th>
        </tr>
      </thead>
      <tbody id="leaderboard"></tbody>
    </table>
  </div>
  </div>

  <div class="footer">
    Updated hourly &nbsp;·&nbsp; last update __UPDATED_HUMAN__ &nbsp;·&nbsp;
    <a href="https://www.strava.com/clubs/__CLUB_ID__" target="_blank">Strava Club</a>
    &nbsp;·&nbsp;
    <a href="https://github.com/DatabenderSK/strava-club-dashboard" target="_blank">Get your own dashboard</a>
  </div>
</div>

<script>
const DATA = __DATA__;
const DAILY   = __DAILY_DATA__;
const MEDALS = ['🥇','🥈','🥉'];
const AWARDS = [
  { key:'king_km',      emoji:'👑', title:'Distance King',   muted:false },
  { key:'king_elev',    emoji:'🏔️', title:'Climbing King',   muted:false },
  { key:'marathoner',   emoji:'⏱️', title:'Marathoner',       muted:false },
  { key:'fastest',      emoji:'⚡', title:'Fastest',          muted:false },
  { key:'longest',      emoji:'📏', title:'Longest Run',      muted:false },
  { key:'climber',      emoji:'🐐', title:'Mountain Goat',    muted:false },
  { key:'flatrunner',   emoji:'🛣️', title:'Flat Runner',      muted:false },
];
const FUN = [
  { key:'virtual',  emoji:'📶', title:'Virtual Cyclist',  desc:'Their bike has never seen rain or sun.' },
  { key:'ebike',    emoji:'🔌', title:'E-Biker',          desc:'Saving legs, spending battery.' },
  { key:'breaks',   emoji:'🛋️', title:'Break King',       desc:"Coffee breaks don't take themselves." },
];

const EMPTY_MSGS = [
  { emoji: '🛋️', title: 'Runners are in offline mode this week', body: 'No one has logged a run yet. Shoes are resting.' },
  { emoji: '🦗', title: 'Quiet as a Monday morning track', body: "Nobody's laced up this week yet. Roads are waiting patiently." },
  { emoji: '⏳', title: 'Week is just getting started', body: "Nothing to measure or count yet. Maybe tomorrow." },
  { emoji: '🌧️', title: 'Rain? Wind? Comfy couch?', body: 'Reason unknown, result clear — no activities this week yet.' },
  { emoji: '🧘', title: 'Recovery week', body: "At least that's what the support crew says. Either way — no runs yet." },
];

function esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

let currentSort        = { key: 'km', dir: -1 };
let currentDailyDate   = null;
let calendarMonth      = null; // 'YYYY-MM', set on first render
let filterUnit         = '';
let filterCompany      = '';
let currentGroup       = 'all';
let currentSub         = 'leaderboard';

const GROUP_LABELS = { all: 'All', nsf: 'NSF (test)', nsmen: 'NSMen (test)' };
const SUB_LABELS    = { leaderboard: 'Leaderboard', '7days': 'Last Week', history: 'History' };

function fmtTime(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return `${h}h ${m < 10 ? '0' : ''}${m}m`;
}

function currentBucket() {
  return currentDailyDate ? DAILY[currentDailyDate] : DATA['today'];
}

function d() {
  const bucket = currentBucket();
  return bucket[currentGroup] || bucket['all'];
}

function setGroup(g, el) {
  currentGroup = g;
  document.querySelectorAll('.group-tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  render();
  updateBreadcrumb(currentSub);
}

function updateBreadcrumb(sub) {
  currentSub = sub;
  const bucket = currentBucket();
  const available = !!bucket[currentGroup];
  const note = (currentGroup !== 'all' && !available) ? ' <span style="color:#bbb">(group breakdown unavailable for this date — showing All)</span>' : '';
  document.getElementById('breadcrumb').innerHTML =
    `<span class="crumb-group">${GROUP_LABELS[currentGroup]}</span> › <span class="crumb-sub">${SUB_LABELS[sub]}</span>${note}`;
}

function toggleHistoryPicker(e) {
  e.stopPropagation();
  const open = document.getElementById('history-picker').classList.toggle('open');
  document.getElementById('hist-backdrop').classList.toggle('open', open);
}

function closeHistoryPicker() {
  document.getElementById('history-picker').classList.remove('open');
  document.getElementById('hist-backdrop').classList.remove('open');
}

document.addEventListener('click', function(e) {
  if (!document.getElementById('history-wrap').contains(e.target)) closeHistoryPicker();
});

function sortBy(key) {
  if (currentSort.key === key) {
    currentSort.dir *= -1;
  } else {
    currentSort = { key, dir: -1 };
  }
  document.querySelectorAll('thead th.sortable').forEach(th => {
    th.classList.remove('sort-asc', 'sort-desc');
    if (th.dataset.key === key) {
      th.classList.add(currentSort.dir === -1 ? 'sort-desc' : 'sort-asc');
    }
  });
  renderLeaderboard(d());
}

function sortedLeaderboard(rows) {
  const { key, dir } = currentSort;
  return [...rows].sort((a, b) => {
    const va = a[key] ?? 0;
    const vb = b[key] ?? 0;
    return (va < vb ? -1 : va > vb ? 1 : 0) * dir;
  });
}

function changeCalendarMonth(delta, e) {
  e.stopPropagation();
  const [y, m] = calendarMonth.split('-').map(Number);
  const nd = new Date(y, m - 1 + delta, 1);
  calendarMonth = `${nd.getFullYear()}-${String(nd.getMonth() + 1).padStart(2, '0')}`;
  render();
}

function renderDayCalendar() {
  const [year, month] = calendarMonth.split('-').map(Number);
  const monthLabel = new Date(year, month - 1, 1).toLocaleDateString('en', { month: 'long', year: 'numeric' });
  const firstWeekday = new Date(year, month - 1, 1).getDay();
  const daysInMonth = new Date(year, month, 0).getDate();
  const dailyKeys = Object.keys(DAILY);
  const minMonth = dailyKeys.length ? dailyKeys.sort()[0].slice(0, 7) : calendarMonth;
  const maxMonth = dailyKeys.length ? dailyKeys.sort().at(-1).slice(0, 7) : calendarMonth;

  let html = `<div class="hist-cal-header">
      <button class="hist-cal-nav" onclick="changeCalendarMonth(-1, event)" ${calendarMonth <= minMonth ? 'disabled' : ''}>‹</button>
      <div class="hist-cal-month">${monthLabel}</div>
      <button class="hist-cal-nav" onclick="changeCalendarMonth(1, event)" ${calendarMonth >= maxMonth ? 'disabled' : ''}>›</button>
    </div>
    <div class="hist-cal-weekdays">${['S','M','T','W','T','F','S'].map(d => `<div>${d}</div>`).join('')}</div>
    <div class="hist-grid hist-cal-grid">`;

  for (let i = 0; i < firstWeekday; i++) html += `<div class="hist-cell"></div>`;
  for (let day = 1; day <= daysInMonth; day++) {
    const date = `${calendarMonth}-${String(day).padStart(2, '0')}`;
    const hasData = !!DAILY[date];
    const isActive = date === currentDailyDate;
    let cls = 'hist-cell';
    if (isActive) cls += ' active';
    else if (hasData) cls += ' has-data';
    else cls += ' empty';
    const tip = hasData ? `title="${DAILY[date].label}"` : '';
    const click = hasData ? `onclick="showDailySnapshot('${date}')"` : '';
    html += `<div class="${cls}" ${tip} ${click}>${day}</div>`;
  }
  html += '</div>';
  return html;
}

function render() {
  const data = d();
  if (currentDailyDate) {
    document.getElementById('period-label').textContent = DAILY[currentDailyDate].label;
  } else {
    document.getElementById('period-label').textContent = `Cumulative · as of ${data.label}`;
  }

  document.getElementById('totals').innerHTML = [
    { v: Math.round(data.total_km).toLocaleString('en'), l: 'total km' },
    { v: Math.round(data.total_elev).toLocaleString('en'), l: 'elevation (m)' },
    { v: data.run_count, l: 'activities' },
    { v: (data.leaderboard || []).filter(r => r.acts > 0).length, l: 'active runners' },
    { v: data.athlete_count, l: 'runners' },
  ].map(t => `<div class="total-card fade">
    <div class="val">${t.v}</div><div class="lbl">${t.l}</div>
  </div>`).join('');

  document.getElementById('awards').innerHTML = AWARDS.map(def => {
    const a = data[def.key]; if (!a) return '';
    return `<div class="award-card fade">
      <div class="award-emoji">${def.emoji}</div>
      <div>
        <div class="award-title">${def.title}</div>
        <div class="award-name">${esc(a.name)}</div>
        <div class="award-val ${def.muted?'muted':''}">${esc(a.value)}</div>
      </div>
    </div>`;
  }).join('');

  const fun = data.fun_stats || {};
  const funHtml = FUN.map(def => {
    const a = fun[def.key]; if (!a || !a.name) return '';
    return `<div class="fun-card fade">
      <div class="fun-emoji">${def.emoji}</div>
      <div>
        <div class="fun-title">${def.title}</div>
        <div class="fun-name">${esc(a.name)}</div>
        <div class="fun-val">${esc(a.value)}</div>
        ${def.desc ? `<div class="fun-desc">${def.desc}</div>` : ''}
      </div>
    </div>`;
  }).join('');
  document.getElementById('fun-stats').innerHTML = funHtml;
  document.getElementById('fun-section').style.display = funHtml.trim() ? '' : 'none';

  const devs = data.device_stats || [];
  const DEVS_SHOW = 3;
  function devChip(d, i, hidden) {
    const icon = MEDALS[i] || `<span style="color:#ccc;font-size:.75rem;min-width:18px;text-align:center">${i+1}</span>`;
    return `<div class="dev-chip${hidden?' dev-hidden':''}">${icon} <strong>${esc(d.device)}</strong><span style="color:#FC4C02;font-weight:700;margin-left:4px">${d.count}×</span></div>`;
  }
  const extraDevs = devs.slice(DEVS_SHOW);
  const moreHtml = extraDevs.length
    ? extraDevs.map((d,i) => devChip(d, DEVS_SHOW+i, true)).join('') +
      `<button class="dev-more-btn" onclick="var o=this.dataset.open==='1';document.querySelectorAll('#devices .dev-hidden').forEach(function(e){e.classList.toggle('dev-visible')});this.dataset.open=o?'':'1';this.textContent=o?'+ ${extraDevs.length} more':'↑ Show less'">+ ${extraDevs.length} more</button>`
    : '';
  document.getElementById('devices').innerHTML = devs.slice(0, DEVS_SHOW).map((d,i) => devChip(d,i,false)).join('') + moreHtml;
  document.getElementById('device-section').style.display = devs.length ? '' : 'none';

  // Empty state
  const isEmpty = !data.run_count;
  const esEl = document.getElementById('empty-state');
  if (isEmpty) {
    const daySeed = new Date().getDate();
    let msg, bottomHtml;
    const hasPrev = Object.keys(DAILY).length > 0;
    const archiveHtml = hasPrev
      ? `Check out <a onclick="showPrevWeek()">last week's results</a> or <a onclick="toggleHistoryPicker(event)">older archives</a>.`
      : '';
    msg = EMPTY_MSGS[daySeed % EMPTY_MSGS.length];
    bottomHtml = `<div class="es-divider"></div>${archiveHtml ? `<div class="es-action">${archiveHtml}</div>` : ''}<div class="es-hint">This page updates every hour.</div>`;
    esEl.innerHTML = `<h2><span class="es-emoji">${msg.emoji}</span>${msg.title}</h2><p>${msg.body}</p>${bottomHtml}`;
  }
  esEl.style.display = isEmpty ? '' : 'none';
  document.getElementById('totals-section').style.display         = isEmpty ? 'none' : '';
  document.getElementById('awards-section').style.display         = isEmpty ? 'none' : '';
  document.getElementById('leaderboard-section').style.display    = isEmpty ? 'none' : '';
  document.getElementById('group-rankings-section').style.display = isEmpty ? 'none' : '';
  if (isEmpty) {
    document.getElementById('fun-section').style.display    = 'none';
    document.getElementById('device-section').style.display = 'none';
  }
  // History picker — populate day calendar
  const dailyKeys = Object.keys(DAILY);
  document.getElementById('history-wrap').style.display = dailyKeys.length ? '' : 'none';
  if (dailyKeys.length) {
    document.getElementById('btn-7days').style.display = '';
  }
  if (!calendarMonth) {
    calendarMonth = (dailyKeys.length ? dailyKeys.sort().at(-1) : new Date().toISOString()).slice(0, 7);
  }
  document.getElementById('history-picker-list').innerHTML = renderDayCalendar();

  renderLeaderboard(data);
  renderGroupRankings(data);
}

let _openFilterKey = null;

function toggleFilterMenu(key, th) {
  const wasOpen = _openFilterKey === key;
  closeFilterMenu();
  if (wasOpen) return;
  _openFilterKey = key;
  const all = d().leaderboard || [];
  const values = [...new Set(all.map(r => r[key]).filter(Boolean))].sort();
  const current = key === 'unit' ? filterUnit : filterCompany;
  const menu = document.createElement('div');
  menu.className = 'filter-menu';
  menu.id = 'active-filter-menu';
  const allItem = document.createElement('div');
  allItem.className = 'filter-menu-item' + (current === '' ? ' active' : '');
  allItem.textContent = 'All ' + (key === 'unit' ? 'Units' : 'Companies');
  allItem.onclick = e => { e.stopPropagation(); setFilter(key, ''); };
  menu.appendChild(allItem);
  values.forEach(v => {
    const item = document.createElement('div');
    item.className = 'filter-menu-item' + (v === current ? ' active' : '');
    item.textContent = v;
    item.onclick = e => { e.stopPropagation(); setFilter(key, v); };
    menu.appendChild(item);
  });
  document.body.appendChild(menu);
  const rect = th.getBoundingClientRect();
  const mw   = menu.offsetWidth;
  const left  = Math.min(rect.left, window.innerWidth - mw - 8);
  menu.style.top  = (rect.bottom + 4) + 'px';
  menu.style.left = Math.max(8, left) + 'px';
}

function setFilter(key, value) {
  if (key === 'unit') filterUnit = value;
  else filterCompany = value;
  closeFilterMenu();
  renderLeaderboard(d());
}

function closeFilterMenu() {
  const m = document.getElementById('active-filter-menu');
  if (m) m.remove();
  _openFilterKey = null;
  ['unit', 'company'].forEach(k => {
    const th = document.getElementById('th-' + k);
    if (th) th.classList.toggle('filter-active', k === 'unit' ? !!filterUnit : !!filterCompany);
  });
}

document.addEventListener('click', e => {
  if (_openFilterKey &&
      !e.target.closest('#active-filter-menu') &&
      !e.target.closest('#th-unit') &&
      !e.target.closest('#th-company')) {
    closeFilterMenu();
  }
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeFilterMenu(); });

function renderLeaderboard(data) {
  const all = data.leaderboard || [];
  const activeCount = all.filter(r => r.acts > 0).length;
  document.getElementById('leaderboard-count').textContent = `(${activeCount} active / ${data.athlete_count} total)`;
  // self-heal: reset filter if its value no longer exists in current dataset
  const units     = new Set(all.map(r => r.unit).filter(Boolean));
  const companies = new Set(all.map(r => r.company).filter(Boolean));
  if (filterUnit    && !units.has(filterUnit))        filterUnit    = '';
  if (filterCompany && !companies.has(filterCompany)) filterCompany = '';
  // sync header active state
  ['unit', 'company'].forEach(k => {
    const th = document.getElementById('th-' + k);
    if (th) th.classList.toggle('filter-active', k === 'unit' ? !!filterUnit : !!filterCompany);
  });
  // apply filters then sort
  let rows = all;
  if (filterUnit)    rows = rows.filter(r => r.unit    === filterUnit);
  if (filterCompany) rows = rows.filter(r => r.company === filterCompany);
  rows = sortedLeaderboard(rows);
  const isByKm = currentSort.key === 'km';
  document.getElementById('leaderboard').innerHTML = rows.map((r, i) => `
    <tr>
      <td>${isByKm && MEDALS[i] ? MEDALS[i] : '<span style="color:#ccc;font-size:.75rem">'+(i+1)+'</span>'}</td>
      <td>${esc(r.name)}${r.ebike ? ' <span title="Mostly e-bike" style="font-size:.8rem;opacity:.6">⚡</span>' : ''}</td>
      <td>${esc(r.unit||'')}</td>
      <td>${esc(r.company||'')}</td>
      <td class="km-cell">${r.km}</td>
      <td class="gap-cell ${r.gap==='leader'?'leader':''}">${r.gap}</td>
      <td>${r.elev} m</td>
      <td>${r.elev_per_km != null ? r.elev_per_km+' m+/km' : '–'}</td>
      <td>${r.time}</td>
      <td>${r.acts}</td>
      <td>${r.avg_speed}</td>
      <td>${r.longest != null ? r.longest + ' km' : '–'}</td>
    </tr>`).join('') || '<tr><td colspan="12" style="text-align:center;color:#ccc;padding:20px">No activities</td></tr>';
}

function renderGroupRankings(data) {
  function groupBy(key) {
    const map = {};
    for (const r of (data.leaderboard || [])) {
      const k = r[key]; if (!k) continue;
      if (!map[k]) map[k] = { name: k, km: 0, active: 0, total: 0 };
      map[k].km += r.km;
      map[k].total++;
      if (r.acts > 0) map[k].active++;
    }
    return Object.values(map).sort((a, b) => b.km - a.km);
  }
  function tableHtml(groups, label) {
    if (!groups.length) return `<p style="color:#ccc;padding:16px;text-align:center;font-size:.82rem">No ${label} data</p>`;
    return `<table><thead><tr><th>#</th><th style="text-align:left">${label}</th><th>km</th><th>Runners</th></tr></thead><tbody>` +
      groups.map((g, i) => `<tr>
        <td>${MEDALS[i]||'<span style="color:#ccc;font-size:.75rem">'+(i+1)+'</span>'}</td>
        <td style="text-align:left;font-weight:700">${esc(g.name)}</td>
        <td class="km-cell">${Math.round(g.km * 10) / 10}</td>
        <td style="text-align:center">${g.active}/${g.total}</td>
      </tr>`).join('') + '</tbody></table>';
  }
  document.getElementById('unit-rankings').innerHTML    = tableHtml(groupBy('unit'),    'Unit');
  document.getElementById('company-rankings').innerHTML = tableHtml(groupBy('company'), 'Company');
}

function showPrevWeek() {
  // Latest Saturday on/before today (Saturday itself if today is one).
  const now = new Date();
  const daysSinceSat = (now.getDay() + 1) % 7;
  const sat = new Date(now.getFullYear(), now.getMonth(), now.getDate() - daysSinceSat);
  const satStr = `${sat.getFullYear()}-${String(sat.getMonth() + 1).padStart(2, '0')}-${String(sat.getDate()).padStart(2, '0')}`;
  const key = Object.keys(DAILY).sort().filter(k => k <= satStr).at(-1);
  if (!key) return;
  showDailySnapshot(key);
  document.getElementById('btn-7days').classList.add('active');
  updateBreadcrumb('7days');
}

function showLeaderboard() {
  currentDailyDate = null;
  document.getElementById('btn-7days').classList.remove('active');
  document.getElementById('btn-history').classList.remove('active');
  document.getElementById('btn-leaderboard').classList.add('active');
  render();
  updateBreadcrumb('leaderboard');
}

function showDailySnapshot(date) {
  currentDailyDate = date;
  closeHistoryPicker();
  document.getElementById('btn-7days').classList.remove('active');
  document.getElementById('btn-history').classList.remove('active');
  document.getElementById('btn-leaderboard').classList.remove('active');
  render();
  updateBreadcrumb('history');
}


showLeaderboard();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def build_daily_history(clean_ledger: list, members: list, name_map: dict = None, uc_map: dict = None) -> dict:
    """Derive {date: {date, label, all, nsf, nsmen}} for every date that ever
    saw a new ledger entry, by re-running build_grouped_data() against the
    ledger cumulative up to and including that date.

    clean_ledger has no per-activity date (Strava's club feed doesn't expose
    one) — ingested_at (scrape time) is the only timeline signal, and is
    exactly what "today" is already computed from, so this reproduces every
    historical date's stats with full fidelity, not just an approximation.
    """
    dates = sorted({a["ingested_at"][:10] for a in clean_ledger if a.get("ingested_at")})
    result = {}
    for date_str in dates:
        subset = [a for a in clean_ledger if a.get("ingested_at", "")[:10] <= date_str]
        y, m, d = (int(p) for p in date_str.split("-"))
        label = f"{d}.{m}.{y}"
        result[date_str] = {"date": date_str, "label": label,
                             **build_grouped_data(subset, members, label, name_map, uc_map)}
    return result


def make_json_safe(stats: dict) -> dict:
    """Convert stats dict to JSON-serializable object (handle NaN/Inf)."""
    def fix(obj):
        if isinstance(obj, dict):
            return {k: fix(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [fix(i) for i in obj]
        if isinstance(obj, float):
            return 0.0 if math.isnan(obj) or math.isinf(obj) else obj
        return obj
    return fix(stats)


LEDGER_PATH = Path(__file__).parent / "ledger.json"

# ponytail: no activity id/timestamp in Strava's club feed, so new entries are
# found by anchoring on the ledger's 3 most-recent entries inside the fresh
# fetch. Anchor missing (>197 new activities in an hour, or an anchored
# activity edited/deleted) -> append everything, accept occasional double-count.

def _activity_key(act: dict) -> tuple:
    athlete = act.get("athlete") or {}
    name = (athlete.get("firstname", ""), athlete.get("lastname", ""))
    return (
        name,
        act.get("name"),
        act.get("distance"),
        act.get("moving_time"),
        act.get("elapsed_time"),
        act.get("total_elevation_gain"),
        act.get("device_name"),
    )


def merge_ledger(ledger: list, fresh: list, now_iso: str) -> tuple:
    """Merge freshly fetched activities (newest-first) into the ledger
    (newest-first). Returns (merged_ledger, anchor_missed).

    The anchor match is only a fast path for finding new activities — Strava's
    club feed has no activity id/timestamp, so the anchor can legitimately miss
    (>197 new activities in an hour, or an anchored activity edited/deleted).
    Content-key dedup below is the actual correctness guarantee: it runs
    unconditionally, so a missed or stale anchor can degrade to "append
    everything" but can never reintroduce an activity already in the ledger.
    """
    if not ledger:
        new_entries, anchor_missed = fresh, False
        print("  Ledger empty — no anchor to match, treating full fetch as new.")
    else:
        anchor = [_activity_key(a) for a in ledger[:3]]
        n = len(anchor)
        match_at = next(
            (i for i in range(len(fresh) - n + 1)
             if [_activity_key(a) for a in fresh[i:i + n]] == anchor),
            None,
        )
        new_entries = fresh if match_at is None else fresh[:match_at]
        anchor_missed = match_at is None
        if anchor_missed:
            print(f"  Anchor NOT found: {anchor}")
        else:
            print(f"  Anchor found at fresh[{match_at}:{match_at + n}]: {anchor}")

    existing_keys = {_activity_key(a) for a in ledger}
    new_entries = [a for a in new_entries if _activity_key(a) not in existing_keys]

    stamped = [{**a, "ingested_at": now_iso} for a in new_entries]
    return stamped + ledger, anchor_missed


CLEAN_LEDGER_PATH = Path(__file__).parent / "ledger-clean.json"


def _same_upload_batch(a: dict, b: dict) -> bool:
    aa, bb = a.get("athlete") or {}, b.get("athlete") or {}
    return (a.get("ingested_at") == b.get("ingested_at")
            and aa.get("firstname") == bb.get("firstname")
            and aa.get("lastname") == bb.get("lastname"))


def dedup_consecutive(entries: list) -> list:
    """Collapse runs of *consecutive* same-athlete activities ingested in the
    same batch (e.g. multiple runs uploaded together) into the single
    longest-distance entry, preserving order."""
    result, group = [], []
    for act in entries:
        if group and not _same_upload_batch(group[-1], act):
            result.append(max(group, key=lambda a: a.get("distance") or 0))
            group = []
        group.append(act)
    if group:
        result.append(max(group, key=lambda a: a.get("distance") or 0))
    return result


def load_ledger(path: Path) -> list:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_ledger(path: Path, ledger: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")


def generate():
    print("Fetching data from Strava...")

    token   = strava_client.get_access_token()
    members = strava_client.fetch_club_members(token)

    print("  Fetching latest club activities...")
    fresh = strava_client.fetch_club_activities(token)
    now_dt = _now_tz()
    now_iso = now_dt.strftime("%Y-%m-%dT%H:%M")

    stored_ledger = load_ledger(LEDGER_PATH)
    full_ledger, anchor_missed = merge_ledger(stored_ledger, fresh, now_iso)
    if anchor_missed and stored_ledger:
        print("  WARNING: ledger anchor not found in fresh activities — "
              "appended full fetch, some activities may be double-counted.")
    new_count = len(full_ledger) - len(stored_ledger)
    print(f"  {new_count} new activities appended to ledger.")
    save_ledger(LEDGER_PATH, full_ledger)

    if CLEAN_LEDGER_PATH.exists():
        clean_ledger = dedup_consecutive(full_ledger[:new_count]) + load_ledger(CLEAN_LEDGER_PATH)
    else:
        # bootstrap: no prior clean ledger, dedup the whole history at once
        clean_ledger = dedup_consecutive(full_ledger)
    save_ledger(CLEAN_LEDGER_PATH, clean_ledger)

    name_map, uc_map = load_nominal_roll()

    date_label = f"{now_dt.day}.{now_dt.month}.{now_dt.year}"
    # clean_ledger entries are all ingested_at <= now, so this *is* the
    # cumulative-to-date total — no per-week/per-day filtering needed.
    today_data = build_grouped_data(clean_ledger, members, date_label, name_map, uc_map)
    daily_snapshots = build_daily_history(clean_ledger, members, name_map, uc_map)

    data = {"today": today_data}

    _, human_label = now_label()

    weather = fetch_weather()
    if weather["ok"]:
        weather_html = (
            f'<span class="weather-widget">'
            f'{weather["icon"]} <strong>{weather["temp"]}°C</strong>'
            f' · {weather["desc"]}'
            f' · 💨 {weather["wind"]} km/h'
            f'</span>'
        )
    else:
        weather_html = ""

    # Club short name — first letters or first word
    club_name = config.CLUB_NAME
    words = club_name.split()
    club_short = "".join(w[0] for w in words).upper() if len(words) > 1 else club_name[:4].upper()

    html = TEMPLATE
    html = html.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    html = html.replace("__DAILY_DATA__", json.dumps(daily_snapshots, ensure_ascii=False))
    html = html.replace("__UPDATED_HUMAN__", human_label)
    html = html.replace("__WEATHER__", weather_html)
    html = html.replace("__CLUB_NAME__", club_name)
    html = html.replace("__CLUB_SHORT__", club_short)
    html = html.replace("__CLUB_ID__", config.STRAVA_CLUB_ID)

    out_path = Path(__file__).parent.parent / "index.html"
    out_path.write_text(html, encoding="utf-8")

    w = data["today"]["all"]
    print(f"Generated: {out_path}")
    print(f"  Cumulative: {w.get('count', 0)} activities, {w.get('athlete_count', 0)} runners")


if __name__ == "__main__":
    generate()
