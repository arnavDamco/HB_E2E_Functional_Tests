# Agent Browser Workflow Patterns

## Table of Contents
- [Core Interaction Loop](#core-interaction-loop)
- [Login & Authentication](#login--authentication)
- [Form Fill & Submit](#form-fill--submit)
- [Navigation & Verification](#navigation--verification)
- [Data Extraction & Assertion](#data-extraction--assertion)
- [Dropdown & Multi-Select](#dropdown--multi-select)
- [Table Interaction](#table-interaction)
- [Search & Filter](#search--filter)
- [Modal & Dialog](#modal--dialog)
- [Multi-Tab Workflow](#multi-tab-workflow)
- [Error Handling Patterns](#error-handling-patterns)
- [Test Case Execution Pattern](#test-case-execution-pattern)

---

## Core Interaction Loop

Every interaction follows this cycle:

```
1. Navigate:    agent-browser open <url>
2. Discover:    agent-browser snapshot -i       # Get interactive element refs
3. Act:         agent-browser click @e3         # Interact using refs
4. Re-discover: agent-browser snapshot -i       # Refs invalidated, get fresh ones
5. Verify:      agent-browser get text @e1      # Check results
```

**Critical rule:** Always re-snapshot after any action that changes the DOM (click, fill, submit, navigation). Refs from a previous snapshot are stale.

---

## Login & Authentication

### First-time login (discovery + state save)

```bash
# Navigate to login page
agent-browser open <login-url>

# Discover form elements
agent-browser snapshot -i
# Output shows: @e1 [input] placeholder="Username", @e2 [input type="password"], @e3 [button] "Login"

# Fill and submit
agent-browser fill @e1 "username"
agent-browser fill @e2 "password"
agent-browser click @e3

# Wait for dashboard to load
agent-browser wait --load networkidle
agent-browser wait --text "Dashboard"

# Save authenticated state for reuse
agent-browser state save ./auth-state.json
```

### Subsequent runs (state restore)

```bash
agent-browser state load ./auth-state.json
agent-browser open <dashboard-url>
agent-browser wait --load networkidle
```

### Using auth vault (recommended for repeated use)

```bash
# Save once
echo "$PASSWORD" | agent-browser auth save myapp \
  --url <login-url> \
  --username testuser --password-stdin

# Login anytime
agent-browser auth login myapp
agent-browser wait --load networkidle
```

---

## Form Fill & Submit

### Standard form

```bash
agent-browser snapshot -i
# Identify fields from snapshot output

agent-browser fill @e1 "John Doe"           # Text input
agent-browser fill @e2 "john@example.com"   # Email input
agent-browser select @e3 "California"       # Dropdown
agent-browser check @e4                     # Checkbox
agent-browser click @e5                     # Radio button
agent-browser fill @e6 "2025-01-15"         # Date input
agent-browser click @e7                     # Submit button

agent-browser wait --load networkidle
agent-browser snapshot -i                   # Verify result
```

### Date picker (custom widget)

```bash
# Try direct fill first
agent-browser fill @e6 "01/15/2025"

# If custom date picker, click to open and navigate
agent-browser click @e6                     # Open date picker
agent-browser snapshot -i                   # See calendar elements
agent-browser click @e10                    # Select date
```

### Rich text editor

```bash
agent-browser click @e5                     # Focus the editor
agent-browser keyboard type "Description text here"
```

---

## Navigation & Verification

### Navigate via menu

```bash
agent-browser snapshot -i
# @e3 [link] "Claims" -- top nav menu item
agent-browser click @e3
agent-browser wait --load networkidle
agent-browser snapshot -i
# @e7 [link] "Claims Dashboard" -- submenu
agent-browser click @e7
agent-browser wait --load networkidle
```

### Verify page loaded correctly

```bash
# Check URL
agent-browser get url
# Expected: contains "/ClaimsDashboard"

# Check page title
agent-browser get title

# Check for expected text
agent-browser wait --text "Claims Dashboard"

# Check specific element exists
agent-browser snapshot -i
# Verify expected elements are present in output
```

### Breadcrumb verification

```bash
agent-browser snapshot -s ".breadcrumb"     # Scope snapshot to breadcrumb
```

---

## Data Extraction & Assertion

### Read element text and compare

```bash
agent-browser get text @e5
# Output: "Premium: $1,250.00"
# Compare against expected value from test case
```

### Read input value

```bash
agent-browser get value @e3
# Output: "California"
```

### Check element state

```bash
agent-browser is visible @e5    # true/false
agent-browser is enabled @e3    # true/false (for disabled fields)
agent-browser is checked @e4    # true/false (for checkboxes)
```

### Count elements

```bash
agent-browser get count ".claim-row"
# Output: "15" -- verify expected count
```

### Extract table data

```bash
agent-browser snapshot -s "table"
# Returns table structure with refs for each cell

# Or extract full text
agent-browser get text "table" > table-data.txt
```

---

## Dropdown & Multi-Select

### Standard select dropdown

```bash
agent-browser select @e3 "Option Value"
```

### Custom dropdown (non-native)

```bash
agent-browser click @e3                     # Open dropdown
agent-browser snapshot -i                   # See options
agent-browser click @e8                     # Click desired option
agent-browser snapshot -i                   # Verify selection
```

### Searchable dropdown / typeahead

```bash
agent-browser click @e3                     # Focus/open
agent-browser type @e3 "Search term"        # Type to filter
agent-browser wait 1000                     # Wait for filter
agent-browser snapshot -i                   # See filtered results
agent-browser click @e10                    # Select from results
```

---

## Table Interaction

### Read table rows

```bash
agent-browser snapshot -s "table"
# Inspect output for row/cell refs

agent-browser get text @e15                 # Specific cell
```

### Click action in table row

```bash
agent-browser snapshot -i
# @e20 [link] "View" inside a row
agent-browser click @e20
agent-browser wait --load networkidle
```

### Pagination

```bash
agent-browser snapshot -i
# @e30 [button] "Next" or @e31 [link] "2"
agent-browser click @e30
agent-browser wait --load networkidle
agent-browser snapshot -i                   # New page of results
```

### Sort column

```bash
agent-browser find text "Column Header" click
agent-browser wait --load networkidle
agent-browser snapshot -i                   # Verify sort order
```

---

## Search & Filter

```bash
agent-browser snapshot -i
agent-browser fill @e1 "search query"       # Search input
agent-browser click @e2                     # Search button (or press Enter)
# OR
agent-browser press Enter

agent-browser wait --load networkidle
agent-browser snapshot -i                   # Verify results
```

---

## Modal & Dialog

```bash
# Trigger modal
agent-browser click @e5
agent-browser wait ".modal"                 # Wait for modal to appear
agent-browser snapshot -i                   # Get modal elements

# Interact inside modal
agent-browser fill @e10 "data"
agent-browser click @e12                    # Confirm/Save

# Wait for modal to close
agent-browser wait ".modal" --state hidden
agent-browser snapshot -i                   # Back to main page
```

---

## Multi-Tab Workflow

```bash
# Open in new tab
agent-browser click @e5 --new-tab
agent-browser tab 1                         # Switch to new tab
agent-browser snapshot -i                   # Interact in new tab

# Switch back
agent-browser tab 0
```

---

## Error Handling Patterns

### Wait for loading to complete before acting

```bash
agent-browser wait --load networkidle
# OR wait for specific indicator
agent-browser wait "#loading-spinner" --state hidden
```

### Retry on stale ref

If a command fails with "element not found", re-snapshot and retry:
```bash
agent-browser snapshot -i                   # Get fresh refs
agent-browser click @e3                     # Retry with new ref
```

### Handle page transitions

```bash
agent-browser click @e5                     # Triggers navigation
agent-browser wait --url "**/next-page"     # Wait for URL change
agent-browser wait --load networkidle       # Wait for page load
agent-browser snapshot -i                   # Fresh snapshot on new page
```

---

## Test Case Execution Pattern

Standard flow for executing a test case from the database:

```
1. Read the test case row (Steps, Expected Result, Target URL)
2. Ensure pre-conditions are met (login, navigate to correct module)
3. For each step:
   a. Translate the human-readable step to agent-browser commands
   b. Execute the command(s)
   c. Re-snapshot after each action
   d. Capture evidence (screenshot or text extraction)
4. After final step, verify Expected Result
5. Record Pass/Fail with evidence
```

### Example: Translating test steps to commands

| Test Step | Agent Browser Commands |
|-----------|----------------------|
| "Navigate to Claims Dashboard" | `open <url>` then `wait --load networkidle` |
| "Click on 'New Claim' button" | `snapshot -i` then `find text "New Claim" click` |
| "Enter Policy Number 'POL-001'" | `snapshot -i` then find policy number field, `fill @eN "POL-001"` |
| "Select 'Fire' from Loss Type dropdown" | `select @eN "Fire"` or click custom dropdown |
| "Verify claim status shows 'Open'" | `get text @eN` and compare to "Open" |
| "Verify 'Submit' button is disabled" | `is enabled @eN` should return false |
| "Verify success message appears" | `wait --text "successfully"` |
