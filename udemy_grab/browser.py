from contextlib import contextmanager

from camoufox.sync_api import Camoufox

from .config import SESSION_FILE


@contextmanager
def session_browser(headless: bool = True):
    """Yield a Playwright BrowserContext pre-loaded with the saved Udemy session.

    One browser instance is shared for the entire CLI run so that lecture-to-lecture
    navigation incurs no browser-startup overhead. Pass headless=False to watch the
    scrape happen in a real window (useful for debugging selector issues).
    """
    with Camoufox(headless=headless) as browser:
        ctx = browser.new_context(storage_state=str(SESSION_FILE))
        try:
            yield ctx
        finally:
            ctx.close()
