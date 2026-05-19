from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .config import PAGE_TIMEOUT_MS

# Udemy auto-numbers these curriculum item types with a fixed "<Type> N:" prefix.
# None of them carry a transcript, and the quiz app in particular triggers a
# Firefox driver crash on load, so we skip navigating to them entirely.
_NON_VIDEO_TITLE = re.compile(
    r"^(Quiz|Practice Test|Assignment|Coding Exercise)\s+\d+\s*:",
    re.IGNORECASE,
)


@dataclass
class SectionInfo:
    section_idx: int       # 0-based; matches data-purpose="section-panel-{N}"
    section_number: int    # 1-based; used for file naming and display
    section_title: str
    lectures: list[str] = field(default_factory=list)  # lecture titles in order


def course_slug(url: str) -> str:
    parts = [p for p in urlparse(url).path.split("/") if p]
    try:
        return parts[parts.index("course") + 1]
    except (ValueError, IndexError):
        return parts[-1] if parts else "unknown-course"


def is_non_video_item(title: str) -> bool:
    """True for curriculum items that never have a transcript (quizzes etc.).

    Detected purely from Udemy's auto-assigned "<Type> N:" title prefix, so no
    navigation is needed — important because loading a quiz page crashes the
    Playwright Firefox driver outright.
    """
    return bool(_NON_VIDEO_TITLE.match(title.strip()))


def learn_url(course_url: str) -> str:
    """Return the /learn/ page URL for a course, derived from any course URL."""
    return f"https://www.udemy.com/course/{course_slug(course_url)}/learn/"


def get_curriculum(page, course_url: str) -> tuple[str, list[SectionInfo]]:
    """Navigate to the course /learn/ page and return (title, sections).

    Expands every section to force Udemy to render its lecture list into the DOM,
    then reads titles and lecture names by data-purpose attributes.
    Uses a caller-supplied page so the same browser context is reused for scraping.
    """
    page.goto(learn_url(course_url), timeout=PAGE_TIMEOUT_MS)
    page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT_MS)

    title = _get_course_title(page)
    sections = _get_section_structure(page)
    return title, sections


# ---------------------------------------------------------------------------
# Curriculum parsing
# ---------------------------------------------------------------------------


def _get_course_title(page) -> str:
    try:
        el = page.query_selector("h1 a")
        if el:
            return el.inner_text().strip()
        el = page.query_selector("h1")
        if el:
            return el.inner_text().strip()
    except Exception:
        pass
    return "Unknown Course"


def _get_section_structure(page) -> list[SectionInfo]:
    # All section panels are in the DOM even before expanding;
    # their *lecture items* are lazy-rendered on first expand.
    panels = page.query_selector_all("[data-purpose^='section-panel-']")
    sections: list[SectionInfo] = []

    for idx, panel in enumerate(panels):
        title_el = panel.query_selector(".ud-accordion-panel-title span")
        section_title = title_el.inner_text().strip() if title_el else f"Section {idx + 1}"

        # Expand collapsed sections so lecture items are injected into the DOM
        _expand_panel(page, idx)

        lecture_els = panel.query_selector_all("[data-purpose='item-title']")
        lecture_titles = [el.inner_text().strip() for el in lecture_els]

        sections.append(SectionInfo(
            section_idx=idx,
            section_number=idx + 1,
            section_title=section_title,
            lectures=lecture_titles,
        ))

    return sections


def _expand_panel(page, section_idx: int) -> None:
    """Ensure a section panel is expanded and its lecture items are in the DOM.

    The lecture-page sidebar virtualises its list: a panel can report
    aria-expanded="true" while its items are absent from the DOM simply because
    the panel is scrolled out of view. So scroll the panel into view first —
    which forces the virtualiser to mount its items — then expand it if it is
    still collapsed.
    """
    panel_sel = f"[data-purpose='section-panel-{section_idx}']"
    panel = page.query_selector(panel_sel)
    if not panel:
        return

    # Scroll the panel into view so the virtualised list mounts its items.
    try:
        panel.scroll_into_view_if_needed(timeout=5_000)
    except Exception:
        pass

    toggle = panel.query_selector("button.js-panel-toggler")
    if toggle and toggle.get_attribute("aria-expanded") != "true":
        # JS click — transcript sidebar can overlap and intercept real pointer events
        page.eval_on_selector(
            f"{panel_sel} button.js-panel-toggler",
            "el => el.click()",
        )

    try:
        page.wait_for_selector(
            f"[data-purpose^='curriculum-item-{section_idx}-']",
            timeout=10_000,
            state="attached",
        )
    except Exception:
        pass  # genuinely empty section, or items still virtualised


# ---------------------------------------------------------------------------
# Navigation helpers (called by cli.py)
# ---------------------------------------------------------------------------


def ensure_section_expanded(page, section_idx: int) -> None:
    """Re-expand a section if the sidebar has collapsed it since initial load."""
    _expand_panel(page, section_idx)


def navigate_to_lecture(page, section_idx: int, lecture_idx: int) -> str:
    """Click the lecture item in the sidebar and return the lecture URL.

    Uses a JS click rather than page.click() because the transcript panel from
    the previous lecture frequently overlaps the curriculum sidebar and
    intercepts real pointer events. If the item is not in the DOM, the section
    panel is re-scrolled into view and re-expanded once — the sidebar
    virtualises long courses and drops off-screen items.
    """
    selector = f"[data-purpose='curriculum-item-{section_idx}-{lecture_idx}']"
    try:
        page.wait_for_selector(selector, timeout=10_000, state="attached")
    except Exception:
        _expand_panel(page, section_idx)
        page.wait_for_selector(selector, timeout=10_000, state="attached")
    page.eval_on_selector(selector, "el => el.click()")
    page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT_MS)
    return page.url
