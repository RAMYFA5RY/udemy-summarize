from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from slugify import slugify


@dataclass
class LectureContent:
    section_number: int
    section_title: str
    lecture_title: str
    transcript: str | None


def section_file_path(
    vault_root: Path,
    course_slug: str,
    section_number: int,
    section_title: str,
) -> Path:
    section_slug = slugify(section_title)
    filename = f"{section_number:02d}-{section_slug}.md"
    return vault_root / "_inbox" / "Udemy" / course_slug / filename


def render_section(
    *,
    course_title: str,
    course_url: str,
    course_slug: str,
    section_number: int,
    section_title: str,
    lectures: list[LectureContent],
    vault_root: Path,
) -> Path:
    out_path = section_file_path(vault_root, course_slug, section_number, section_title)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    course_tag = slugify(course_title, separator="-")
    today = date.today().isoformat()

    lines: list[str] = [
        "---",
        f'course: "{course_title}"',
        f'section: "{section_title}"',
        f"section_number: {section_number}",
        f'source_url: "{course_url}"',
        f'ingested_at: "{today}"',
        f"tags: [udemy, transcript, {course_tag}]",
        "---",
        "",
    ]

    for lc in lectures:
        lines.append(f"## {lc.lecture_title}")
        lines.append("")
        lines.append(lc.transcript if lc.transcript else "*No transcript available.*")
        lines.append("")
        lines.append("---")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
