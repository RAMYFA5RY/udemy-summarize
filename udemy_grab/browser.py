from contextlib import contextmanager

from camoufox.sync_api import Camoufox

from .config import SESSION_FILE


@contextmanager
def session_browser():
    """Yield a Playwright BrowserContext pre-loaded with the saved Udemy session.

    One browser instance is shared for the entire CLI run so that lecture-to-lecture
    navigation incurs no browser-startup overhead.
    """
    with Camoufox(headless=False) as browser:
        ctx = browser.new_context(storage_state=str(SESSION_FILE))
        try:
            yield ctx
        finally:
            ctx.close()
