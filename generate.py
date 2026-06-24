"""
Generate a static dashboard/index.html from current Strava club data.
Run locally or via GitHub Actions (hourly cron).

Usage:
  python3 generate.py
"""
import os, json, math
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

import config
import strava_client, report_generator

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

def now_label() -> tuple:
    """Return (iso_str, human_label) in configured timezone."""
    try:
        import pytz
        tz = pytz.timezone(config.TIMEZONE)
        now = datetime.now(tz)
    except Exception:
        from datetime import timezone
        now = datetime.now(timezone.utc)
    iso = now.strftime("%Y-%m-%dT%H:%M")
    human = f"{now.day}.{now.month}.{now.year} {now.hour:02}:{now.minute:02}"
    return iso, human


# ---------------------------------------------------------------------------
# Week helpers
# ---------------------------------------------------------------------------

_TZ8 = timezone(timedelta(hours=8))



def week_label_for_id(week_id: str) -> str:
    year, wnum = int(week_id[:4]), int(week_id[6:])
    jan4 = datetime(year, 1, 4, tzinfo=_TZ8)
    monday = jan4 - timedelta(days=jan4.weekday()) + timedelta(weeks=wnum - 1)
    sunday = monday - timedelta(days=1)  # week starts on Sunday
    if week_id == get_week_id():
        now = datetime.now(_TZ8)
        return f"{sunday.day}.{sunday.month} – {now.day}.{now.month}.{now.year}"
    return f"Week of {sunday.day}.{sunday.month}.{sunday.year}"


def build_week_data(acts: list, members: list, label: str) -> dict:
    def build(a):
        s = report_generator.compute_stats(a, members=members)
        s["label"] = label
        s["count"] = len(a)
        return make_json_safe(s)
    return {"all": build(acts)}


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__CLUB_NAME__ – Strava Dashboard</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🚴</text></svg>">

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
thead th:nth-child(8), thead th:nth-child(9), thead th:nth-child(10) { text-align: center; }
tbody td:nth-child(8), tbody td:nth-child(9), tbody td:nth-child(10) { text-align: center; }
tbody td:nth-child(2) { text-align: left; font-weight: 700; color: #1c1c1e; }
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
        <h1>🚴 Weekly Report – __CLUB_NAME__</h1>
        <div class="sub">
          <span class="dot"></span>
          <span id="period-label"></span>
        </div>
      </div>
      __WEATHER__
    </div>
  </div>

  <div class="controls-row">
    <div class="toggle">
      <button class="tab active" onclick="showMode('week')" id="btn-week">This Week</button>
      <button class="tab" onclick="showPrevWeek()" id="btn-7days" style="display:none">Last Week</button>
      <button class="tab" onclick="showLeaderboard()" id="btn-leaderboard">🏆 Leaderboard</button>
      <div id="daily-tabs" style="display:inline-flex;gap:4px"></div>
      <div class="history-wrap" id="history-wrap" style="display:none">
        <button class="tab" onclick="toggleHistoryPicker(event)" id="btn-history">📅 History</button>
        <div class="history-picker" id="history-picker">
          <div class="history-picker-header">
            <div class="history-picker-title">Pick a week</div>
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

  <div id="leaderboard-section">
    <div class="section-title">Runner Leaderboard</div>
    <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Runner</th>
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
const HISTORY = __HISTORY_DATA__;
const DAILY   = __DAILY_DATA__;
const PREV_WEEK_ID = '__PREV_WEEK_ID__';
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
let currentHistoryWeek = null;
let cumulativeMode     = false;
let currentDailyDate   = null;

function fmtTime(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return `${h}h ${m < 10 ? '0' : ''}${m}m`;
}

function sundayOfWeek(weekId) {
  const [yr, w] = weekId.split('-W').map(Number);
  const jan4 = new Date(yr, 0, 4);
  const dow = jan4.getDay() || 7;
  const mon1 = new Date(jan4); mon1.setDate(jan4.getDate() - dow + 1);
  const sun = new Date(mon1); sun.setDate(mon1.getDate() + (w - 1) * 7 + 6);
  return sun.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function buildCumulative() {
  const weeks = [DATA['week'], ...Object.values(HISTORY)];
  const byName = {};
  for (const wk of weeks) {
    const wd = wk['all'];
    for (const r of (wd.leaderboard || [])) {
      if (!byName[r.name]) byName[r.name] = { name: r.name, km: 0, elev: 0, acts: 0, time_s: 0, ebike: false };
      byName[r.name].km    += r.km;
      byName[r.name].elev  += r.elev;
      byName[r.name].acts  += r.acts;
      byName[r.name].time_s += r.time_s;
      if (r.ebike) byName[r.name].ebike = true;
    }
  }
  const rows = Object.values(byName).sort((a, b) => b.km - a.km);
  rows.forEach((r, i) => {
    r.km          = Math.round(r.km * 10) / 10;
    r.elev        = Math.round(r.elev);
    r.gap         = i === 0 ? 'leader' : `–${(rows[0].km - r.km).toFixed(1)}`;
    r.time        = fmtTime(r.time_s);
    r.elev_per_km = r.km > 0 ? Math.round(r.elev / r.km * 10) / 10 : 0;
    r.avg_speed_ms = r.time_s > 0 ? r.km / (r.time_s / 3600) / 3.6 : 0;
    r.avg_speed   = r.time_s > 0 ? (r.km / (r.time_s / 3600)).toFixed(1) + ' km/h' : '–';
    r.longest     = null; // ponytail: doesn't aggregate meaningfully
  });
  return {
    leaderboard:   rows,
    total_km:      rows.reduce((s, r) => s + r.km, 0),
    total_elev:    rows.reduce((s, r) => s + r.elev, 0),
    run_count:     rows.reduce((s, r) => s + r.acts, 0),
    athlete_count: rows.length,
    label:         '',
  };
}

function d() {
  if (currentDailyDate)  return DAILY[currentDailyDate]['all'];
  if (cumulativeMode)    return buildCumulative();
  if (currentHistoryWeek) return HISTORY[currentHistoryWeek]['all'];
  return DATA['week']['all'];
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

function render() {
  const data = d();
  if (currentDailyDate) {
    document.getElementById('period-label').textContent = DAILY[currentDailyDate].label;
  } else if (cumulativeMode) {
    document.getElementById('period-label').textContent = `Cumulative · Week of ${sundayOfWeek('__CURRENT_WEEK_ID__')}`;
  } else if (currentHistoryWeek) {
    document.getElementById('period-label').textContent = data.label;
  } else {
    const _wNum = parseInt('__CURRENT_WEEK_ID__'.split('-W')[1] || '0');
    document.getElementById('period-label').textContent = `Week ${_wNum}  ·  ${data.label}`;
  }

  document.getElementById('totals').innerHTML = [
    { v: Math.round(data.total_km).toLocaleString('en'), l: 'total km' },
    { v: Math.round(data.total_elev).toLocaleString('en'), l: 'elevation (m)' },
    { v: data.run_count, l: 'activities' },
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
  const devMedals = ['🥇','🥈','🥉'];
  const DEVS_SHOW = 3;
  function devChip(d, i, hidden) {
    const icon = devMedals[i] || `<span style="color:#ccc;font-size:.75rem;min-width:18px;text-align:center">${i+1}</span>`;
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
    const wNum = parseInt('__CURRENT_WEEK_ID__'.split('-W')[1] || '1');
    let msg, bottomHtml;
    const hasPrev = PREV_WEEK_ID && HISTORY[PREV_WEEK_ID];
    const hasHistory = Object.keys(HISTORY).length > 0;
    const archiveHtml = hasPrev
      ? `Check out <a onclick="showPrevWeek()">last week's results</a>${hasHistory ? ` or <a onclick="toggleHistoryPicker(event)">older archives</a>` : ''}.`
      : (hasHistory ? `Browse <a onclick="toggleHistoryPicker(event)">older results</a> in the archive.` : '');
    msg = EMPTY_MSGS[wNum % EMPTY_MSGS.length];
    bottomHtml = `<div class="es-divider"></div>${archiveHtml ? `<div class="es-action">${archiveHtml}</div>` : ''}<div class="es-hint">This page updates every hour.</div>`;
    esEl.innerHTML = `<h2><span class="es-emoji">${msg.emoji}</span>${msg.title}</h2><p>${msg.body}</p>${bottomHtml}`;
  }
  esEl.style.display = isEmpty ? '' : 'none';
  document.getElementById('totals-section').style.display    = isEmpty ? 'none' : '';
  document.getElementById('awards-section').style.display    = isEmpty ? 'none' : '';
  document.getElementById('leaderboard-section').style.display = isEmpty ? 'none' : '';
  if (isEmpty) {
    document.getElementById('fun-section').style.display    = 'none';
    document.getElementById('device-section').style.display = 'none';
  }
  if (cumulativeMode) {
    document.getElementById('awards-section').style.display  = 'none';
    document.getElementById('fun-section').style.display     = 'none';
    document.getElementById('device-section').style.display  = 'none';
  }

  // History picker — populate week grid
  const histKeys = new Set(Object.keys(HISTORY));
  const currentWid = '__CURRENT_WEEK_ID__';
  document.getElementById('history-wrap').style.display = histKeys.size ? '' : 'none';
  if (PREV_WEEK_ID && HISTORY[PREV_WEEK_ID]) {
    document.getElementById('btn-7days').style.display = '';
  }
  const years = new Set([parseInt(currentWid.split('-W')[0])]);
  histKeys.forEach(k => years.add(parseInt(k.split('-W')[0])));
  let pickerHtml = '';
  [...years].sort().forEach(year => {
    pickerHtml += `<div class="hist-year-label">${year}</div><div class="hist-grid">`;
    for (let w = 1; w <= 52; w++) {
      const wid = `${year}-W${String(w).padStart(2,'0')}`;
      const hasData = histKeys.has(wid);
      const isCurrent = wid === currentWid;
      const isActive = wid === currentHistoryWeek;
      let cls = 'hist-cell';
      if (isActive) cls += ' active';
      else if (hasData) cls += ' has-data';
      else if (isCurrent) cls += ' current';
      else cls += ' empty';
      const tip = hasData ? `title="${HISTORY[wid].label}"` : (isCurrent ? 'title="Current week"' : '');
      const click = hasData ? `onclick="showHistoryWeek('${wid}')"` : (isCurrent ? `onclick="showMode('week');closeHistoryPicker()"` : '');
      pickerHtml += `<div class="${cls}" ${tip} ${click}>${w}</div>`;
    }
    pickerHtml += '</div>';
  });
  document.getElementById('history-picker-list').innerHTML = pickerHtml;

  // Daily snapshot tabs (descending order, right of Leaderboard button)
  const dailyKeys = Object.keys(DAILY).sort().reverse();
  document.getElementById('daily-tabs').innerHTML = dailyKeys.map(date => {
    const isActive = date === currentDailyDate;
    return `<button class="tab${isActive ? ' active' : ''}" onclick="showDailySnapshot('${date}')">${DAILY[date].label}</button>`;
  }).join('');

  renderLeaderboard(data);
}

function renderLeaderboard(data) {
  const rows = sortedLeaderboard(data.leaderboard || []);
  const isByKm = currentSort.key === 'km';
  document.getElementById('leaderboard').innerHTML = rows.map((r, i) => `
    <tr>
      <td>${isByKm && MEDALS[i] ? MEDALS[i] : '<span style="color:#ccc;font-size:.75rem">'+(i+1)+'</span>'}</td>
      <td>${esc(r.name)}${r.ebike ? ' <span title="Mostly e-bike" style="font-size:.8rem;opacity:.6">⚡</span>' : ''}</td>
      <td class="km-cell">${r.km}</td>
      <td class="gap-cell ${r.gap==='leader'?'leader':''}">${r.gap}</td>
      <td>${r.elev} m</td>
      <td>${r.elev_per_km != null ? r.elev_per_km+' m+/km' : '–'}</td>
      <td>${r.time}</td>
      <td>${r.acts}</td>
      <td>${r.avg_speed}</td>
      <td>${r.longest != null ? r.longest + ' km' : '–'}</td>
    </tr>`).join('') || '<tr><td colspan="10" style="text-align:center;color:#ccc;padding:20px">No activities</td></tr>';
}

function showMode(mode) {
  cumulativeMode = false;
  currentHistoryWeek = null;
  document.getElementById('btn-week').classList.toggle('active', mode==='week');
  document.getElementById('btn-7days').classList.remove('active');
  document.getElementById('btn-history').classList.remove('active');
  document.getElementById('btn-leaderboard').classList.remove('active');
  render();
}

function showPrevWeek() {
  if (!PREV_WEEK_ID) return;
  cumulativeMode = false;
  currentHistoryWeek = PREV_WEEK_ID;
  document.getElementById('btn-week').classList.remove('active');
  document.getElementById('btn-7days').classList.add('active');
  document.getElementById('btn-history').classList.remove('active');
  document.getElementById('btn-leaderboard').classList.remove('active');
  render();
}

function showHistoryWeek(weekId) {
  cumulativeMode = false;
  currentHistoryWeek = weekId;
  closeHistoryPicker();
  const isPrevWeek = weekId === PREV_WEEK_ID;
  document.getElementById('btn-week').classList.remove('active');
  document.getElementById('btn-7days').classList.toggle('active', isPrevWeek);
  document.getElementById('btn-history').classList.toggle('active', !isPrevWeek);
  document.getElementById('btn-leaderboard').classList.remove('active');
  render();
}

function showLeaderboard() {
  cumulativeMode = true;
  currentHistoryWeek = null;
  document.getElementById('btn-week').classList.remove('active');
  document.getElementById('btn-7days').classList.remove('active');
  document.getElementById('btn-history').classList.remove('active');
  document.getElementById('btn-leaderboard').classList.add('active');
  render();
}


document.getElementById('btn-week').textContent = 'Week of ' + sundayOfWeek('__CURRENT_WEEK_ID__');
render();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def get_week_id() -> str:
    """Return ISO week id for current week in configured timezone, e.g. '2026-W09'."""
    try:
        import pytz
        tz = pytz.timezone(config.TIMEZONE)
        now = datetime.now(tz)
    except Exception:
        from datetime import timezone
        now = datetime.now(timezone.utc)
    iso = now.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def save_week_history(week_id: str, label: str, week_data: dict):
    """Save current week data to dashboard/history/{week_id}.json."""
    hist_dir = Path(__file__).parent / "dashboard" / "history"
    hist_dir.mkdir(parents=True, exist_ok=True)
    payload = {"week_id": week_id, "label": label, "all": week_data["all"]}
    (hist_dir / f"{week_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_history() -> dict:
    """Load all historical weeks from dashboard/history/*.json."""
    hist_dir = Path(__file__).parent / "dashboard" / "history"
    if not hist_dir.exists():
        return {}
    result = {}
    for f in sorted(hist_dir.glob("20*.json")):
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
            result[obj["week_id"]] = obj
        except Exception:
            pass
    return result


def save_daily_snapshot(date_str: str, label: str, week_data: dict):
    daily_dir = Path(__file__).parent / "dashboard" / "history" / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    payload = {"date": date_str, "label": label, "all": week_data["all"]}
    (daily_dir / f"{date_str}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_daily_snapshots() -> dict:
    daily_dir = Path(__file__).parent / "dashboard" / "history" / "daily"
    if not daily_dir.exists():
        return {}
    result = {}
    for f in sorted(daily_dir.glob("*.json")):
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
            result[obj["date"]] = obj
        except Exception:
            pass
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


def generate():
    print("Fetching data from Strava...")

    token   = strava_client.get_access_token()
    members = strava_client.fetch_club_members(token)

    week_id = get_week_id()
    history = load_history()

    print("  Fetching all club activities...")
    activities = strava_client.fetch_club_activities(token)

    label = week_label_for_id(week_id)
    week_data = build_week_data(activities, members, label)
    save_week_history(week_id, label, week_data)

    today = datetime.now(_TZ8)
    date_str = today.strftime("%Y-%m-%d")
    date_label = f"{today.day}.{today.month}.{today.year}"
    save_daily_snapshot(date_str, date_label, week_data)
    daily_snapshots = load_daily_snapshots()

    history = load_history()
    # exclude current week from history tabs (it's shown as live)
    history_past = {k: v for k, v in history.items() if k != week_id}
    prev_week_id = max(history_past.keys()) if history_past else ""

    data = {"week": history.get(week_id, {"all": {}})}

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
    html = html.replace("__HISTORY_DATA__", json.dumps(history_past, ensure_ascii=False))
    html = html.replace("__DAILY_DATA__", json.dumps(daily_snapshots, ensure_ascii=False))
    html = html.replace("__CURRENT_WEEK_ID__", week_id)
    html = html.replace("__PREV_WEEK_ID__", prev_week_id)
    html = html.replace("__UPDATED_HUMAN__", human_label)
    html = html.replace("__WEATHER__", weather_html)
    html = html.replace("__CLUB_NAME__", club_name)
    html = html.replace("__CLUB_SHORT__", club_short)
    html = html.replace("__CLUB_ID__", config.STRAVA_CLUB_ID)

    out_dir = Path(__file__).parent / "dashboard"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")

    w = data["week"]["all"]
    print(f"Generated: {out_path}")
    print(f"  This week: {w.get('count', 0)} activities, {w.get('athlete_count', 0)} runners")


if __name__ == "__main__":
    generate()
    # try:
    #     generate()
    # except strava_client.StravaAuthError as e:
    #     print(f"\n⚠️  STRAVA AUTH ERROR: {e}")
    #     print("Dashboard not updated. Skipping this run.")
    # except Exception as e:
    #     print(f"\n⚠️  UNEXPECTED ERROR: {e}")
    #     print("Dashboard not updated. Skipping this run.")
