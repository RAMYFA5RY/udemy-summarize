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


_EPILOG = """\
\b
Examples:
  # Scrape a course into a local folder
  udemy-grab https://www.udemy.com/course/python-bootcamp/ --vault ./output
  # Use the OBSIDIAN_VAULT env var instead of --vault
  export OBSIDIAN_VAULT=~/Obsidian/MyVault
  udemy-grab https://www.udemy.com/course/python-bootcamp/
  # Watch the browser work (debugging)
  udemy-grab https://www.udemy.com/course/python-bootcamp/ --vault ./output --headful
  # Force a fresh Udemy login
  udemy-grab https://www.udemy.com/course/python-bootcamp/ --vault ./output --reauth

\b
Notes:
  - Output is one markdown file per section, under
    <vault>/_inbox/Udemy/<course-slug>/
  - Re-runs are resumable: sections whose file already exists are skipped.
  - The first run opens a visible browser so you can complete login (2FA);
    the session is saved and reused afterwards.
"""


@click.command(epilog=_EPILOG)
@click.argument("course_url", metavar="COURSE_URL")
@click.option(
    "--vault",
    envvar="OBSIDIAN_VAULT",
    required=True,
    metavar="PATH",
    help="Obsidian vault root path. Defaults to the OBSIDIAN_VAULT env var.",
)
@click.option(
    "--subdir",
    default="_inbox/Udemy",
    show_default=True,
    metavar="PATH",
    help="Sub-path under the vault for course folders. "
         "Use '.' to write course folders directly into the vault root.",
)
@click.option(
    "--reauth",
    is_flag=True,
    default=False,
    help="Force a fresh Udemy login even if a saved session exists.",
)
@click.option(
    "--headful",
    is_flag=True,
    default=False,
    help="Show the browser window while scraping. Default: headless.",
)
@click.version_option(package_name="udemy-grab", message="%(prog)s %(version)s")
def main(course_url: str, vault: str, subdir: str, reauth: bool, headful: bool) -> None:
    """Scrape Udemy course transcripts into an Obsidian vault.

    Walks a course's curriculum, extracts the transcript panel for every
    lecture, and writes one clean markdown file per section into the vault's
    _inbox/Udemy/ folder.

    \b
    COURSE_URL  Full URL of the Udemy course, e.g.
                https://www.udemy.com/course/python-bootcamp/
    """
    vault_root = Path(vault).expanduser().resolve()

    # ── Validate the output location up front ─────────────────────────────
    if vault_root.exists() and not vault_root.is_dir():
        click.echo(f"[FAIL] --vault path is not a directory: {vault_root}", err=True)
        sys.exit(1)
    try:
        vault_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        click.echo(f"[FAIL] Cannot create vault directory {vault_root}: {exc}", err=True)
        sys.exit(1)

    # ── Auth ──────────────────────────────────────────────────────────────
    if reauth or not is_session_valid():
        login()

    slug = course_slug(course_url)
    course_dir = (vault_root / subdir if subdir else vault_root) / slug
    course_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f"Output  : {course_dir}")

    with session_browser(headless=not headful) as ctx:
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
            out_path = section_file_path(
                vault_root, subdir, slug, section.section_number, section.section_title
            )

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
                subdir=subdir,
            )
            click.echo(f"  → {written}")

        page.close()

    click.echo("\nDone.")
