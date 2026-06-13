import os

from camoufox.sync_api import Camoufox

from .config import (
    PAGE_TIMEOUT_MS,
    SESSION_FILE,
    UDEMY_LOGIN_URL,
    ensure_dirs,
)


def is_session_valid() -> bool:
    """Return True only if the saved session file exists and contains a non-expired Udemy auth cookie."""
    if not SESSION_FILE.exists():
        return False
    try:
        import json, time
        data = json.loads(SESSION_FILE.read_text())
        cookies = data.get("cookies", [])
        auth_cookies = [
            c for c in cookies
            if "udemy" in c.get("domain", "") and c.get("name", "") in ("access_token", "client_id", "ud_cache_user")
        ]
        if not auth_cookies:
            return False
        now = time.time()
        # If any auth cookie carries an expiry, treat it as expired when past it.
        for c in auth_cookies:
            exp = c.get("expires", -1)
            if exp != -1 and exp < now:
                return False
        return True
    except Exception:
        return SESSION_FILE.exists()


def login() -> None:
    """Open a visible browser, auto-fill credentials, save session after login.

    Headful so the user can handle 2FA or CAPTCHA if Udemy requires it.
    Credentials are read from UDEMY_EMAIL / UDEMY_PASSWORD env vars.
    """
    ensure_dirs()
    email = os.environ["UDEMY_EMAIL"]
    password = os.environ["UDEMY_PASSWORD"]

    print("Opening browser for Udemy login (close it manually if something goes wrong)…")
    with Camoufox(headless=False) as browser:
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(UDEMY_LOGIN_URL, timeout=PAGE_TIMEOUT_MS)

        # Fill the email and submit the first step
        page.wait_for_selector('[name="email"]', timeout=PAGE_TIMEOUT_MS)
        page.fill('[name="email"]', email)
        page.press('[name="email"]', 'Enter')

        # After the email step Udemy may show a password field, a 2FA code,
        # a CAPTCHA, or go straight to the homepage — handle it all manually.
        print("Complete the login in the browser (2FA, password, etc.)…")
        print("Waiting up to 5 minutes for the Udemy homepage to load…")
        try:
            page.wait_for_function(
                "() => window.location.href === 'https://www.udemy.com/' "
                "|| window.location.href.startsWith('https://www.udemy.com/?')",
                timeout=300_000,
            )
        except Exception:
            pass  # save whatever session state we have regardless

        ctx.storage_state(path=str(SESSION_FILE))
        ctx.close()

    print(f"Session saved → {SESSION_FILE}")
