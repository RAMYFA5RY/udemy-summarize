from __future__ import annotations

from scrapling.parser import Adaptor

from .config import FINGERPRINTS_DB, PAGE_TIMEOUT_MS

_TRANSCRIPT_TOGGLE = "[data-purpose='transcript-toggle']"
_TRANSCRIPT_PANEL  = "[data-purpose='transcript-panel']"
_CUE_TEXT          = "[data-purpose='transcript-panel'] [data-purpose='cue-text']"

_CUES_PER_PARAGRAPH = 6


def get_transcript_from_page(page, retries: int = 1) -> str | None:
    """Extract cleaned transcript from the currently loaded lecture page.

    Retries on a freshly reloaded page when the first attempt comes up empty —
    the first real video in a section sometimes has not mounted its transcript
    toggle by the time we check. Lectures with no <video> element (quizzes,
    articles) are never retried, since they genuinely have no transcript.
    """
    for attempt in range(retries + 1):
        result = _try_extract(page)
        if result is not None:
            return result
        if attempt >= retries or not page.query_selector("video"):
            break
        try:
            page.reload(timeout=PAGE_TIMEOUT_MS)
            page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT_MS)
        except Exception:
            break
    return None


def _try_extract(page) -> str | None:
    """Run one transcript-extraction attempt against the current page state."""
    _ensure_transcript_visible(page)

    try:
        page.wait_for_selector(_TRANSCRIPT_PANEL, timeout=15_000, state="visible")
    except Exception:
        return None

    # Force all cues into the DOM in case the panel virtualises long transcripts.
    # Scrolls the panel's own scroll container to the bottom and waits until the
    # cue count stops growing, then resets scroll to top before reading HTML.
    _force_full_transcript_load(page)

    html = page.content()
    return _parse_transcript(html, page.url)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_transcript_visible(page) -> None:
    """Open the transcript sidebar panel if it is not already showing."""
    panel = page.query_selector(_TRANSCRIPT_PANEL)
    if panel and panel.is_visible():
        return

    # Wait for the video element to mount (skip non-video lectures fast)
    try:
        page.wait_for_selector("video", timeout=8_000, state="attached")
    except Exception:
        return  # article-only or quiz lecture — no transcript possible

    # Hover the player so the control bar (containing the toggle) renders
    video = page.query_selector("video")
    if video:
        try:
            box = video.bounding_box()
            if box:
                page.mouse.move(
                    box["x"] + box["width"] / 2,
                    box["y"] + box["height"] / 2,
                )
        except Exception:
            pass

    # Now wait for the transcript toggle button itself to mount
    try:
        page.wait_for_selector(_TRANSCRIPT_TOGGLE, timeout=15_000, state="attached")
    except Exception:
        return  # toggle never rendered

    toggle = page.query_selector(_TRANSCRIPT_TOGGLE)
    if not toggle:
        return
    if toggle.get_attribute("aria-expanded") != "true":
        try:
            toggle.scroll_into_view_if_needed()
            toggle.click()
            page.wait_for_timeout(1500)
        except Exception:
            try:
                page.evaluate(
                    "document.querySelector(\"[data-purpose='transcript-toggle']\").click()"
                )
                page.wait_for_timeout(1500)
            except Exception:
                pass


def _force_full_transcript_load(page) -> None:
    """Scroll the transcript scroll container until cue count stabilises."""
    js_scroll = """
        () => {
            const el = document.querySelector("[data-purpose='sidebar-content']")
                   || document.querySelector("[data-purpose='transcript-panel']")?.parentElement;
            if (el) el.scrollTop = el.scrollHeight;
            return document.querySelectorAll(
                "[data-purpose='transcript-panel'] [data-purpose='cue-text']"
            ).length;
        }
    """
    last_count = -1
    for _ in range(20):  # cap iterations so we never hang
        try:
            count = page.evaluate(js_scroll)
        except Exception:
            break
        if count == last_count:
            break
        last_count = count
        page.wait_for_timeout(250)

    try:  # reset scroll so the panel doesn't look odd if user is watching
        page.evaluate(
            "() => { const el = document.querySelector(\"[data-purpose='sidebar-content']\");"
            " if (el) el.scrollTop = 0; }"
        )
    except Exception:
        pass


def _parse_transcript(html: str, url: str) -> str | None:
    adaptor = _make_adaptor(html, url=url)
    cues = _find_adaptive(adaptor, _CUE_TEXT, "udemy_transcript_cue")

    if not cues:
        return None

    # Cue text is already timestamp-free — just normalise whitespace
    texts = [" ".join(cue.text.split()) for cue in cues if cue.text.strip()]
    return _merge_into_prose(texts) if texts else None


def _merge_into_prose(cues: list[str]) -> str:
    paragraphs: list[str] = []
    for i in range(0, len(cues), _CUES_PER_PARAGRAPH):
        paragraphs.append(" ".join(cues[i : i + _CUES_PER_PARAGRAPH]))
    return "\n\n".join(paragraphs)


def _make_adaptor(html: str, url: str = "") -> Adaptor:
    try:
        from scrapling.storage import SQLiteStorageSystem
        storage = SQLiteStorageSystem(db_path=str(FINGERPRINTS_DB))
        return Adaptor(html, url=url, auto_match=True, auto_match_storage=storage)
    except (ImportError, TypeError):
        return Adaptor(html, url=url)


def _find_adaptive(adaptor: Adaptor, selector: str, identifier: str):
    try:
        elements = adaptor.css(selector, adaptive=True, identifier=identifier)
        if elements:
            return elements
    except Exception:
        pass
    return adaptor.css(selector, auto_save=True, identifier=identifier)
