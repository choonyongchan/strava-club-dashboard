# Strava Club Dashboard

Free, open-source weekly statistics dashboard for any Strava cycling club. Auto-updates every hour via GitHub Actions, hosted free on GitHub Pages.

**Features:**
- Weekly leaderboard with 20+ metrics (distance, elevation, speed, time...)
- Awards: Distance King, Climbing King, Marathoner, Fastest, Mountain Goat...
- Fun stats: Virtual Cyclist, E-Biker, Break King
- Device stats across the club
- Outdoor/Indoor activity filter
- Week history archive with visual picker
- Local weather widget
- Fully responsive (mobile + desktop)
- No database needed — JSON file storage

**[Live Demo](https://kcmi.sk/strava/)** — see it in action for Klub cyklistov Michalovce (Slovak cycling club)

![Strava Club Dashboard Screenshot](screenshot.webp)

---

## Quick Start (5 minutes)

### 1. Fork This Repository

1. Click the **Fork** button at the top of this page
2. This creates your own copy of the project

### 2. Create a Strava API Application

1. Go to [strava.com/settings/api](https://www.strava.com/settings/api)
2. Create a new application:
   - **Application Name:** anything (e.g. "My Club Dashboard")
   - **Category:** Club
   - **Website:** your GitHub Pages URL (or just `http://localhost`)
   - **Authorization Callback Domain:** `localhost`
3. Note your **Client ID** and **Client Secret**

### 3. Get Your Refresh Token

```bash
# Clone your forked repo
git clone https://github.com/YOUR_USERNAME/strava-club-dashboard.git
cd strava-club-dashboard

# Install dependencies
pip install -r requirements.txt

# Run the setup wizard
python3 src/setup_strava.py
```

The wizard will:
1. Ask for your Client ID and Client Secret
2. Give you a URL to open in your browser
3. You authorize the app on Strava
4. Your browser redirects to `localhost` (page won't load — that's expected!)
5. Copy the full URL from your browser and paste it back
6. You get your `STRAVA_REFRESH_TOKEN`

### 4. Find Your Club ID

Open your Strava club page. The URL looks like:
```
https://www.strava.com/clubs/123456
                             ^^^^^^ this is your CLUB_ID
```

### 5. Test Locally (Optional)

Copy the example config and fill in your values:

```bash
cp env.example .env
```

Edit `.env`:
```env
STRAVA_CLIENT_ID=your_id
STRAVA_CLIENT_SECRET=your_secret
STRAVA_REFRESH_TOKEN=your_token
STRAVA_CLUB_ID=123456
CLUB_NAME=My Cycling Club
WEATHER_LAT=48.75
WEATHER_LON=21.92
TIMEZONE=Europe/Bratislava
```

Generate and preview:
```bash
python3 src/generate.py
```

Open `index.html` in your browser to verify it works.

> **Note:** The `.env` file is for local testing only. For automatic updates via GitHub Actions, you need to set up GitHub Secrets (see next section).

---

## Auto-Update with GitHub Actions + GitHub Pages (Free Hosting)

### Set Up GitHub Secrets (Required)

The dashboard auto-updates every hour via GitHub Actions. **It will only run after you add your secrets** — without them, the workflow is safely skipped (no errors, no emails).

In your forked repo, go to **Settings → Secrets and variables → Actions → New repository secret** and add each one:

| Secret | Required | Value |
|--------|----------|-------|
| `STRAVA_CLIENT_ID` | **Yes** | Your Strava app Client ID (from step 2) |
| `STRAVA_CLIENT_SECRET` | **Yes** | Your Strava app Client Secret (from step 2) |
| `STRAVA_REFRESH_TOKEN` | **Yes** | Token from setup wizard (from step 3) |
| `STRAVA_CLUB_ID` | **Yes** | Your club ID number (from step 4) |
| `CLUB_NAME` | No | Display name for your club (default: "My Cycling Club") |
| `WEATHER_LAT` | No | Latitude for weather widget (find at [latlong.net](https://www.latlong.net/)) |
| `WEATHER_LON` | No | Longitude for weather widget |
| `TIMEZONE` | No | Your timezone, e.g. `Europe/Bratislava` (default: `America/New_York`). [Full list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) |

> **How to add a secret:** Go to your repo → Settings → Secrets and variables → Actions → click "New repository secret" → enter the name (e.g. `STRAVA_CLIENT_ID`) and the value → click "Add secret". Repeat for each secret.

### Enable GitHub Pages

1. Go to **Settings → Pages**
2. Source: **GitHub Actions** (the workflow deploys `index.html` via the Pages artifact, not a branch folder)
3. Save

Your dashboard will be live at `https://yourusername.github.io/strava-club-dashboard/`

### Verify It Works

1. Go to the **Actions** tab in your repo
2. Click **Update Strava Dashboard** on the left
3. Click **Run workflow** → **Run workflow** (green button)
4. Wait ~30 seconds — if it passes, your dashboard is being generated
5. Check your GitHub Pages URL after a minute

The workflow runs automatically every hour after this.

---

## Customization

### Language / Localization

The dashboard is in English by default. To translate it to your language, you can simply ask an AI assistant:

> "Translate all UI text in `src/generate.py` to Czech/Slovak/German/Spanish/..."

All translatable strings are in one place inside the `TEMPLATE` variable in `src/generate.py` — the JavaScript constants `AWARDS`, `FUN`, `EMPTY_MSGS`, button labels, and section titles.

### Colors

The accent color is Strava orange (`#FC4C02`). Search and replace in the `TEMPLATE` CSS to change it.

### Weather Location

Find your coordinates at [latlong.net](https://www.latlong.net/) and set `WEATHER_LAT` / `WEATHER_LON` in `.env`. Weather data comes from [Open-Meteo](https://open-meteo.com/) (free, no API key needed).

---

## How It Works

```
Strava API
    ↓
src/strava_client.py      → OAuth token refresh + fetch activities/members
    ↓
src/report_generator.py   → Compute 20+ statistics, awards, leaderboard
    ↓
src/generate.py           → Inject data into HTML template
    ↓
index.html                → Static file, open in any browser
src/ledger.json / ledger-clean.json → activity log (source of truth)
```

**Key design decisions:**
- **No server needed** — generates a single static HTML file
- **No database** — every activity ever fetched is appended to `src/ledger.json`, deduped into `src/ledger-clean.json`. History (per-date leaderboards) is computed on the fly from this ledger at generation time, not stored as separate snapshot files
- **E-bike fair play** — awards exclude e-bike rides (tracked separately)
- **Rate limit friendly** — uses ~4 API calls per run (Strava allows 1000/day)

---

## File Structure

```
├── index.html             # OUTPUT — the dashboard (don't edit manually!)
├── src/
│   ├── generate.py           # Main script — generates the dashboard
│   ├── strava_client.py      # Strava API client (OAuth + data fetch)
│   ├── report_generator.py   # Statistics engine (all computations)
│   ├── config.py             # Configuration from .env
│   ├── setup_strava.py       # One-time OAuth setup wizard
│   ├── nominal_roll.csv      # Name/unit/company roster
│   ├── ledger.json           # OUTPUT — raw activity log (source of truth)
│   └── ledger-clean.json     # OUTPUT — deduped activity log, used for all stats
├── test/
│   ├── test_build_grouped_data.py
│   └── test_ledger.py
├── requirements.txt      # Python dependencies
├── env.example           # Example .env file
└── .github/workflows/
    └── update.yml        # Hourly auto-update via GitHub Actions
```

---

## Requirements

- Python 3.9+
- A Strava account that's a member of the club
- The club must be set to allow member activity visibility

---

## Troubleshooting

**GitHub Actions workflow is skipped (grey icon)**
→ You haven't added the required GitHub Secrets yet. See [Set Up GitHub Secrets](#set-up-github-secrets-required) above.

**"STRAVA AUTH ERROR: refresh token is likely expired"**
→ Run `python3 src/setup_strava.py` again to get a new token. Then update the `STRAVA_REFRESH_TOKEN` secret in your repo settings.

**"ERROR: Missing required config"**
→ One or more required secrets are missing. Check that `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN`, and `STRAVA_CLUB_ID` are all set in your repo's GitHub Secrets.

**"401 Unauthorized" from Strava**
→ Your Client ID or Client Secret is incorrect. Double-check them at [strava.com/settings/api](https://www.strava.com/settings/api).

**Empty dashboard (no activities)**
→ Check that your club has activities this week. The dashboard shows Monday–Sunday.

**Weather not showing**
→ Check your `WEATHER_LAT`/`WEATHER_LON` values. Weather is optional — the dashboard works without it.

**GitHub Actions not running at all**
→ After forking, go to the **Actions** tab and enable workflows (GitHub disables them by default on forks).

---

## License

MIT — use it for your club, modify it, share it.

---

Built with data from [Strava API](https://developers.strava.com/) and weather from [Open-Meteo](https://open-meteo.com/).
