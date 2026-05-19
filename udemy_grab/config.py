from pathlib import Path

GRAB_DIR = Path.home() / ".udemy_grab"
SESSION_DIR = GRAB_DIR / "session"
SESSION_FILE = SESSION_DIR / "state.json"
FINGERPRINTS_DB = GRAB_DIR / "fingerprints.db"

UDEMY_BASE = "https://www.udemy.com"
UDEMY_LOGIN_URL = f"{UDEMY_BASE}/join/login-popup/"

# Seconds to wait between lecture page loads to avoid rate limiting
INTER_PAGE_DELAY = 2.5

# Playwright timeout in milliseconds
PAGE_TIMEOUT_MS = 60_000


def ensure_dirs() -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
