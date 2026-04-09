# Onboarding — Setting Up This Repository

These are instructions for **Claude Code** to follow when a user downloads this repository and asks to set it up. The user should not need to run any commands manually — Claude Code handles everything.

---

## Prerequisites

The following must be installed on the user's machine before setup:

1. **Node.js** (v18+) — needed to install agent-browser
2. **Python 3** — needed to initialize the SQLite database
3. **Claude Code** — the CLI that operates this test suite

### How to check prerequisites

```bash
node --version    # Should print v18.x or higher
python3 --version # Should print Python 3.x
sqlite3 --version # Should be available (comes with macOS/most Linux; Windows users install separately)
```

If any are missing, tell the user what to install before proceeding.

---

## Setup Steps

Run these steps in order when the user asks you to set up the repository.

### Step 1 — Install Agent Browser

```bash
npm install -g agent-browser
```

Then download the bundled test browser (Chrome for Testing):

```bash
agent-browser install
```

Verify it works:

```bash
agent-browser open https://example.com && agent-browser get title && agent-browser close
```

You should see the title "Example Domain" printed. If this fails, check that Node.js is installed and `npm` global bin is on the PATH.

### Step 2 — Verify the Database

The test database (`tests.db`) is checked into the repository. It comes pre-loaded with test definitions, modules, workflows, and shared run history. No initialization needed.

Verify it works:

```bash
sqlite3 tests.db "SELECT count(*) FROM modules;"
```

Should return `10` (the number of seeded modules).

If the database is ever missing or corrupted, recreate it:

```bash
python3 init_db.py
```

This is idempotent — it uses `CREATE TABLE IF NOT EXISTS` and `INSERT OR IGNORE`.

### Step 3 — Verify the Skill

The agent-browser skill is bundled in this repository at `.skill/skills/agent-browser/`. Claude Code reads it automatically when using the agent-browser skill. No additional registration is needed — the skill files are self-contained reference material that Claude Code uses when executing browser-based tests.

### Step 4 — Read the Project Instructions

Read `CLAUDE.md` in the repository root. It contains:

- How to run tests (smoke, critical, regression)
- How to create runs and record results in the database
- The database schema
- Module and workflow definitions
- Naming and timestamp conventions

---

## What This Repository Contains

| File/Folder | Purpose |
|---|---|
| `CLAUDE.md` | Instructions for Claude Code on how to operate this test suite |
| `init_db.py` | Python script to create/seed the SQLite database |
| `tests.db` | SQLite database with test definitions, runs, and results |
| `dashboard.py` | Single-file web dashboard for viewing tests, runs, and bugs (`python3 dashboard.py`) |
| `.skill/skills/agent-browser/` | Agent Browser skill reference (SKILL.md + command/workflow docs) |
| `onboarding.md` | This file — setup instructions |
| `.gitignore` | Ignores SQLite temp files and Python bytecode |

---

## How It Works

This repository has **no application code**. It is a test management system where:

1. **Test definitions** live in the SQLite database (`tests` table)
2. **Claude Code** is the test executor — it reads tests from the database, runs them using Agent Browser against the target web application, and records results back to the database
3. **Agent Browser** is the browser automation tool — Claude Code drives it via CLI commands to navigate pages, fill forms, click buttons, take screenshots, and verify outcomes

The workflow is:
```
User asks Claude Code to run tests
  -> Claude Code queries tests.db for matching tests
  -> Claude Code creates a run in the database
  -> For each test, Claude Code uses agent-browser to execute the steps
  -> Claude Code records pass/fail results and remarks back to tests.db
  -> Claude Code reports a summary to the user
```

---

## Troubleshooting

### `agent-browser: command not found`
The npm global bin directory is not on the PATH. Fix:
```bash
# Find where npm installs global packages
npm config get prefix
# Add <prefix>/bin to your PATH in ~/.zshrc or ~/.bashrc
```

### `agent-browser install` fails
This downloads Chromium. If behind a proxy, set `HTTPS_PROXY`. If on a restricted network, download Chrome for Testing manually and point to it:
```bash
export AGENT_BROWSER_EXECUTABLE_PATH="/path/to/chrome"
```

### `sqlite3: command not found`
- **macOS**: Comes pre-installed. If missing: `brew install sqlite`
- **Linux**: `sudo apt install sqlite3` or `sudo yum install sqlite`
- **Windows**: Download from https://sqlite.org/download.html and add to PATH

### Database is empty or corrupted
Re-run the init script — it is idempotent:
```bash
python3 init_db.py
```

### Python 3 not found
- **macOS**: `brew install python3` or use the Xcode command line tools (`xcode-select --install`)
- **Linux**: `sudo apt install python3`
- **Windows**: Download from https://python.org
