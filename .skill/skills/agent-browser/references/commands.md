# Agent Browser CLI Command Reference

## Table of Contents
- [Navigation](#navigation)
- [Snapshot & Element Discovery](#snapshot--element-discovery)
- [Element Interaction](#element-interaction)
- [Keyboard & Input](#keyboard--input)
- [Scrolling & Mouse](#scrolling--mouse)
- [Semantic Locators](#semantic-locators)
- [Information Retrieval](#information-retrieval)
- [Element State Checks](#element-state-checks)
- [Screenshot & PDF](#screenshot--pdf)
- [Wait & Synchronization](#wait--synchronization)
- [JavaScript Execution](#javascript-execution)
- [Network Commands](#network-commands)
- [Session Management](#session-management)
- [State Persistence](#state-persistence)
- [Authentication](#authentication)
- [Cookies & Storage](#cookies--storage)
- [Tab & Window Management](#tab--window-management)
- [Frame Management](#frame-management)
- [Dialog Handling](#dialog-handling)
- [Viewport & Device Emulation](#viewport--device-emulation)
- [Diff & Visual Regression](#diff--visual-regression)
- [Recording & Debugging](#recording--debugging)
- [Batch Execution](#batch-execution)
- [Configuration](#configuration)

---

## Navigation

| Command | Description |
|---------|-------------|
| `open <url>` | Navigate to URL (aliases: `goto`, `navigate`). Auto-adds `https://` |
| `back` | Go back in history |
| `forward` | Go forward in history |
| `reload` | Reload current page |
| `close` | Close current session |
| `close --all` | Close all sessions |

## Snapshot & Element Discovery

| Command | Description |
|---------|-------------|
| `snapshot` | Full accessibility tree |
| `snapshot -i` | **Interactive elements only (recommended)** |
| `snapshot -c` | Compact format |
| `snapshot -d <N>` | Limit depth to N levels |
| `snapshot -s "<selector>"` | Scope to CSS selector |
| `snapshot -i --json` | JSON structured output |
| `snapshot -i -c -d 5` | Combine flags |

**Ref format:** `@e1 [tag type="value"] "text" placeholder="hint"`

**Ref lifecycle:** Refs are invalidated on navigation, form submission, or dynamic content loading. Always re-snapshot after any DOM change.

## Element Interaction

| Command | Description |
|---------|-------------|
| `click @e1` | Click element |
| `click @e1 --new-tab` | Open link in new tab |
| `dblclick @e1` | Double-click |
| `fill @e1 "text"` | Clear field then fill (for inputs) |
| `type @e1 "text"` | Type without clearing first |
| `select @e1 "value"` | Choose dropdown option |
| `check @e1` | Check checkbox |
| `uncheck @e1` | Uncheck checkbox |
| `hover @e1` | Hover over element |
| `focus @e1` | Set keyboard focus |
| `drag @e1 @e2` | Drag from @e1 to @e2 |
| `upload @e1 "file.pdf"` | Upload file to file input |
| `download @e1 ./file.pdf` | Click element and save download |

All commands accept either `@ref` identifiers or CSS selectors (e.g., `"#submit"`).

## Keyboard & Input

| Command | Description |
|---------|-------------|
| `press Enter` | Press a key (alias: `key`) |
| `press Control+a` | Key combination |
| `press Tab` | Tab key |
| `press Escape` | Escape key |
| `keyboard type "text"` | Type text at current focus |
| `keyboard inserttext "text"` | Insert without triggering key events |
| `keydown Shift` | Hold key down |
| `keyup Control` | Release key |

## Scrolling & Mouse

| Command | Description |
|---------|-------------|
| `scroll down [px]` | Scroll page (up/down/left/right) |
| `scroll --selector "#panel" down 300` | Scroll within a specific element |
| `scrollintoview @e2` | Scroll element into viewport (alias: `scrollinto`) |
| `mouse move <x> <y>` | Move cursor to coordinates |
| `mouse down [button]` | Press mouse button (left/right/middle) |
| `mouse up [button]` | Release mouse button |
| `mouse wheel <dy> [dx]` | Scroll wheel |

## Semantic Locators

Alternative to ref-based interaction -- find elements by semantic attributes:

| Command | Description |
|---------|-------------|
| `find text "Sign In" click` | By visible text |
| `find label "Email" fill "user@test.com"` | By form label |
| `find role button click --name "Submit"` | By ARIA role |
| `find placeholder "Search" type "query"` | By placeholder text |
| `find testid "submit-btn" click` | By data-testid attribute |
| `find alt "Profile picture" click` | By alt text |
| `find title "Close dialog" click` | By title attribute |
| `find first ".item" click` | First matching element |
| `find last ".item" click` | Last matching element |
| `find nth 2 "a" text` | Nth matching element |

## Information Retrieval

| Command | Description |
|---------|-------------|
| `get text @e1` | Element text content |
| `get text body > page.txt` | Save all page text to file |
| `get html @e1` | Inner HTML of element |
| `get value @e1` | Input/select current value |
| `get attr @e1 "href"` | Specific attribute value |
| `get title` | Page title |
| `get url` | Current URL |
| `get count ".item"` | Count matching elements |
| `get box @e1` | Bounding box (x, y, width, height) |
| `get styles @e1` | Computed CSS styles |

## Element State Checks

| Command | Description |
|---------|-------------|
| `is visible @e1` | Returns true/false for visibility |
| `is enabled @e1` | Returns true/false for enabled state |
| `is checked @e1` | Returns true/false for checkbox state |

## Screenshot & PDF

| Command | Description |
|---------|-------------|
| `screenshot` | Save to temp directory |
| `screenshot page.png` | Save to specific path |
| `screenshot --full` | Full page (not just viewport) |
| `screenshot --annotate` | Numbered labels on interactive elements; caches refs |
| `screenshot --screenshot-format jpeg` | PNG (default) or JPEG |
| `screenshot --screenshot-quality 80` | JPEG quality 0-100 |
| `pdf output.pdf` | Save page as PDF |

## Wait & Synchronization

| Command | Description |
|---------|-------------|
| `wait @e1` | Wait for element to be visible |
| `wait "#selector"` | Wait for CSS selector match |
| `wait 3000` | Wait N milliseconds |
| `wait --text "Welcome"` | Wait for text substring to appear |
| `wait --url "**/dashboard"` | Wait for URL pattern |
| `wait --load networkidle` | Wait for network idle |
| `wait --load domcontentloaded` | Wait for DOM ready |
| `wait --fn "window.ready"` | Wait for JS condition to be truthy |
| `wait "#spinner" --state hidden` | Wait for element to become hidden |
| `wait --download ./output.zip` | Wait for file download |

## JavaScript Execution

```bash
agent-browser eval 'document.title'                         # Simple expression
agent-browser eval -b "$(echo -n 'code' | base64)"         # Base64 encoded
agent-browser eval --stdin <<'EVALEOF'                       # Multiline heredoc
JSON.stringify(Array.from(document.querySelectorAll("img")).map(i => i.src))
EVALEOF
```

## Network Commands

| Command | Description |
|---------|-------------|
| `network requests` | All tracked requests |
| `network requests --type xhr,fetch` | Filter by type |
| `network requests --method POST` | Filter by method |
| `network requests --status 2xx` | Filter by status code |
| `network request <requestId>` | Full request/response details |
| `network route "**/api/*" --abort` | Block matching requests |
| `network route <url> --body <json>` | Mock a response |
| `network unroute [url]` | Remove route rules |
| `network har start` | Start HAR recording |
| `network har stop ./capture.har` | Stop and save HAR file |

## Session Management

| Command | Description |
|---------|-------------|
| `--session <name> <cmd>` | Run command in isolated session |
| `--session-name <name> <cmd>` | Auto-save/restore named session |
| `session list` | List active sessions |
| `--auto-connect <cmd>` | Discover and attach to running Chrome |
| `--cdp <port> <cmd>` | Connect via explicit CDP port |
| `connect <port>` | Connect to running Chrome via CDP |

## State Persistence

| Command | Description |
|---------|-------------|
| `state save ./auth.json` | Save cookies + localStorage |
| `state load ./auth.json` | Restore saved state |
| `state list` | List saved states |
| `state show <file>` | Inspect state contents |
| `state clear [name]` | Delete a session state |
| `state clear --all` | Delete all states |

State files stored in `~/.agent-browser/sessions/`.

## Authentication

| Command | Description |
|---------|-------------|
| `auth save <name> --url <url> --username <user> --password-stdin` | Save credentials to encrypted vault |
| `auth login <name>` | Navigate to URL and auto-fill login form |
| `auth list` | List saved auth profiles |
| `auth show <name>` | Show auth profile details |
| `auth delete <name>` | Delete auth profile |

## Cookies & Storage

| Command | Description |
|---------|-------------|
| `cookies` | Get all cookies |
| `cookies set <name> <value>` | Set a cookie |
| `cookies clear` | Clear all cookies |
| `storage local` | Get all localStorage entries |
| `storage local <key>` | Get a specific localStorage value |
| `storage local set <k> <v>` | Set localStorage value |
| `storage local clear` | Clear localStorage |
| `storage session` | Same operations for sessionStorage |

## Tab & Window Management

| Command | Description |
|---------|-------------|
| `tab` | List open tabs |
| `tab new [url]` | Open new tab |
| `tab <n>` | Switch to tab N |
| `tab close [n]` | Close tab N |
| `window new` | Open new window |

## Frame Management

| Command | Description |
|---------|-------------|
| `frame @e2` | Switch to iframe by ref |
| `frame "#content-frame"` | Switch to iframe by selector |
| `frame main` | Return to main frame |

Note: Iframe content is auto-inlined in snapshots. Refs inside iframes carry frame context, so direct interaction works without manual frame switching.

## Dialog Handling

| Command | Description |
|---------|-------------|
| `dialog status` | Check if a dialog is open |
| `dialog accept` | Accept (OK) |
| `dialog accept "input"` | Accept prompt dialog with text |
| `dialog dismiss` | Dismiss (Cancel) |

Auto-accept is enabled by default. Disable with `--no-auto-dialog`.

## Viewport & Device Emulation

| Command | Description |
|---------|-------------|
| `set viewport <w> <h> [scale]` | Set viewport size (default 1280x720) |
| `set device "iPhone 14"` | Full device emulation |
| `set geo <lat> <lon>` | Set geolocation |
| `set offline on\|off` | Toggle offline mode |
| `set headers '{"Auth": "Bearer x"}'` | Set extra HTTP headers |
| `set credentials <user> <pass>` | HTTP basic auth |
| `set media dark\|light` | Emulate color scheme |

## Diff & Visual Regression

| Command | Description |
|---------|-------------|
| `diff snapshot` | Compare current vs last snapshot |
| `diff snapshot --baseline before.txt` | Compare vs saved baseline |
| `diff screenshot --baseline before.png` | Visual pixel diff (red highlights, mismatch %) |
| `diff screenshot --baseline b.png -o d.png` | Save diff image |
| `diff screenshot --baseline b.png -t 0.2` | Set threshold |
| `diff url <url1> <url2>` | Compare two pages |
| `diff url <url1> <url2> --screenshot` | Screenshot comparison of two pages |

## Recording & Debugging

| Command | Description |
|---------|-------------|
| `record start demo.webm` | Start video recording |
| `record stop` | Stop recording |
| `console` | View browser console logs |
| `console --json` | Structured console output |
| `errors` | View JavaScript errors |
| `highlight @e1` | Visually highlight element |
| `inspect` | Open Chrome DevTools |

## Batch Execution

```bash
# JSON array of commands
echo '[["open","https://example.com"],["snapshot","-i"],["click","@e1"]]' | agent-browser batch --json

# Stop on first error
agent-browser batch --bail < commands.json
```

## Configuration

### Config File (`agent-browser.json` or `~/.agent-browser/config.json`)

All CLI flags map to camelCase keys. Example:
```json
{
  "headed": true,
  "proxy": "http://localhost:8080",
  "profile": "./browser-data"
}
```

### Key Environment Variables

| Variable | Description |
|----------|-------------|
| `AGENT_BROWSER_HEADED` | Show browser window (`1`/`true`) |
| `AGENT_BROWSER_SESSION` | Default session name |
| `AGENT_BROWSER_EXECUTABLE_PATH` | Custom browser binary path |
| `AGENT_BROWSER_DEFAULT_TIMEOUT` | Timeout in ms (default: 25000) |
| `AGENT_BROWSER_SCREENSHOT_DIR` | Screenshot output directory |
| `AGENT_BROWSER_ALLOWED_DOMAINS` | Domain allowlist (comma-separated) |
| `AGENT_BROWSER_ACTION_POLICY` | Path to action policy JSON |
| `AGENT_BROWSER_PROXY` | Proxy URL |

### Action Policy File

Restrict allowed commands:
```json
{ "default": "deny", "allow": ["navigate", "snapshot", "click", "scroll", "wait", "get"] }
```
