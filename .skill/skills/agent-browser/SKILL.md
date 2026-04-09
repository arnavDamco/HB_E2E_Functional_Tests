---
name: agent-browser
description: Browser automation via the agent-browser CLI for web testing, form filling, navigation, screenshots, and data extraction. Use when the user asks to automate browser interactions, run test cases against a web application, execute QA test steps, take screenshots of web pages, fill forms, verify UI elements, or perform any browser-based testing or automation task. Triggers on mentions of "agent-browser", "browser automation", "run test cases", "web testing", "UI testing", or requests to interact with web applications programmatically.
---

# Agent Browser

Fast Rust CLI for browser automation. All interaction happens via `agent-browser <command>` in the shell.

## Setup

```bash
npm install -g agent-browser
agent-browser install    # Downloads Chrome for Testing (first run only)
```

Verify: `agent-browser open https://example.com && agent-browser get title && agent-browser close`

## Core Interaction Loop

Every browser interaction follows this cycle:

```
1. open <url>              Navigate to page
2. snapshot -i             Get interactive elements with @refs
3. <action> @eN            Interact using refs (click, fill, select, etc.)
4. snapshot -i             Re-snapshot (refs are invalidated after DOM changes)
5. get text @eN / wait     Verify results
```

**Critical rules:**
- Always `snapshot -i` before interacting -- never guess refs
- Always re-snapshot after any action that changes the DOM
- Always `wait --load networkidle` after navigation or form submission
- Use `--headed` flag when debugging to see the browser: `agent-browser --headed open <url>`

## Essential Commands

### Navigate
```bash
agent-browser open <url>                 # Go to page
agent-browser back / forward / reload    # History navigation
```

### Discover elements
```bash
agent-browser snapshot -i                # Interactive elements with @refs (primary tool)
agent-browser snapshot -i -c             # Compact format (less tokens)
agent-browser snapshot -s "table"        # Scope to CSS selector
```

### Interact
```bash
agent-browser click @e3                  # Click
agent-browser fill @e1 "text"            # Clear + type into input
agent-browser select @e2 "value"         # Dropdown selection
agent-browser check @e4 / uncheck @e4   # Checkbox
agent-browser press Enter                # Keyboard
agent-browser press Tab                  # Tab between fields
```

### Verify
```bash
agent-browser get text @e5               # Read element text
agent-browser get value @e3              # Read input value
agent-browser get url                    # Current URL
agent-browser is visible @e5             # true/false
agent-browser is enabled @e3             # true/false
agent-browser is checked @e4             # true/false
agent-browser get count ".item"          # Count matching elements
```

### Wait
```bash
agent-browser wait --load networkidle    # Wait for page to settle
agent-browser wait --text "Success"      # Wait for text to appear
agent-browser wait "#spinner" --state hidden  # Wait for element to disappear
agent-browser wait 2000                  # Wait milliseconds
```

### Screenshot
```bash
agent-browser screenshot evidence.png    # Capture viewport
agent-browser screenshot --full page.png # Full page
```

### Semantic locators (alternative to @refs)
```bash
agent-browser find text "Submit" click
agent-browser find label "Email" fill "user@test.com"
agent-browser find placeholder "Search" type "query"
agent-browser find testid "submit-btn" click
```

## Login Pattern

```bash
agent-browser open <login-url>
agent-browser snapshot -i
agent-browser fill @e1 "username"
agent-browser fill @e2 "password"
agent-browser click @e3                  # Login button
agent-browser wait --load networkidle
agent-browser state save ./auth.json     # Save for reuse
```

Subsequent runs: `agent-browser state load ./auth.json`

## Executing Test Cases from the Database

Test cases are stored in `tests.db` with columns: steps, expected_result, target_url.

### Workflow per test case:
1. Read the test case (steps, expected result, target URL)
2. Ensure pre-conditions (logged in, correct page)
3. Translate each step to agent-browser commands
4. Execute, re-snapshot after each action
5. Verify expected result
6. Screenshot as evidence

### Step translation examples:

| Human Step | Commands |
|-----------|----------|
| "Navigate to Claims Dashboard" | `open <url>` + `wait --load networkidle` |
| "Click New Claim button" | `snapshot -i` + `find text "New Claim" click` |
| "Enter Policy Number POL-001" | `snapshot -i` + find field + `fill @eN "POL-001"` |
| "Select Fire from Loss Type" | `select @eN "Fire"` or click custom dropdown |
| "Verify status shows Open" | `get text @eN` and compare |
| "Verify Submit button is disabled" | `is enabled @eN` returns false |
| "Verify success message" | `wait --text "successfully"` |

### Custom dropdowns (non-native `<select>`):
```bash
agent-browser click @e3              # Open dropdown
agent-browser snapshot -i            # See options
agent-browser click @e8              # Select option
```

### Searchable/typeahead dropdowns:
```bash
agent-browser click @e3              # Focus
agent-browser type @e3 "search"      # Type to filter
agent-browser wait 1000              # Wait for results
agent-browser snapshot -i            # See filtered list
agent-browser click @e10             # Select
```

## Session Management

```bash
agent-browser --session test1 open <url>    # Isolated session
agent-browser --session test2 open <url>    # Parallel session
agent-browser session list                  # List active sessions
agent-browser close                         # Close current
agent-browser close --all                   # Close all
```

## Debugging

```bash
agent-browser --headed open <url>           # Visible browser
agent-browser console                       # Browser console logs
agent-browser errors                        # JS errors
agent-browser highlight @e1                 # Visually highlight element
agent-browser screenshot debug.png          # Capture current state
```

## Full Reference

- **All commands:** Read [references/commands.md](references/commands.md) for the complete CLI reference (navigation, network, cookies, storage, frames, tabs, recording, diffs, batch execution, config)
- **Workflow patterns:** Read [references/workflows.md](references/workflows.md) for detailed patterns (login, forms, tables, modals, error handling, test case execution)
