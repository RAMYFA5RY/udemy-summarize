from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .config import PAGE_TIMEOUT_MS

_API_BASE = "https://www.udemy.com/api-2.0"
_CHAPTER_CLASS = "chapter"
# Curriculum item _class -> URL path segment for that item's page.
_ITEM_PATH = {"lecture": "lecture", "quiz": "quiz", "practice": "practice"}
# Item kinds that never carry a transcript — the caller skips navigating to them.
SKIP_KINDS = frozenset({"quiz", "practice"})
# Course id as it appears in the api-2.0 traffic the /learn/ page fires.
_COURSE_ID_RE = re.compile(r"/api-2\.0/.*?courses/(\d+)")


@dataclass
class LectureRef:
    """One curriculum item: display title, direct lecture URL, and Udemy _class.

    url is None only when the API returned no id for the item (rare); the
    caller skips such items rather than navigating to them.
    """
    title: str
    url: str | None
    kind: str


@dataclass
class SectionInfo:
    section_idx: int       # 0-based list position
    section_number: int    # 1-based; used for file naming and display
    section_title: str
    lectures: list[LectureRef] = field(default_factory=list)  # in curriculum order


def course_slug(url: str) -> str:
    parts = [p for p in urlparse(url).path.split("/") if p]
    try:
        return parts[parts.index("course") + 1]
    except (ValueError, IndexError):
        return parts[-1] if parts else "unknown-course"


def learn_url(course_url: str) -> str:
    """Return the /learn/ page URL for a course, derived from any course URL."""
    return f"https://www.udemy.com/course/{course_slug(course_url)}/learn/"


def get_curriculum(page, course_url: str) -> tuple[str, list[SectionInfo]]:
    """Return (course_title, sections) for a course.

    Udemy's curriculum sidebar is plain JavaScript-routed <div>s with no
    lecture links, so the structure is read from Udemy's curriculum API
    instead. The numeric course id is sniffed from the API traffic the
    /learn/ page fires, then the full ordered curriculum is fetched in one
    pass and grouped into sections.
    """
    slug = course_slug(course_url)
    course_id = _discover_course_id(page, course_url)
    title = _get_course_title(page)
    items = _fetch_curriculum_items(page, course_id)
    return title, _build_sections(slug, items)


def goto_lecture(page, url: str) -> str:
    """Navigate directly to a lecture URL, bypassing the curriculum sidebar.

    A direct page.goto sidesteps the sidebar's pointer-event interception and
    list virtualisation entirely — every lecture is reachable regardless of how
    far down the curriculum it sits.
    """
    page.goto(url, timeout=PAGE_TIMEOUT_MS)
    page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT_MS)
    return page.url


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _discover_course_id(page, course_url: str) -> str:
    """Load the /learn/ page and sniff the numeric course id from its API calls."""
    seen: list[str] = []

    def _on_request(request) -> None:
        match = _COURSE_ID_RE.search(request.url)
        if match:
            seen.append(match.group(1))

    page.on("request", _on_request)
    try:
        page.goto(learn_url(course_url), timeout=PAGE_TIMEOUT_MS)
        try:
            page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT_MS)
        except Exception:
            pass  # the SPA may poll forever; the id is captured long before idle
    finally:
        page.remove_listener("request", _on_request)

    if not seen:
        raise RuntimeError("could not determine the Udemy course id from page traffic")
    # The course's own id dominates the learn page's API traffic.
    return max(set(seen), key=seen.count)


def _fetch_curriculum_items(page, course_id: str) -> list[dict]:
    """Fetch the full ordered curriculum (chapters + items) from Udemy's API.

    page.request shares the browser context's session cookies, so the call is
    authenticated as the logged-in user.
    """
    url = f"{_API_BASE}/courses/{course_id}/subscriber-curriculum-items/?page_size=100"
    items: list[dict] = []
    while url:
        resp = page.request.get(url, timeout=PAGE_TIMEOUT_MS)
        if not resp.ok:
            raise RuntimeError(
                f"curriculum API returned HTTP {resp.status} for course {course_id}"
            )
        data = resp.json()
        items.extend(data.get("results", []))
        url = data.get("next")
    return items


def _build_sections(slug: str, items: list[dict]) -> list[SectionInfo]:
    """Group the flat curriculum item list into sections by chapter markers."""
    sections: list[SectionInfo] = []
    for item in items:
        kind = item.get("_class", "")
        title = (item.get("title") or "").strip()

        if kind == _CHAPTER_CLASS:
            number = len(sections) + 1
            sections.append(SectionInfo(
                section_idx=len(sections),
                section_number=number,
                section_title=f"Section {number}: {title}" if title else f"Section {number}",
            ))
            continue

        if not sections:  # items before the first chapter — hold them in one
            sections.append(SectionInfo(0, 1, "Section 1"))

        item_id = item.get("id")
        segment = _ITEM_PATH.get(kind, "lecture")
        url = (
            f"https://www.udemy.com/course/{slug}/learn/{segment}/{item_id}"
            if item_id else None
        )
        sections[-1].lectures.append(LectureRef(title=title, url=url, kind=kind))

    return sections


def _get_course_title(page) -> str:
    try:
        el = page.query_selector("h1 a") or page.query_selector("h1")
        if el:
            return el.inner_text().strip()
    except Exception:
        pass
    return "Unknown Course"
