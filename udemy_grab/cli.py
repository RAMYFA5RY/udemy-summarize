from __future__ import annotations

import sys
import time
from pathlib import Path

import click

from .auth import is_session_valid, login
from .browser import session_browser
from .config import INTER_PAGE_DELAY
from .curriculum import (
    SectionInfo,
    course_slug,
    ensure_section_expanded,
    get_curriculum,
    navigate_to_lecture,
)
from .renderer import LectureContent, render_section, section_file_path
from .transcript import get_transcript_from_page


@click.command()
@click.argument("course_url")
@click.option(
    "--vault",
    envvar="OBSIDIAN_VAULT",
    required=True,
    help="Obsidian vault root path (or set OBSIDIAN_VAULT env var).",
)
@click.option(
    "--reauth",
    is_flag=True,
    default=False,
    help="Force re-authentication even if a saved session exists.",
)
def main(course_url: str, vault: str, reauth: bool) -> None:
    """Scrape Udemy course transcripts into an Obsidian vault.

    COURSE_URL  Full URL of the Udemy course, e.g.
                https://www.udemy.com/course/python-bootcamp/
    """
    vault_root = Path(vault).expanduser().resolve()

    # ── Auth ──────────────────────────────────────────────────────────────
    if reauth or not is_session_valid():
        login()

    slug = course_slug(course_url)

    with session_browser() as ctx:
        # One page object reused for the entire run — avoids browser restarts
        page = ctx.new_page()

        # ── Curriculum ────────────────────────────────────────────────────
        click.echo(f"\nFetching curriculum: {course_url}")
        try:
            course_title, sections = get_curriculum(page, course_url)
        except Exception as exc:
            click.echo(f"[FAIL] Could not scrape curriculum: {exc}", err=True)
            sys.exit(1)

        total_lectures = sum(len(s.lectures) for s in sections)
        click.echo(f"Course  : {course_title}")
        click.echo(f"Slug    : {slug}")
        click.echo(f"Sections: {len(sections)}  Lectures: {total_lectures}")

        # ── Process each section ──────────────────────────────────────────
        for section in sections:
            out_path = section_file_path(vault_root, slug, section.section_number, section.section_title)

            if out_path.exists():
                click.echo(f"\n[SKIP] §{section.section_number} {section.section_title}")
                continue

            click.echo(f"\n§{section.section_number} {section.section_title} ({len(section.lectures)} lectures)")

            # Collapsed sections need expanding before their items are clickable
            ensure_section_expanded(page, section.section_idx)

            contents: list[LectureContent] = []
            for lecture_idx, lecture_title in enumerate(section.lectures):
                time.sleep(INTER_PAGE_DELAY)
                try:
                    navigate_to_lecture(page, section.section_idx, lecture_idx)
                    transcript = get_transcript_from_page(page)
                    if transcript is None:
                        click.echo(f"  [SKIP - no transcript] {lecture_title}")
                    else:
                        click.echo(f"  [OK] {lecture_title}")
                    contents.append(LectureContent(
                        section_number=section.section_number,
                        section_title=section.section_title,
                        lecture_title=lecture_title,
                        transcript=transcript,
                    ))
                except Exception as exc:
                    click.echo(f"  [FAIL] {lecture_title}: {exc}")
                    contents.append(LectureContent(
                        section_number=section.section_number,
                        section_title=section.section_title,
                        lecture_title=lecture_title,
                        transcript=None,
                    ))

            written = render_section(
                course_title=course_title,
                course_url=course_url,
                course_slug=slug,
                section_number=section.section_number,
                section_title=section.section_title,
                lectures=contents,
                vault_root=vault_root,
            )
            click.echo(f"  → {written}")

        page.close()

    click.echo("\nDone.")
