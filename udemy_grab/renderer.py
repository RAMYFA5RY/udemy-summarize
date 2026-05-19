from __future__ import annotations

import os
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
    """Return the markdown file path for a section inside the vault inbox."""
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
    """Write one section's lectures to a markdown file and return its path.

    The destination directory is created if missing. The file is written
    atomically (to a temp file, then renamed) so an interrupted run can never
    leave a half-written or corrupt markdown file behind.
    """
    out_path = section_file_path(vault_root, course_slug, section_number, section_title)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    course_tag = slugify(course_title, separator="-")
    today = date.today().isoformat()

    lines: list[str] = [
        "---",
        f"course: {_yaml_quote(course_title)}",
        f"section: {_yaml_quote(section_title)}",
        f"section_number: {section_number}",
        f"source_url: {_yaml_quote(course_url)}",
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

    content = "\n".join(lines).rstrip("\n") + "\n"
    _atomic_write(out_path, content)
    return out_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _yaml_quote(value: str) -> str:
    """Double-quote a string for YAML frontmatter, escaping embedded quotes."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically via a sibling temp file + os.replace."""
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)
