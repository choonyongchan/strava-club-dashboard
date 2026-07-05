# Graph Report - .  (2026-07-06)

## Corpus Check
- 28 files · ~107,911 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 82 nodes · 113 edges · 16 communities (9 shown, 7 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 12 edges (avg confidence: 0.78)
- Token cost: 52,000 input · 26,240 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Dashboard UI & Riders|Dashboard UI & Riders]]
- [[_COMMUNITY_Deploy Pipeline & Docs|Deploy Pipeline & Docs]]
- [[_COMMUNITY_Report Generation|Report Generation]]
- [[_COMMUNITY_Week ID Utilities|Week ID Utilities]]
- [[_COMMUNITY_Weekly Data Snapshot Pipeline|Weekly Data Snapshot Pipeline]]
- [[_COMMUNITY_Strava API Client|Strava API Client]]
- [[_COMMUNITY_Setup & Configuration|Setup & Configuration]]
- [[_COMMUNITY_Strava Auth|Strava Auth]]
- [[_COMMUNITY_Name Mapping & Truncation|Name Mapping & Truncation]]
- [[_COMMUNITY_CLAUDE.md Principles|CLAUDE.md Principles]]
- [[_COMMUNITY_Weather Fetch|Weather Fetch]]
- [[_COMMUNITY_History Loading|History Loading]]
- [[_COMMUNITY_UnitCompany Mapping|Unit/Company Mapping]]
- [[_COMMUNITY_JSON Safety Helper|JSON Safety Helper]]
- [[_COMMUNITY_Timestamp Labeling|Timestamp Labeling]]
- [[_COMMUNITY_TODO Backlog|TODO Backlog]]

## God Nodes (most connected - your core abstractions)
1. `generate()` - 12 edges
2. `Weekly Report Dashboard Screenshot` - 10 edges
3. `Rider Leaderboard Table` - 6 edges
4. `_now_tz()` - 5 edges
5. `get_week_id()` - 5 edges
6. `dashboard/index.html (generated dashboard)` - 5 edges
7. `How It Works pipeline diagram` - 5 edges
8. `Awards Section (Distance King, Climbing King, Marathoner, Fastest, Longest Ride, Mountain Goat, Flat Rider)` - 5 edges
9. `now_label()` - 4 edges
10. `week_label_for_id()` - 4 edges

## Surprising Connections (you probably didn't know these)
- `Simplicity First principle` --semantically_similar_to--> `Key design decisions (no server, no DB, e-bike fair play, rate-limit friendly)`  [INFERRED] [semantically similar]
  CLAUDE.md → README.md
- `dashboard/index.html (generated dashboard)` --references--> `Open-Meteo weather API`  [INFERRED]
  dashboard/index.html → README.md
- `GitHub Pages` --references--> `Deploy Static Content to Pages (workflow)`  [INFERRED]
  README.md → .github/workflows/pages.yml
- `Deploy Static Content to Pages (workflow)` --references--> `dashboard/index.html (generated dashboard)`  [EXTRACTED]
  .github/workflows/pages.yml → dashboard/index.html
- `GitHub Actions` --references--> `Update Strava Dashboard (workflow)`  [INFERRED]
  README.md → .github/workflows/update.yml

## Import Cycles
- 1-file cycle: `generate.py -> generate.py`

## Hyperedges (group relationships)
- **Hourly generate-and-deploy pipeline (update.yml -> generate.py -> dashboard/index.html -> pages.yml)** — workflows_update_workflow, generate_py, dashboard_index_html, workflows_pages_deploy_workflow [EXTRACTED 1.00]
- **Strava data-to-dashboard computation pipeline described in README** — strava_client_py, report_generator_py, generate_py, dashboard_index_html [EXTRACTED 1.00]
- **CLAUDE.md behavioral guideline set** — claude_md_think_before_coding, claude_md_simplicity_first, claude_md_surgical_changes, claude_md_goal_driven_execution [EXTRACTED 1.00]

## Communities (16 total, 7 thin omitted)

### Community 0 - "Dashboard UI & Riders"
Cohesion: 0.17
Nodes (17): Activity Type Filter (All / Outdoor / Indoor), Awards Section (Distance King, Climbing King, Marathoner, Fastest, Longest Ride, Mountain Goat, Flat Rider), Weekly Report Dashboard Screenshot, Demo Cycling Club (DCC), Devices in the Club (Apple Watch, Bosch eBike, Garmin Edge, Hammerhead Karoo 2, Wahoo ELEMNT ROAM, Zwift), Fun Stats Section (Virtual Cyclist, E-Biker, Break King), Hourly Auto-Update ('Updated hourly · last update 5.4.2026 08:57'), Period Filter Tabs (This Week / Last Week / History) (+9 more)

### Community 1 - "Deploy Pipeline & Docs"
Cohesion: 0.20
Nodes (11): Simplicity First principle, Surgical Changes principle, GitHub Actions, GitHub Pages, Open-Meteo weather API, dashboard/index.html (generated dashboard), GitHub Secrets configuration, Key design decisions (no server, no DB, e-bike fair play, rate-limit friendly) (+3 more)

### Community 2 - "Report Generation"
Cohesion: 0.33
Nodes (5): Strava API, How It Works pipeline diagram, compute_stats(), Statistics computation engine for Strava club activities., Compute all statistics from club activities.     members: optional member list

### Community 3 - "Week ID Utilities"
Cohesion: 0.40
Nodes (6): datetime, get_week_id(), _now_tz(), Return ISO week id for current week in configured timezone, e.g. '2026-W09'., Return current time in configured timezone, falling back to UTC., week_label_for_id()

### Community 4 - "Weekly Data Snapshot Pipeline"
Cohesion: 0.33
Nodes (6): build_week_data(), generate(), load_daily_snapshots(), Save current week data to dashboard/history/{week_id}.json., save_daily_snapshot(), save_week_history()

### Community 5 - "Strava API Client"
Cohesion: 0.33
Nodes (5): fetch_club_activities(), fetch_club_members(), Strava OAuth token refresh + club API calls., Fetch club activities with pagination.     after: Unix timestamp — only return, Fetch club member list (firstname, lastname, id).

### Community 6 - "Setup & Configuration"
Cohesion: 0.40
Nodes (3): Central configuration loaded from .env file., Quick Start setup guide, One-time helper to obtain a Strava refresh_token.  Usage:   python3 setup_str

### Community 7 - "Strava Auth"
Cohesion: 0.40
Nodes (5): Exception, get_access_token(), Exchange refresh token for a fresh access token., Raised when Strava authentication fails., StravaAuthError

### Community 8 - "Name Mapping & Truncation"
Cohesion: 0.50
Nodes (4): _all_truncations(), load_name_map(), Generate a static dashboard/index.html from current Strava club data. Run local, Yield every possible API-truncated form by splitting at each word boundary.

## Knowledge Gaps
- **8 isolated node(s):** `Enable ingestion of excel sheet (name and unit mapping)`, `Filter for All, 40SAR, 41SAR, 8SAB unit sets`, `Stat Summary Cards (Total km, Elevation, Activities, Riders)`, `Period Filter Tabs (This Week / Last Week / History)`, `Activity Type Filter (All / Outdoor / Indoor)` (+3 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `dashboard/index.html (generated dashboard)` connect `Deploy Pipeline & Docs` to `Name Mapping & Truncation`, `Report Generation`?**
  _High betweenness centrality (0.108) - this node is a cross-community bridge._
- **Why does `Update Strava Dashboard (workflow)` connect `Deploy Pipeline & Docs` to `Name Mapping & Truncation`?**
  _High betweenness centrality (0.057) - this node is a cross-community bridge._
- **Why does `How It Works pipeline diagram` connect `Report Generation` to `Name Mapping & Truncation`, `Deploy Pipeline & Docs`, `Strava API Client`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **What connects `Central configuration loaded from .env file.`, `Generate a static dashboard/index.html from current Strava club data. Run local`, `Yield every possible API-truncated form by splitting at each word boundary.` to the rest of the system?**
  _30 weakly-connected nodes found - possible documentation gaps or missing edges._