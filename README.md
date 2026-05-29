# udemy-summarize-tool

Turn Udemy courses into clean, readable Markdown notes.

The project is a two-stage pipeline:

1. **Grab** — log in to Udemy, walk a course's curriculum, and scrape the full
   transcript of every lecture into one Markdown file per section. *Implemented,
   shipped as the `udemy-grab` CLI.*
2. **Summarize** — condense those transcripts into study notes. *Planned.*

This README covers stage 1.

## How it works

`udemy-grab` drives a stealth Firefox browser ([camoufox](https://camoufox.com/))
to sign in to your Udemy account, reads the course curriculum from Udemy's API,
visits each lecture by direct URL, opens the transcript panel, and writes the
text as Markdown — one file per course section, ready to drop into an Obsidian
vault.

## Requirements

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — package manager and runner
- A Udemy account enrolled in the course you want to grab

## Setup

This is a Python package — there is no compile step. `uv sync` installs the CLI
and all locked dependencies into a local `.venv` and exposes the `udemy-grab`
command.

```bash
# 1. Install uv (if you don't have it)
#    macOS / Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh
#    Windows (PowerShell):
#    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. Clone and enter the repo
git clone https://github.com/RAMYFA5RY/udemy-summarize.git
cd udemy-summarize

# 3. Install dependencies + the CLI — reproducible, pinned by uv.lock
uv sync

# 4. Download the camoufox browser binary (one-time)
uv run camoufox fetch

# 5. Apply the Playwright driver patch (see "The Playwright patch" below)
uv run python scripts/patch_playwright.py
```

`uv sync` is fully reproducible — it installs the exact versions pinned in
`uv.lock`. Re-run it whenever `pyproject.toml` or `uv.lock` changes.

## Credentials

`udemy-grab` reads your Udemy login from two environment variables:

| Variable         | Purpose                |
| ---------------- | ---------------------- |
| `UDEMY_EMAIL`    | Udemy account email    |
| `UDEMY_PASSWORD` | Udemy account password |

> These only fill the browser login form. The password is stored wherever you
> set it (e.g. your shell profile) — treat that file accordingly.

### macOS / Linux (zsh)

Add the exports to `~/.zshrc`, then reload it:

```bash
echo 'export UDEMY_EMAIL="you@example.com"' >> ~/.zshrc
echo 'export UDEMY_PASSWORD="your-password"' >> ~/.zshrc
source ~/.zshrc
```

(For bash, use `~/.bashrc` instead.)

### Windows

PowerShell — persistent (survives new terminals):

```powershell
setx UDEMY_EMAIL "you@example.com"
setx UDEMY_PASSWORD "your-password"
```

Open a **new** terminal afterwards for `setx` values to take effect. For the
current session only:

```powershell
$env:UDEMY_EMAIL = "you@example.com"
$env:UDEMY_PASSWORD = "your-password"
```

## Usage

```bash
uv run udemy-grab <COURSE_URL> --vault <PATH> [options]
```

Example:

```bash
uv run udemy-grab https://www.udemy.com/course/master-linux-administration \
  --vault ./output --subdir .
```

If you activate the venv first (`source .venv/bin/activate`), drop the `uv run`
prefix and just call `udemy-grab`.

### Options

| Option       | Description |
| ------------ | ----------- |
| `COURSE_URL` | Full Udemy course URL (required) |
| `--vault`    | Output root directory. Falls back to the `OBSIDIAN_VAULT` env var. Required. |
| `--subdir`   | Sub-path under the vault for course folders. Default `_inbox/Udemy`; use `.` to write straight into the vault root. |
| `--reauth`   | Force a fresh Udemy login even if a saved session exists. |
| `--headful`  | Show the browser window while scraping (default: headless). |
| `--version`  | Print the version and exit. |
| `--help`     | Show full help. |

### First run & login

The first run opens a **visible** browser and signs in with your env-var
credentials. Complete any 2FA / CAPTCHA in that window — the session is then
saved to `~/.udemy_grab/session/` and reused on later runs. When the session
expires, re-run with `--reauth` to sign in again.

### Output

One Markdown file per section:

```
<vault>/<subdir>/<course-slug>/
  01-section-1-....md
  02-section-2-....md
  ...
```

Runs are **resumable** — a section whose file already exists is skipped, so a
re-run continues where an interrupted run stopped.

## The Playwright patch

`scripts/patch_playwright.py` fixes a crash in Playwright's bundled Firefox
driver: when a page throws an uncaught JavaScript error with no source
`location`, the driver reads an undefined field and the whole driver process
dies, aborting the scrape ("Connection closed while reading from the driver").

The patch is **idempotent** and lives inside the virtual environment, so it is
**reverted whenever you recreate `.venv` or reinstall Playwright**. Re-run it
after any such change:

```bash
uv run python scripts/patch_playwright.py
```

## Roadmap

- [x] **Grab** — scrape course transcripts to Markdown
- [ ] **Summarize** — condense transcripts into study notes
