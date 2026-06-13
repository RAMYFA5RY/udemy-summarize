from __future__ import annotations

import json
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
# Fallback: course id patterns embedded in page HTML.
_HTML_COURSE_ID_RES = [
    re.compile(r'"courseId"\s*:\s*(\d+)'),
    re.compile(r'"id"\s*:\s*(\d+)\s*,\s*"_class"\s*:\s*"course"'),
    re.compile(r'data-course-id=["\'](\d+)["\']'),
    re.compile(r'/courses/(\d+)/subscriber-curriculum-items'),
]


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


def get_curriculum(page, course_url: str, debug: bool = False) -> tuple[str, list[SectionInfo]]:
    """Return (course_title, sections) for a course.

    Udemy's curriculum sidebar is plain JavaScript-routed <div>s with no
    lecture links, so the structure is read from Udemy's curriculum API
    instead. The numeric course id is sniffed from the API traffic the
    /learn/ page fires, then the full ordered curriculum is fetched in one
    pass and grouped into sections.
    """
    slug = course_slug(course_url)
    course_id = _discover_course_id(page, course_url, debug=debug)
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


def _discover_course_id(page, course_url: str, debug: bool = False) -> str:
    """Load the /learn/ page and sniff the numeric course id from its API calls.

    Falls back to scraping the course ID from the page HTML, then from the
    course landing page, so the tool works even if the user is not yet enrolled.
    """
    seen: list[str] = []
    all_api_urls: list[str] = []

    def _on_request(request) -> None:
        url = request.url
        if "api" in url or "udemy" in url:
            all_api_urls.append(url)
        match = _COURSE_ID_RE.search(url)
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

    # Detect session expiry: Udemy redirected to the login page.
    if any("/join/login-popup" in u or "/join/passwordless-auth" in u for u in all_api_urls):
        raise RuntimeError(
            "Udemy session has expired — re-run with --reauth to log in again"
        )

    if debug and not seen:
        import sys
        print("\n[DEBUG] No course ID found in request traffic. Captured URLs:", file=sys.stderr)
        for u in all_api_urls[:40]:
            print(f"  {u}", file=sys.stderr)

    if seen:
        return max(set(seen), key=seen.count)

    # API traffic approach failed (e.g. not enrolled, redirected to landing page).
    # Try extracting the course id from the current page's HTML.
    course_id = _extract_id_from_html(page.content())
    if course_id:
        return course_id

    # Last resort: navigate to the public course landing page and scrape there.
    slug = course_slug(course_url)
    page.goto(f"https://www.udemy.com/course/{slug}/", timeout=PAGE_TIMEOUT_MS)
    try:
        page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT_MS)
    except Exception:
        pass
    course_id = _extract_id_from_html(page.content())
    if course_id:
        return course_id

    raise RuntimeError("could not determine the Udemy course id from page traffic")


def _extract_id_from_html(html: str) -> str | None:
    """Try each known HTML pattern for the numeric course id."""
    for pattern in _HTML_COURSE_ID_RES:
        m = pattern.search(html)
        if m:
            return m.group(1)
    return None


def _fetch_curriculum_items(page, course_id: str) -> list[dict]:
    """Fetch the full ordered curriculum (chapters + items) from Udemy's API.

    The request is issued via fetch() inside the page so it runs same-origin
    with the real browser session (cookies, headers, user agent). Udemy
    rejects out-of-band API calls with HTTP 403.
    """
    url = f"{_API_BASE}/courses/{course_id}/subscriber-curriculum-items/?page_size=100"
    items: list[dict] = []
    while url:
        result = page.evaluate(
            """async (u) => {
                const r = await fetch(u, { credentials: 'include' });
                return { status: r.status, body: await r.text() };
            }""",
            url,
        )
        if result["status"] != 200:
            raise RuntimeError(
                f"curriculum API returned HTTP {result['status']} for course {course_id}"
            )
        data = json.loads(result["body"])
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
