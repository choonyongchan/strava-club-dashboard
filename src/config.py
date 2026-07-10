"""Central configuration loaded from .env file."""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Required — Strava API
STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID", "")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET", "")
STRAVA_REFRESH_TOKEN = os.getenv("STRAVA_REFRESH_TOKEN", "")
STRAVA_CLUB_ID = os.getenv("STRAVA_CLUB_ID", "")

# Validate required values
_REQUIRED = {
    "STRAVA_CLIENT_ID": STRAVA_CLIENT_ID,
    "STRAVA_CLIENT_SECRET": STRAVA_CLIENT_SECRET,
    "STRAVA_REFRESH_TOKEN": STRAVA_REFRESH_TOKEN,
    "STRAVA_CLUB_ID": STRAVA_CLUB_ID,
}
_missing = [k for k, v in _REQUIRED.items() if not v]
if _missing:
    print(f"ERROR: Missing required config: {', '.join(_missing)}")
    print("Set them in .env (local) or GitHub Secrets (Actions).")
    print("Run 'python3 setup_strava.py' to get Strava credentials.")
    sys.exit(0)  # exit 0 so GitHub Actions doesn't report failure

# Optional — Dashboard customization
CLUB_NAME = os.getenv("CLUB_NAME", "My Cycling Club")
WEATHER_LAT = os.getenv("WEATHER_LAT", "40.71")
WEATHER_LON = os.getenv("WEATHER_LON", "-74.01")
TIMEZONE = os.getenv("TIMEZONE", "America/New_York")
