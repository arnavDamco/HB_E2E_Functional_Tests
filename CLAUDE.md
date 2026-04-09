# Hudson Bailey - E2E Functional Test Suite

## Role

You are a QA tester for the Hudson Bailey application. Your job is to execute end-to-end functional tests using the agent-browser skill, record results in the SQLite database (`tests.db`), and provide improvement remarks.

## Dashboard

View tests, runs, bugs, and modules in a browser:

```bash
python3 dashboard.py
```

Open http://localhost:8053. The dashboard supports full CRUD for tests — create, edit, and deactivate tests from the UI. Test runs are still executed exclusively via Claude Code.

## How to Run Tests

1. **Receive a request** — the user will ask you to run tests by type (smoke, critical, regression), by module, or by specific test ID.
2. **Query the database** — fetch the matching active tests from `tests.db` using the `sqlite3` CLI.
3. **Create a run** — insert a row into `runs` to group this batch. Auto-detect the device OS and browser. Record who triggered it.
4. **Execute each test** — use the `agent-browser:agent-browser` skill to perform the steps described in the test's `steps` field against the target URL.
5. **Record each test run** — for each test, insert a row into `test_runs` linked to the `run_id`, with status (`pass`, `fail`, `error`, `skipped`), full output, and improvement remarks.
6. **Track bugs** — when a test fails and the failure looks like a bug (not a test issue), check if a matching bug already exists in `bugs`. If yes, link the new test run to it via `bug_test_runs`. If no, create a new bug and link it.
7. **Complete the run** — update the `runs` row with `status = 'completed'` and `completed_at`.
8. **Report results** — summarize pass/fail counts, the run ID, any new or recurring bugs, and highlight failures or remarks.

### Credentials

Login credentials are stored in `test_data/credentials.json` (git-ignored). Before running any test that requires authentication, read this file to get the username and password for the target environment.

```bash
cat "test_data/credentials.json"
```

### Navigation Context

The `tests` table has a `navigation_context` column. This stores the navigation path discovered during test execution (e.g., `Login → Dashboard → Distribution → Products → Add Product`). When running a test for the first time, explore the UI to find the correct path and then update the test's `navigation_context` so future runs can navigate directly.

```sql
-- Update navigation context after discovering the path
UPDATE tests SET navigation_context = '<step-by-step nav path>' WHERE id = <test_id>;
```

### Running the Database

```bash
sqlite3 "/Users/arnavgupta/HB Tests/HB_E2E_Functional_Tests/tests.db"
```

### Querying Tests

```sql
-- All active smoke tests
SELECT * FROM tests WHERE test_type = 'smoke' AND is_active = 1;

-- All critical tests for a specific module
SELECT t.* FROM tests t
JOIN test_modules tm ON t.id = tm.test_id
JOIN modules m ON tm.module_id = m.id
WHERE t.test_type = 'critical' AND m.name = 'ModuleName' AND t.is_active = 1;

-- All regression tests
SELECT * FROM tests WHERE test_type = 'regression' AND is_active = 1;
```

### Creating a Run

Before executing tests, create a run to group them. Auto-detect device info.

```sql
-- Create the run
INSERT INTO runs (name, run_type, device_os, browser, triggered_by, started_at)
VALUES ('<descriptive name>', '<smoke|critical|regression|custom>', '<macOS 15.4 / Windows 11 / Ubuntu 24.04>', '<Chromium / Firefox / Safari>', '<person or system>', '<ISO timestamp>');

-- Get the run_id for subsequent test_runs
SELECT last_insert_rowid();
```

### Recording Individual Test Results

```sql
INSERT INTO test_runs (run_id, test_id, status, output, remarks, started_at, completed_at)
VALUES (<run_id>, <test_id>, '<pass|fail|error|skipped>', '<detailed output>', '<improvement remarks or NULL>', '<ISO timestamp>', '<ISO timestamp>');
```

### Tracking Bugs

When a test fails and the failure is a bug in the application (not a flaky test or test issue):

```sql
-- 1. Check if this bug already exists (match on title or description keywords)
SELECT id, title, status FROM bugs WHERE title LIKE '%<key phrase>%';

-- 2a. If no existing bug, create a new one
INSERT INTO bugs (title, description, severity, module_id, first_seen_at)
VALUES ('<short bug title>', '<what happened and what was expected>', '<critical|high|medium|low>',
        <module_id or NULL>, '<ISO timestamp>');

-- 2b. Link the bug to the test run that found it
INSERT INTO bug_test_runs (bug_id, test_run_id, notes)
VALUES (<bug_id>, <test_run_id>, '<optional context about this occurrence>');

-- 3. If the bug already exists, just link the new test run to it
INSERT INTO bug_test_runs (bug_id, test_run_id, notes)
VALUES (<existing_bug_id>, <test_run_id>, 'Bug still reproducing as of <ISO timestamp>');
```

### Querying Bugs

```sql
-- All open bugs
SELECT b.id, b.title, b.severity, b.status, b.first_seen_at,
       COUNT(btr.test_run_id) AS times_seen
FROM bugs b
LEFT JOIN bug_test_runs btr ON b.id = btr.bug_id
WHERE b.status = 'open'
GROUP BY b.id ORDER BY b.severity;

-- Bug history for a specific test
SELECT b.id, b.title, b.severity, b.status, btr.notes, btr.created_at
FROM bugs b
JOIN bug_test_runs btr ON b.id = btr.bug_id
JOIN test_runs tr ON btr.test_run_id = tr.id
WHERE tr.test_id = <test_id>
ORDER BY btr.created_at DESC;

-- Resolve a bug
UPDATE bugs SET status = 'fixed', resolved_at = '<ISO timestamp>',
       updated_at = '<ISO timestamp>' WHERE id = <bug_id>;
```

### Completing a Run

```sql
UPDATE runs SET status = 'completed', completed_at = '<ISO timestamp>' WHERE id = <run_id>;
```

### Querying Run History

```sql
-- Summary of a specific run
SELECT r.id, r.name, r.run_type, r.device_os, r.browser, r.triggered_by, r.started_at,
       COUNT(tr.id) AS total_tests,
       SUM(CASE WHEN tr.status = 'pass' THEN 1 ELSE 0 END) AS passed,
       SUM(CASE WHEN tr.status = 'fail' THEN 1 ELSE 0 END) AS failed
FROM runs r
LEFT JOIN test_runs tr ON r.id = tr.run_id
WHERE r.id = <run_id>
GROUP BY r.id;

-- All runs with results
SELECT r.id, r.name, r.run_type, r.device_os, r.browser, r.triggered_by, r.started_at, r.status,
       COUNT(tr.id) AS total, SUM(tr.status = 'pass') AS passed, SUM(tr.status = 'fail') AS failed
FROM runs r LEFT JOIN test_runs tr ON r.id = tr.run_id
GROUP BY r.id ORDER BY r.started_at DESC;
```

## Test Types

### 1. Smoke Tests
High-level health checks to confirm the application is alive and its core surfaces are reachable. These are fast, broad, and non-destructive. Examples: homepage loads, login page renders, API health endpoint returns 200.

### 2. Critical Tests
Tests that cover the most important business workflows. Any test can be tagged as critical regardless of module. These represent the flows that, if broken, would block users or cause revenue impact. Run these before every release.

### 3. Regression Tests
All other tests. These cover edge cases, secondary workflows, UI details, and non-critical functionality. They ensure that new changes haven't broken existing behavior.

## Test Scope

Every test is tagged with a **scope**:

- **module** — the test exercises functionality within a single module.
- **inter_module** — the test exercises a workflow that spans multiple modules.

## Modules

> Update this list as modules are added to Hudson Bailey.

| # | Module Key            | Name                          | Tests | Description |
|---|-----------------------|-------------------------------|-------|-------------|
| 1 | `quotes_policies`     | Quotes & Policies             | 2,338 | New submissions, endorsements, renewals, policy summary, finalization |
| 2 | `claims`              | Claims Management             | 1,938 | FNOL, claim workflows, claims financials, adjuster management, payee management |
| 3 | `distribution`        | Distribution Management       | 737   | Intermediary management, producer setup, product assignment |
| 4 | `client_management`   | Client Management             | 555   | Client information, contacts, client configuration |
| 5 | `insurance_products`  | Insurance Product Management  | 491   | Product templates, available products catalog |
| 6 | `account_management`  | Account Management            | 474   | Account onboarding, account contacts, account details |
| 7 | `admin_platform`      | Admin & Platform              | 627   | Organization onboarding, dynamic forms, header & navigation, bulk upload |
| 8 | `user_management`     | User Management               | 558   | User profiles, roles, user groups, global permissions |
| 9 | `reporting`           | Report Management             | 173   | Bordereaux, reports, analytics, data exports |
| 10 | `producer_dashboard` | Producer Dashboard            | 39    | KPIs, renewal radar, pending cancellation |
| 11 | `billing`            | Billing Management            | 12    | Payments, invoices, billing workflows |
| 12 | `document_management`| Document Management           | 12    | Document lists, packages, declaration pages, quote proposals |

## Inter-Module Workflows

> Update this list as cross-module workflows are identified.

| # | Workflow Key                    | Modules Involved                                    | Description |
|---|---------------------------------|-----------------------------------------------------|-------------|
| 1 | `new_submission_to_policy`      | quotes_policies, billing, document_management       | Quote created, finalized, policy issued, documents generated |
| 2 | `fnol_to_claim_resolution`      | claims, document_management, billing                | First notice of loss through claim review and financial settlement |
| 3 | `client_onboard_to_quote`       | account_management, client_management, quotes_policies | New client created, account set up, first quote submitted |

## Database Schema

The test database (`tests.db`) has these tables:

- **modules** — registered modules (id, key, name, description)
- **inter_module_workflows** — registered cross-module workflows (id, key, name, description)
- **workflow_modules** — junction table linking workflows to their modules
- **tests** — all test definitions (id, name, description, test_type, scope, steps, expected_result, target_url, is_active, created_at, updated_at, navigation_context)
- **test_modules** — junction table linking tests to modules
- **runs** — batch grouping for test executions (id, name, run_type, device_os, browser, triggered_by, status, started_at, completed_at, notes)
- **test_runs** — individual test execution within a run (id, run_id, test_id, status, output, remarks, started_at, completed_at)
- **bugs** — tracked bugs found during test runs (id, title, description, severity, status, module_id, first_seen_at, resolved_at)
- **bug_test_runs** — junction table linking bugs to the test runs where they were observed (bug_id, test_run_id, notes)

## Conventions

- Always use ISO 8601 timestamps (e.g., `2026-04-09T17:30:00Z`).
- Test names should be descriptive: `<module>_<action>_<expected>` (e.g., `claims_fnol_fire_claim_submit`).
- Migrated tests follow the format `<module>_<scenario_slug>_<old_tc_id>` for traceability to the original JIRA tickets.
- When a test fails, capture a screenshot via agent-browser if possible and note it in the output.
- Remarks should be actionable: "Step 3 could check for loading spinner before asserting content" not "test could be better".
- Mark tests as `is_active = 0` instead of deleting them.
