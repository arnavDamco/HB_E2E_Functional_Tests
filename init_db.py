#!/usr/bin/env python3
"""Initialize the Hudson Bailey E2E test database."""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # --- Modules ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
    """)

    # --- Inter-Module Workflows ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS inter_module_workflows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
    """)

    # --- Workflow <-> Module junction ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS workflow_modules (
            workflow_id INTEGER NOT NULL REFERENCES inter_module_workflows(id),
            module_id INTEGER NOT NULL REFERENCES modules(id),
            PRIMARY KEY (workflow_id, module_id)
        )
    """)

    # --- Tests ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            test_type TEXT NOT NULL CHECK (test_type IN ('smoke', 'critical', 'regression')),
            scope TEXT NOT NULL CHECK (scope IN ('module', 'inter_module')),
            steps TEXT NOT NULL,
            expected_result TEXT,
            target_url TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
    """)

    # --- Test <-> Module junction ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS test_modules (
            test_id INTEGER NOT NULL REFERENCES tests(id),
            module_id INTEGER NOT NULL REFERENCES modules(id),
            PRIMARY KEY (test_id, module_id)
        )
    """)

    # --- Runs (batch grouping) ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            run_type TEXT CHECK (run_type IN ('smoke', 'critical', 'regression', 'custom')),
            device_os TEXT,
            browser TEXT,
            triggered_by TEXT,
            status TEXT DEFAULT 'running' CHECK (status IN ('running', 'completed', 'aborted')),
            started_at TEXT NOT NULL,
            completed_at TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
    """)

    # --- Test Runs (individual test within a run) ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS test_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES runs(id),
            test_id INTEGER NOT NULL REFERENCES tests(id),
            status TEXT NOT NULL CHECK (status IN ('pass', 'fail', 'error', 'skipped')),
            output TEXT,
            remarks TEXT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
    """)

    # --- Bugs ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bugs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            severity TEXT CHECK (severity IN ('critical', 'high', 'medium', 'low')),
            status TEXT DEFAULT 'open' CHECK (status IN ('open', 'investigating', 'fixed', 'wont_fix', 'duplicate')),
            module_id INTEGER REFERENCES modules(id),
            first_seen_at TEXT NOT NULL,
            resolved_at TEXT,
            created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
    """)

    # --- Bug <-> Test Run junction (many-to-many: a bug can appear in multiple test runs) ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bug_test_runs (
            bug_id INTEGER NOT NULL REFERENCES bugs(id),
            test_run_id INTEGER NOT NULL REFERENCES test_runs(id),
            notes TEXT,
            created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            PRIMARY KEY (bug_id, test_run_id)
        )
    """)

    # --- Indexes for common queries ---
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tests_type ON tests(test_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tests_scope ON tests(scope)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tests_active ON tests(is_active)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_runs_type ON runs(run_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_test_runs_run_id ON test_runs(run_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_test_runs_test_id ON test_runs(test_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_test_runs_status ON test_runs(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bugs_status ON bugs(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bugs_module ON bugs(module_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bug_test_runs_bug ON bug_test_runs(bug_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bug_test_runs_test_run ON bug_test_runs(test_run_id)")

    # --- Seed modules (insurance-domain) ---
    modules = [
        ("quotes_policies", "Quotes & Policies", "New submissions, endorsements, renewals, policy summary, finalization"),
        ("claims", "Claims Management", "FNOL, claim workflows, claims financials, adjuster management, payee management"),
        ("distribution", "Distribution Management", "Intermediary management, producer setup, product assignment"),
        ("client_management", "Client Management", "Client information, contacts, client configuration"),
        ("insurance_products", "Insurance Product Management", "Product templates, available products catalog"),
        ("account_management", "Account Management", "Account onboarding, account contacts, account details"),
        ("admin_platform", "Admin & Platform", "Organization onboarding, dynamic forms, header & navigation, bulk upload"),
        ("user_management", "User Management", "User profiles, roles, user groups, global permissions"),
        ("reporting", "Report Management", "Bordereaux, reports, analytics, data exports"),
        ("producer_dashboard", "Producer Dashboard", "KPIs, renewal radar, pending cancellation"),
        ("billing", "Billing Management", "Payments, invoices, billing workflows"),
        ("document_management", "Document Management", "Document lists, packages, declaration pages, quote proposals"),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO modules (key, name, description) VALUES (?, ?, ?)",
        modules,
    )

    # --- Seed inter-module workflows (insurance-domain) ---
    workflows = [
        ("new_submission_to_policy", "New Submission to Policy", "Quote created, finalized, policy issued, documents generated"),
        ("fnol_to_claim_resolution", "FNOL to Claim Resolution", "First notice of loss through claim review and financial settlement"),
        ("client_onboard_to_quote", "Client Onboard to Quote", "New client created, account set up, first quote submitted"),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO inter_module_workflows (key, name, description) VALUES (?, ?, ?)",
        workflows,
    )

    # --- Link workflows to modules ---
    workflow_module_links = {
        "new_submission_to_policy": ["quotes_policies", "billing", "document_management"],
        "fnol_to_claim_resolution": ["claims", "document_management", "billing"],
        "client_onboard_to_quote": ["account_management", "client_management", "quotes_policies"],
    }

    for wf_key, mod_keys in workflow_module_links.items():
        cur.execute("SELECT id FROM inter_module_workflows WHERE key = ?", (wf_key,))
        wf_row = cur.fetchone()
        if not wf_row:
            continue
        wf_id = wf_row[0]
        for mk in mod_keys:
            cur.execute("SELECT id FROM modules WHERE key = ?", (mk,))
            mod_row = cur.fetchone()
            if mod_row:
                cur.execute(
                    "INSERT OR IGNORE INTO workflow_modules (workflow_id, module_id) VALUES (?, ?)",
                    (wf_id, mod_row[0]),
                )

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")


if __name__ == "__main__":
    init_db()
