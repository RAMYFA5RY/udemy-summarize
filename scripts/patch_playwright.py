#!/usr/bin/env python3
"""Patch a known Playwright Firefox driver crash.

Playwright's bundled Node driver reads ``pageError.location.url`` without
guarding against a missing ``location``. When a page throws an uncaught
JavaScript error that carries no location (Udemy quiz and some lecture pages
do this), the read throws a ``TypeError``, the whole Node driver process dies,
and the scrape aborts with "Connection closed while reading from the driver".

This script rewrites those reads to optional-chaining (``location?.url``) so a
missing location yields ``undefined`` instead of crashing.

It is idempotent: once patched, the unpatched text no longer exists, so a
second run reports "already patched" and changes nothing.

Run it after creating or reinstalling the virtualenv, since the driver lives
inside the (gitignored) environment and a reinstall reverts the patch:

    .udemy_env/bin/python scripts/patch_playwright.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# (unpatched, patched) — applied in order; each replacement is its own no-op
# once done, because the unpatched substring is gone after the first pass.
_REPLACEMENTS = [
    ("pageError.location.url", "pageError.location?.url"),
    ("pageError.location.lineNumber", "pageError.location?.lineNumber"),
    ("pageError.location.columnNumber", "pageError.location?.columnNumber"),
]


def _driver_bundle_path() -> Path:
    """Locate coreBundle.js inside the installed playwright package."""
    import playwright

    bundle = Path(playwright.__file__).parent / "driver" / "package" / "lib" / "coreBundle.js"
    if not bundle.is_file():
        raise FileNotFoundError(f"Playwright driver bundle not found at {bundle}")
    return bundle


def patch() -> int:
    try:
        bundle = _driver_bundle_path()
    except (ImportError, FileNotFoundError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    source = bundle.read_text(encoding="utf-8")
    patched = source
    total = 0
    for unpatched, fixed in _REPLACEMENTS:
        count = patched.count(unpatched)
        total += count
        patched = patched.replace(unpatched, fixed)

    if patched == source:
        print(f"[OK] Already patched: {bundle}")
        return 0

    bundle.write_text(patched, encoding="utf-8")
    print(f"[OK] Patched {total} occurrence(s) in {bundle}")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
