#!/usr/bin/env python3
"""Patch a known Playwright Firefox driver crash.

When a page throws an uncaught JavaScript error that carries no source
``location`` (Udemy quiz and some lecture pages do this), Playwright's bundled
Node driver crashes and aborts the scrape with "Connection closed while
reading from the driver". There are two failure points, and this script fixes
both:

1. The driver reads ``pageError.location.url`` with no guard, so a missing
   ``location`` throws a ``TypeError``.
2. Even guarded, an ``undefined`` url/line/column fails the driver's own event
   schema validation ("expected string, got undefined").

The fix rewrites the ``pageError`` location object to use optional chaining
with valid-typed fallbacks (``"" `` for the url, ``0`` for line/column), so a
missing location dispatches a harmless empty location instead of crashing.

It is idempotent: a regex matches the location block in any state (original,
half-patched, or fully patched) and rewrites it to the final form, so a second
run reports "already patched" and changes nothing.

Run it after creating or reinstalling the virtualenv, since the driver lives
inside the (gitignored) environment and a reinstall reverts the patch:

    .udemy_env/bin/python scripts/patch_playwright.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Matches the pageError `location` object in any state — original
# (`pageError.location.url`), the optional-chaining-only interim patch, or the
# final patched form — and rewrites it to the final form below.
_LOCATION_BLOCK = re.compile(
    r"""location:\s*\{\s*
        url:\s*pageError\.location\??\.url(?:\s*\?\?\s*"")?,\s*
        line:\s*pageError\.location\??\.lineNumber(?:\s*\?\?\s*0)?,\s*
        column:\s*pageError\.location\??\.columnNumber(?:\s*\?\?\s*0)?\s*
        \}""",
    re.VERBOSE,
)

_PATCHED_BLOCK = (
    "location: {\n"
    '              url: pageError.location?.url ?? "",\n'
    "              line: pageError.location?.lineNumber ?? 0,\n"
    "              column: pageError.location?.columnNumber ?? 0\n"
    "            }"
)


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
    matches = _LOCATION_BLOCK.findall(source)
    if not matches:
        print(f"[FAIL] pageError location block not found in {bundle} — "
              "Playwright internals may have changed.", file=sys.stderr)
        return 1

    patched = _LOCATION_BLOCK.sub(_PATCHED_BLOCK, source)
    if patched == source:
        print(f"[OK] Already patched ({len(matches)} site(s)): {bundle}")
        return 0

    bundle.write_text(patched, encoding="utf-8")
    print(f"[OK] Patched {len(matches)} site(s) in {bundle}")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
