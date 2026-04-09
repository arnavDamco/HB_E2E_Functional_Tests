#!/usr/bin/env python3
"""HB QA Test Dashboard — lightweight single-file dashboard.

Run:  python3 dashboard.py
Open: http://localhost:8053
"""

import http.server
import json
import sqlite3
import os
import sys
import urllib.parse
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests.db")
PORT = 8053


# ─── Database helpers ───────────────────────────────────────────────────────────

def query_db(sql, params=(), one=False):
    """Run a read query and return list of dicts (or single dict if one=True)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute_db(sql, params=()):
    """Run a write query and return the lastrowid."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    lastid = cur.lastrowid
    conn.close()
    return lastid


def execute_db_many(statements):
    """Run multiple write statements in a single transaction.
    statements is a list of (sql, params) tuples.
    Returns the lastrowid of the final statement.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    lastid = None
    for sql, params in statements:
        cur.execute(sql, params)
        lastid = cur.lastrowid
    conn.commit()
    conn.close()
    return lastid


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─── API handlers ──────────────────────────────────────────────────────────────

def api_summary():
    test_counts = query_db(
        "SELECT COUNT(*) as total, SUM(CASE WHEN is_active=1 THEN 1 ELSE 0 END) as active FROM tests",
        one=True
    )
    by_type = query_db(
        "SELECT test_type, COUNT(*) as count FROM tests WHERE is_active=1 GROUP BY test_type"
    )
    last_run = query_db(
        """SELECT r.*, COUNT(tr.id) as total,
           SUM(CASE WHEN tr.status='pass' THEN 1 ELSE 0 END) as passed,
           SUM(CASE WHEN tr.status='fail' THEN 1 ELSE 0 END) as failed
           FROM runs r LEFT JOIN test_runs tr ON r.id = tr.run_id
           WHERE r.status='completed'
           GROUP BY r.id ORDER BY r.completed_at DESC LIMIT 1""",
        one=True
    )
    open_bugs = query_db(
        "SELECT severity, COUNT(*) as count FROM bugs WHERE status IN ('open','investigating') GROUP BY severity"
    )
    open_bugs_total = sum(b["count"] for b in open_bugs)
    by_module = query_db(
        """SELECT m.id, m.key, m.name, COUNT(tm.test_id) as test_count
           FROM modules m LEFT JOIN test_modules tm ON m.id = tm.module_id
           LEFT JOIN tests t ON tm.test_id = t.id AND t.is_active = 1
           GROUP BY m.id ORDER BY m.id"""
    )
    recent_runs = query_db(
        """SELECT r.id, r.name, r.run_type, r.status, r.started_at, r.completed_at,
           COUNT(tr.id) as total,
           SUM(CASE WHEN tr.status='pass' THEN 1 ELSE 0 END) as passed,
           SUM(CASE WHEN tr.status='fail' THEN 1 ELSE 0 END) as failed,
           SUM(CASE WHEN tr.status='error' THEN 1 ELSE 0 END) as errored,
           SUM(CASE WHEN tr.status='skipped' THEN 1 ELSE 0 END) as skipped
           FROM runs r LEFT JOIN test_runs tr ON r.id = tr.run_id
           GROUP BY r.id ORDER BY r.started_at DESC LIMIT 5"""
    )
    open_bugs_list = query_db(
        """SELECT b.id, b.title, b.severity, b.status, m.name as module_name
           FROM bugs b LEFT JOIN modules m ON b.module_id = m.id
           WHERE b.status IN ('open','investigating')
           ORDER BY CASE b.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
           WHEN 'medium' THEN 2 ELSE 3 END LIMIT 10"""
    )
    pass_rate = None
    if last_run and last_run["total"] and last_run["total"] > 0:
        pass_rate = round(last_run["passed"] / last_run["total"] * 100, 1)

    return {
        "total_tests": test_counts["total"] or 0,
        "active_tests": test_counts["active"] or 0,
        "tests_by_type": {r["test_type"]: r["count"] for r in by_type},
        "last_run": last_run,
        "pass_rate": pass_rate,
        "open_bugs_total": open_bugs_total,
        "open_bugs_by_severity": {r["severity"]: r["count"] for r in open_bugs},
        "open_bugs_list": open_bugs_list,
        "by_module": by_module,
        "recent_runs": recent_runs,
    }


def api_tests(params):
    conditions = ["1=1"]
    sql_params = []
    if "type" in params:
        conditions.append("t.test_type = ?")
        sql_params.append(params["type"][0])
    if "scope" in params:
        conditions.append("t.scope = ?")
        sql_params.append(params["scope"][0])
    if "active" in params:
        conditions.append("t.is_active = ?")
        sql_params.append(int(params["active"][0]))
    if "search" in params:
        conditions.append("(t.name LIKE ? OR t.description LIKE ?)")
        term = f"%{params['search'][0]}%"
        sql_params.extend([term, term])

    where = " AND ".join(conditions)
    tests = query_db(
        f"""SELECT t.id, t.name, t.description, t.test_type, t.scope,
            t.steps, t.expected_result, t.target_url, t.is_active,
            t.created_at, t.updated_at
            FROM tests t WHERE {where}
            ORDER BY t.id""",
        sql_params
    )

    # Attach modules and last 5 results per test
    for test in tests:
        test["modules"] = query_db(
            """SELECT m.id, m.key, m.name FROM modules m
               JOIN test_modules tm ON m.id = tm.module_id
               WHERE tm.test_id = ?""",
            (test["id"],)
        )
        test["last_results"] = query_db(
            """SELECT tr.id, tr.run_id, tr.status, tr.completed_at
               FROM test_runs tr WHERE tr.test_id = ?
               ORDER BY tr.completed_at DESC LIMIT 5""",
            (test["id"],)
        )
    return tests


def api_test_detail(test_id):
    test = query_db("SELECT * FROM tests WHERE id = ?", (test_id,), one=True)
    if not test:
        return None
    test["modules"] = query_db(
        """SELECT m.id, m.key, m.name FROM modules m
           JOIN test_modules tm ON m.id = tm.module_id WHERE tm.test_id = ?""",
        (test_id,)
    )
    test["last_results"] = query_db(
        """SELECT tr.id, tr.run_id, tr.status, tr.output, tr.remarks,
           tr.started_at, tr.completed_at, r.name as run_name
           FROM test_runs tr JOIN runs r ON tr.run_id = r.id
           WHERE tr.test_id = ?
           ORDER BY tr.completed_at DESC LIMIT 10""",
        (test_id,)
    )
    return test


def api_create_test(data):
    required = ["name", "test_type", "scope", "steps"]
    for f in required:
        if not data.get(f):
            return {"error": f"Missing required field: {f}"}, 400

    ts = now_iso()
    test_id = execute_db(
        """INSERT INTO tests (name, description, test_type, scope, steps,
           expected_result, target_url, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (data["name"], data.get("description", ""), data["test_type"],
         data["scope"], data["steps"], data.get("expected_result", ""),
         data.get("target_url", ""), ts, ts)
    )

    module_ids = data.get("module_ids", [])
    if module_ids:
        stmts = [
            ("INSERT INTO test_modules (test_id, module_id) VALUES (?, ?)", (test_id, mid))
            for mid in module_ids
        ]
        execute_db_many(stmts)

    return {"id": test_id, "message": "Test created"}


def api_update_test(test_id, data):
    existing = query_db("SELECT id FROM tests WHERE id = ?", (test_id,), one=True)
    if not existing:
        return {"error": "Test not found"}, 404

    updatable = ["name", "description", "test_type", "scope", "steps",
                 "expected_result", "target_url", "is_active"]
    sets = []
    vals = []
    for field in updatable:
        if field in data:
            sets.append(f"{field} = ?")
            vals.append(data[field])

    if sets:
        sets.append("updated_at = ?")
        vals.append(now_iso())
        vals.append(test_id)
        execute_db(f"UPDATE tests SET {', '.join(sets)} WHERE id = ?", vals)

    if "module_ids" in data:
        stmts = [("DELETE FROM test_modules WHERE test_id = ?", (test_id,))]
        for mid in data["module_ids"]:
            stmts.append(
                ("INSERT INTO test_modules (test_id, module_id) VALUES (?, ?)", (test_id, mid))
            )
        execute_db_many(stmts)

    return {"message": "Test updated"}


def api_delete_test(test_id):
    existing = query_db("SELECT id FROM tests WHERE id = ?", (test_id,), one=True)
    if not existing:
        return {"error": "Test not found"}, 404
    execute_db(
        "UPDATE tests SET is_active = 0, updated_at = ? WHERE id = ?",
        (now_iso(), test_id)
    )
    return {"message": "Test deactivated"}


def api_runs(params):
    conditions = ["1=1"]
    sql_params = []
    if "type" in params:
        conditions.append("r.run_type = ?")
        sql_params.append(params["type"][0])
    if "status" in params:
        conditions.append("r.status = ?")
        sql_params.append(params["status"][0])

    where = " AND ".join(conditions)
    return query_db(
        f"""SELECT r.id, r.name, r.run_type, r.device_os, r.browser,
            r.triggered_by, r.status, r.started_at, r.completed_at, r.notes,
            COUNT(tr.id) as total,
            SUM(CASE WHEN tr.status='pass' THEN 1 ELSE 0 END) as passed,
            SUM(CASE WHEN tr.status='fail' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN tr.status='error' THEN 1 ELSE 0 END) as errored,
            SUM(CASE WHEN tr.status='skipped' THEN 1 ELSE 0 END) as skipped
            FROM runs r LEFT JOIN test_runs tr ON r.id = tr.run_id
            WHERE {where}
            GROUP BY r.id ORDER BY r.started_at DESC""",
        sql_params
    )


def api_run_detail(run_id):
    run = query_db("SELECT * FROM runs WHERE id = ?", (run_id,), one=True)
    if not run:
        return None

    test_results = query_db(
        """SELECT tr.id as test_run_id, tr.test_id, t.name as test_name,
           t.description as test_description, tr.status, tr.output, tr.remarks,
           tr.started_at, tr.completed_at
           FROM test_runs tr JOIN tests t ON tr.test_id = t.id
           WHERE tr.run_id = ?
           ORDER BY CASE tr.status WHEN 'fail' THEN 0 WHEN 'error' THEN 1
           WHEN 'skipped' THEN 2 ELSE 3 END, tr.started_at""",
        (run_id,)
    )

    # Attach linked bugs to each test result
    bug_links = query_db(
        """SELECT btr.test_run_id, b.id as bug_id, b.title, b.severity, b.status, btr.notes
           FROM bug_test_runs btr JOIN bugs b ON btr.bug_id = b.id
           WHERE btr.test_run_id IN (SELECT id FROM test_runs WHERE run_id = ?)""",
        (run_id,)
    )
    bugs_by_tr = {}
    for bl in bug_links:
        bugs_by_tr.setdefault(bl["test_run_id"], []).append(bl)

    for tr in test_results:
        tr["bugs"] = bugs_by_tr.get(tr["test_run_id"], [])

    run["test_results"] = test_results
    run["total"] = len(test_results)
    run["passed"] = sum(1 for t in test_results if t["status"] == "pass")
    run["failed"] = sum(1 for t in test_results if t["status"] == "fail")
    run["errored"] = sum(1 for t in test_results if t["status"] == "error")
    run["skipped"] = sum(1 for t in test_results if t["status"] == "skipped")
    return run


def api_bugs(params):
    conditions = ["1=1"]
    sql_params = []
    if "severity" in params:
        conditions.append("b.severity = ?")
        sql_params.append(params["severity"][0])
    if "status" in params:
        conditions.append("b.status = ?")
        sql_params.append(params["status"][0])

    where = " AND ".join(conditions)
    return query_db(
        f"""SELECT b.id, b.title, b.description, b.severity, b.status,
            m.key as module_key, m.name as module_name,
            b.first_seen_at, b.resolved_at,
            COUNT(btr.test_run_id) as times_seen
            FROM bugs b LEFT JOIN modules m ON b.module_id = m.id
            LEFT JOIN bug_test_runs btr ON b.id = btr.bug_id
            WHERE {where}
            GROUP BY b.id
            ORDER BY CASE b.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
            WHEN 'medium' THEN 2 ELSE 3 END""",
        sql_params
    )


def api_bug_detail(bug_id):
    bug = query_db(
        """SELECT b.*, m.key as module_key, m.name as module_name
           FROM bugs b LEFT JOIN modules m ON b.module_id = m.id
           WHERE b.id = ?""",
        (bug_id,), one=True
    )
    if not bug:
        return None
    bug["occurrences"] = query_db(
        """SELECT btr.test_run_id, tr.run_id, r.name as run_name,
           t.name as test_name, tr.status, btr.notes, btr.created_at
           FROM bug_test_runs btr
           JOIN test_runs tr ON btr.test_run_id = tr.id
           JOIN tests t ON tr.test_id = t.id
           JOIN runs r ON tr.run_id = r.id
           WHERE btr.bug_id = ?
           ORDER BY btr.created_at DESC""",
        (bug_id,)
    )
    return bug


def api_modules():
    return query_db(
        """SELECT m.id, m.key, m.name, m.description,
           COUNT(DISTINCT CASE WHEN t.is_active=1 THEN tm.test_id END) as test_count,
           COUNT(DISTINCT CASE WHEN b.status IN ('open','investigating') THEN b.id END) as open_bug_count
           FROM modules m
           LEFT JOIN test_modules tm ON m.id = tm.module_id
           LEFT JOIN tests t ON tm.test_id = t.id
           LEFT JOIN bugs b ON m.id = b.module_id
           GROUP BY m.id ORDER BY m.id"""
    )


def api_workflows():
    workflows = query_db("SELECT * FROM inter_module_workflows ORDER BY id")
    for wf in workflows:
        wf["modules"] = query_db(
            """SELECT m.id, m.key, m.name FROM modules m
               JOIN workflow_modules wm ON m.id = wm.module_id
               WHERE wm.workflow_id = ?""",
            (wf["id"],)
        )
    return workflows


# ─── HTML SPA ───────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HB QA Dashboard</title>
<style>
:root {
  --bg-primary: #0f172a;
  --bg-secondary: #f8fafc;
  --bg-card: #ffffff;
  --text-primary: #1e293b;
  --text-secondary: #64748b;
  --text-muted: #94a3b8;
  --border: #e2e8f0;
  --border-light: #f1f5f9;
  --pass: #22c55e;
  --pass-bg: rgba(34,197,94,0.12);
  --fail: #ef4444;
  --fail-bg: rgba(239,68,68,0.12);
  --error: #f59e0b;
  --error-bg: rgba(245,158,11,0.12);
  --skipped: #94a3b8;
  --skipped-bg: rgba(148,163,184,0.12);
  --running: #3b82f6;
  --running-bg: rgba(59,130,246,0.12);
  --completed: #22c55e;
  --aborted: #ef4444;
  --critical: #ef4444;
  --high: #f97316;
  --medium: #f59e0b;
  --low: #6366f1;
  --investigating: #f59e0b;
  --fixed: #22c55e;
  --wont_fix: #94a3b8;
  --duplicate: #94a3b8;
  --open: #ef4444;
  --accent: #3b82f6;
  --accent-bg: rgba(59,130,246,0.08);
  --sidebar-w: 220px;
}
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg-secondary); color: var(--text-primary);
  display: flex; min-height: 100vh;
}

/* Sidebar */
#sidebar {
  width: var(--sidebar-w); background: var(--bg-primary); color: #fff;
  display: flex; flex-direction: column; position: fixed; top: 0; left: 0;
  height: 100vh; z-index: 100;
}
#sidebar .logo { padding: 20px 16px; font-size: 15px; font-weight: 700;
  border-bottom: 1px solid rgba(255,255,255,0.1); letter-spacing: -0.3px; }
#sidebar .logo span { color: var(--accent); }
#sidebar nav { flex: 1; padding: 8px 0; }
#sidebar nav a {
  display: flex; align-items: center; gap: 10px; padding: 10px 16px;
  color: rgba(255,255,255,0.6); text-decoration: none; font-size: 13px;
  font-weight: 500; transition: all 0.15s; border-left: 3px solid transparent;
}
#sidebar nav a:hover { color: #fff; background: rgba(255,255,255,0.05); }
#sidebar nav a.active { color: #fff; background: rgba(255,255,255,0.08);
  border-left-color: var(--accent); }
#sidebar nav a svg { width: 18px; height: 18px; opacity: 0.7; flex-shrink: 0; }
#sidebar nav a.active svg { opacity: 1; }
#sidebar .sidebar-footer { padding: 12px 16px; font-size: 11px;
  color: rgba(255,255,255,0.3); border-top: 1px solid rgba(255,255,255,0.08); }

/* Main content */
#main { margin-left: var(--sidebar-w); flex: 1; padding: 24px 32px; min-height: 100vh; }
.view { display: none; }
.view.active { display: block; }

/* Page header */
.page-header { display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 20px; }
.page-header h1 { font-size: 20px; font-weight: 700; letter-spacing: -0.3px; }
.page-header .subtitle { font-size: 13px; color: var(--text-secondary); margin-top: 2px; }

/* Cards */
.card { background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 8px; padding: 16px; }
.card-shadow { box-shadow: 0 1px 3px rgba(0,0,0,0.06); }

/* Summary cards row */
.summary-cards { display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 14px; margin-bottom: 20px; }
.summary-card { text-align: center; padding: 20px 16px; }
.summary-card .label { font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.5px; color: var(--text-secondary); font-weight: 600; margin-bottom: 6px; }
.summary-card .value { font-size: 28px; font-weight: 700; letter-spacing: -0.5px; }
.summary-card .sub { font-size: 12px; color: var(--text-muted); margin-top: 4px; }

/* Dashboard grid */
.dash-grid { display: grid; grid-template-columns: 1fr 320px; gap: 14px; margin-bottom: 20px; }
.dash-grid-full { grid-column: 1 / -1; }

/* Tables */
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.5px; color: var(--text-secondary); font-weight: 600;
  padding: 8px 12px; border-bottom: 1px solid var(--border); }
td { padding: 10px 12px; font-size: 13px; border-bottom: 1px solid var(--border-light); }
tr:hover td { background: var(--accent-bg); }
tr.clickable { cursor: pointer; }
tr.inactive td { opacity: 0.45; }

/* Badges */
.badge {
  display: inline-block; padding: 2px 8px; border-radius: 9999px;
  font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px;
}
.badge-pass { background: var(--pass-bg); color: var(--pass); }
.badge-fail { background: var(--fail-bg); color: var(--fail); }
.badge-error { background: var(--error-bg); color: var(--error); }
.badge-skipped { background: var(--skipped-bg); color: var(--skipped); }
.badge-running { background: var(--running-bg); color: var(--running); }
.badge-completed { background: var(--pass-bg); color: var(--completed); }
.badge-aborted { background: var(--fail-bg); color: var(--aborted); }
.badge-smoke { background: rgba(59,130,246,0.1); color: #3b82f6; }
.badge-critical { background: var(--fail-bg); color: var(--critical); }
.badge-regression { background: rgba(168,85,247,0.1); color: #a855f7; }
.badge-custom { background: rgba(107,114,128,0.1); color: #6b7280; }
.badge-sev-critical { background: var(--fail-bg); color: var(--critical); }
.badge-sev-high { background: rgba(249,115,22,0.1); color: var(--high); }
.badge-sev-medium { background: var(--error-bg); color: var(--medium); }
.badge-sev-low { background: rgba(99,102,241,0.1); color: var(--low); }
.badge-open { background: var(--fail-bg); color: var(--open); }
.badge-investigating { background: var(--error-bg); color: var(--investigating); }
.badge-fixed { background: var(--pass-bg); color: var(--fixed); }
.badge-wont_fix { background: var(--skipped-bg); color: var(--wont_fix); }
.badge-duplicate { background: var(--skipped-bg); color: var(--duplicate); }

/* Progress bar */
.progress-bar { display: flex; height: 8px; border-radius: 4px; overflow: hidden;
  background: var(--border-light); min-width: 100px; }
.progress-bar .seg-pass { background: var(--pass); }
.progress-bar .seg-fail { background: var(--fail); }
.progress-bar .seg-error { background: var(--error); }
.progress-bar .seg-skipped { background: var(--skipped); }

/* Filters */
.filters { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 16px; }
.filters input, .filters select {
  padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px;
  font-size: 13px; background: var(--bg-card); color: var(--text-primary);
  outline: none;
}
.filters input:focus, .filters select:focus { border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(59,130,246,0.15); }
.filters input { min-width: 200px; }
.filters label { font-size: 13px; color: var(--text-secondary); display: flex;
  align-items: center; gap: 4px; cursor: pointer; }
.filters label input[type="checkbox"] { accent-color: var(--accent); }

/* Buttons */
.btn {
  display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px;
  border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer;
  border: 1px solid transparent; transition: all 0.15s;
}
.btn-primary { background: var(--accent); color: #fff; }
.btn-primary:hover { background: #2563eb; }
.btn-ghost { background: transparent; color: var(--text-secondary); border-color: var(--border); }
.btn-ghost:hover { background: var(--bg-secondary); color: var(--text-primary); }
.btn-sm { padding: 4px 8px; font-size: 12px; }
.btn-icon { padding: 4px; border: none; background: transparent;
  color: var(--text-muted); cursor: pointer; border-radius: 4px; }
.btn-icon:hover { background: var(--bg-secondary); color: var(--text-primary); }

/* Back link */
.back-link { display: inline-flex; align-items: center; gap: 4px;
  font-size: 13px; color: var(--accent); text-decoration: none; cursor: pointer;
  margin-bottom: 12px; font-weight: 500; }
.back-link:hover { text-decoration: underline; }

/* Detail header */
.detail-header { margin-bottom: 20px; }
.detail-header h2 { font-size: 18px; font-weight: 700; margin-bottom: 6px; }
.detail-meta { display: flex; gap: 16px; flex-wrap: wrap; font-size: 13px;
  color: var(--text-secondary); }
.detail-meta .meta-item { display: flex; align-items: center; gap: 4px; }

/* Results summary bar */
.results-bar { display: flex; align-items: center; gap: 16px; padding: 14px;
  margin-bottom: 16px; }
.results-bar .counts { display: flex; gap: 14px; }
.results-bar .count-item { display: flex; align-items: center; gap: 4px;
  font-size: 13px; font-weight: 600; }
.results-bar .count-dot { width: 8px; height: 8px; border-radius: 50%; }

/* Test result rows */
.test-result { border: 1px solid var(--border-light); border-radius: 8px;
  margin-bottom: 8px; overflow: hidden; }
.test-result-header {
  display: flex; align-items: center; gap: 10px; padding: 10px 14px;
  cursor: pointer; font-size: 13px;
}
.test-result-header:hover { background: var(--accent-bg); }
.test-result-body { padding: 0 14px 14px 42px; display: none; }
.test-result.expanded .test-result-body { display: block; }
.test-result-body .output-block {
  background: #1e293b; color: #e2e8f0; padding: 12px; border-radius: 6px;
  font-family: 'SF Mono', 'Fira Code', Consolas, monospace; font-size: 12px;
  line-height: 1.5; white-space: pre-wrap; word-break: break-word;
  max-height: 200px; overflow-y: auto; margin: 8px 0;
}
.test-result-body .remarks-block {
  font-size: 13px; color: var(--text-secondary); font-style: italic;
  margin: 8px 0; padding: 8px 12px; background: var(--bg-secondary);
  border-radius: 6px; border-left: 3px solid var(--accent);
}
.test-result-body .bug-link {
  display: inline-flex; align-items: center; gap: 4px; font-size: 12px;
  color: var(--fail); cursor: pointer; margin-top: 4px;
}
.test-result-body .bug-link:hover { text-decoration: underline; }
.test-result-body .section-label { font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.5px; color: var(--text-muted); font-weight: 600;
  margin-top: 10px; margin-bottom: 4px; }
.test-result-name { font-weight: 500; flex: 1; }
.chevron { color: var(--text-muted); transition: transform 0.15s; font-size: 16px; }
.test-result.expanded .chevron { transform: rotate(90deg); }

/* Modules grid */
.modules-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px; }
.module-card { padding: 16px; }
.module-card .module-name { font-size: 14px; font-weight: 600; margin-bottom: 2px; }
.module-card .module-key { font-size: 11px; color: var(--text-muted);
  font-family: monospace; margin-bottom: 8px; }
.module-card .module-desc { font-size: 12px; color: var(--text-secondary);
  margin-bottom: 10px; line-height: 1.4; }
.module-card .module-stats { display: flex; gap: 12px; font-size: 12px; }
.module-card .module-stat { display: flex; align-items: center; gap: 4px; }

/* Workflow cards */
.workflow-card { padding: 14px; margin-bottom: 10px; }
.workflow-card .wf-name { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
.workflow-card .wf-desc { font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; }
.workflow-card .wf-modules { display: flex; gap: 6px; flex-wrap: wrap; }
.workflow-card .wf-module-pill {
  background: var(--accent-bg); color: var(--accent); padding: 3px 10px;
  border-radius: 9999px; font-size: 11px; font-weight: 600;
}

/* Empty state */
.empty-state { text-align: center; padding: 48px 24px; color: var(--text-muted); }
.empty-state svg { width: 48px; height: 48px; margin-bottom: 12px; opacity: 0.4; }
.empty-state .empty-title { font-size: 14px; font-weight: 600; margin-bottom: 4px;
  color: var(--text-secondary); }
.empty-state .empty-text { font-size: 13px; line-height: 1.5; }

/* Modal */
.modal-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.4); z-index: 200; display: none;
  align-items: center; justify-content: center;
}
.modal-overlay.open { display: flex; }
.modal {
  background: var(--bg-card); border-radius: 12px; width: 560px;
  max-height: 85vh; overflow-y: auto; box-shadow: 0 20px 60px rgba(0,0,0,0.2);
}
.modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid var(--border);
}
.modal-header h3 { font-size: 16px; font-weight: 700; }
.modal-body { padding: 20px; }
.modal-footer { padding: 12px 20px; border-top: 1px solid var(--border);
  display: flex; justify-content: flex-end; gap: 8px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 12px; font-weight: 600;
  color: var(--text-secondary); margin-bottom: 4px; text-transform: uppercase;
  letter-spacing: 0.3px; }
.form-group input, .form-group select, .form-group textarea {
  width: 100%; padding: 8px 10px; border: 1px solid var(--border);
  border-radius: 6px; font-size: 13px; font-family: inherit;
  background: var(--bg-card); color: var(--text-primary);
}
.form-group input:focus, .form-group select:focus, .form-group textarea:focus {
  outline: none; border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(59,130,246,0.15);
}
.form-group textarea { min-height: 80px; resize: vertical; }
.form-group .checkbox-grid { display: flex; flex-wrap: wrap; gap: 6px; }
.form-group .checkbox-grid label {
  display: flex; align-items: center; gap: 4px; padding: 4px 10px;
  border: 1px solid var(--border); border-radius: 6px; font-size: 12px;
  font-weight: 500; cursor: pointer; text-transform: none; letter-spacing: 0;
  color: var(--text-primary); transition: all 0.15s;
}
.form-group .checkbox-grid label:has(input:checked) {
  background: var(--accent-bg); border-color: var(--accent); color: var(--accent);
}
.form-group .checkbox-grid input { display: none; }
.form-error { color: var(--fail); font-size: 12px; margin-top: 4px; }

/* Bug detail */
.bug-detail-occurrences { margin-top: 16px; }
.occurrence-item { display: flex; align-items: center; gap: 10px; padding: 8px 0;
  border-bottom: 1px solid var(--border-light); font-size: 13px; }
.occurrence-item:last-child { border-bottom: none; }
.occurrence-item .occ-link { color: var(--accent); cursor: pointer; }
.occurrence-item .occ-link:hover { text-decoration: underline; }

@media (max-width: 900px) {
  .summary-cards { grid-template-columns: repeat(2, 1fr); }
  .dash-grid { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  #sidebar { width: 56px; }
  #sidebar .logo span, #sidebar nav a span, #sidebar .sidebar-footer { display: none; }
  #sidebar .logo { padding: 16px 12px; text-align: center; }
  #sidebar nav a { justify-content: center; padding: 12px; }
  #main { margin-left: 56px; padding: 16px; }
  .summary-cards { grid-template-columns: 1fr 1fr; }
}
</style>
</head>
<body>

<aside id="sidebar">
  <div class="logo"><span>HB</span> Test Suite</div>
  <nav>
    <a href="#dashboard" class="active" onclick="navigate('dashboard')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
      <span>Dashboard</span>
    </a>
    <a href="#tests" onclick="navigate('tests')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
      <span>Tests</span>
    </a>
    <a href="#runs" onclick="navigate('runs')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
      <span>Runs</span>
    </a>
    <a href="#bugs" onclick="navigate('bugs')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 2l1.88 1.88M14.12 3.88L16 2M9 7.13v-1a3 3 0 116 0v1M12 20c-3.87 0-7-3.13-7-7h2c0 2.76 2.24 5 5 5s5-2.24 5-5h2c0 3.87-3.13 7-7 7zM5 13H2M22 13h-3M6.31 17.69L4.5 19.5M19.5 19.5l-1.81-1.81"/><circle cx="12" cy="13" r="3"/></svg>
      <span>Bugs</span>
    </a>
    <a href="#modules" onclick="navigate('modules')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
      <span>Modules</span>
    </a>
  </nav>
  <div class="sidebar-footer">tests.db</div>
</aside>

<div id="main">

  <!-- DASHBOARD VIEW -->
  <div id="view-dashboard" class="view active">
    <div class="page-header"><div><h1>Dashboard</h1><div class="subtitle">Overview of your test suite</div></div></div>
    <div class="summary-cards" id="summary-cards"></div>
    <div class="dash-grid">
      <div class="card card-shadow">
        <div style="font-size:13px;font-weight:600;margin-bottom:10px;">Recent Runs</div>
        <div class="table-wrap" id="dash-recent-runs"></div>
      </div>
      <div class="card card-shadow">
        <div style="font-size:13px;font-weight:600;margin-bottom:10px;">Open Bugs</div>
        <div id="dash-open-bugs"></div>
      </div>
    </div>
    <div class="card card-shadow">
      <div style="font-size:13px;font-weight:600;margin-bottom:10px;">Module Coverage</div>
      <div class="modules-grid" id="dash-module-coverage"></div>
    </div>
  </div>

  <!-- TESTS VIEW -->
  <div id="view-tests" class="view">
    <div class="page-header">
      <div><h1>Tests</h1><div class="subtitle">All test definitions</div></div>
      <button class="btn btn-primary" onclick="openTestModal()">+ New Test</button>
    </div>
    <div class="filters" id="test-filters">
      <input type="text" id="test-search" placeholder="Search tests..." oninput="debounceLoadTests()">
      <select id="test-type-filter" onchange="loadTests()">
        <option value="">All Types</option>
        <option value="smoke">Smoke</option>
        <option value="critical">Critical</option>
        <option value="regression">Regression</option>
      </select>
      <select id="test-scope-filter" onchange="loadTests()">
        <option value="">All Scopes</option>
        <option value="module">Module</option>
        <option value="inter_module">Inter-Module</option>
      </select>
      <label><input type="checkbox" id="test-show-inactive" onchange="loadTests()"> Show inactive</label>
    </div>
    <div class="card card-shadow">
      <div class="table-wrap" id="tests-table"></div>
    </div>
  </div>

  <!-- RUNS VIEW -->
  <div id="view-runs" class="view">
    <div class="page-header"><div><h1>Runs</h1><div class="subtitle">Test execution history</div></div></div>
    <div class="filters">
      <select id="run-type-filter" onchange="loadRuns()">
        <option value="">All Types</option>
        <option value="smoke">Smoke</option>
        <option value="critical">Critical</option>
        <option value="regression">Regression</option>
        <option value="custom">Custom</option>
      </select>
      <select id="run-status-filter" onchange="loadRuns()">
        <option value="">All Status</option>
        <option value="running">Running</option>
        <option value="completed">Completed</option>
        <option value="aborted">Aborted</option>
      </select>
    </div>
    <div class="card card-shadow">
      <div class="table-wrap" id="runs-table"></div>
    </div>
  </div>

  <!-- RUN DETAIL VIEW -->
  <div id="view-run-detail" class="view">
    <a class="back-link" onclick="navigate('runs')">&larr; Back to Runs</a>
    <div id="run-detail-content"></div>
  </div>

  <!-- BUGS VIEW -->
  <div id="view-bugs" class="view">
    <div class="page-header"><div><h1>Bugs</h1><div class="subtitle">Tracked issues from test failures</div></div></div>
    <div class="filters">
      <select id="bug-severity-filter" onchange="loadBugs()">
        <option value="">All Severities</option>
        <option value="critical">Critical</option>
        <option value="high">High</option>
        <option value="medium">Medium</option>
        <option value="low">Low</option>
      </select>
      <select id="bug-status-filter" onchange="loadBugs()">
        <option value="">All Status</option>
        <option value="open">Open</option>
        <option value="investigating">Investigating</option>
        <option value="fixed">Fixed</option>
        <option value="wont_fix">Won't Fix</option>
        <option value="duplicate">Duplicate</option>
      </select>
    </div>
    <div class="card card-shadow">
      <div class="table-wrap" id="bugs-table"></div>
    </div>
  </div>

  <!-- BUG DETAIL VIEW -->
  <div id="view-bug-detail" class="view">
    <a class="back-link" onclick="navigate('bugs')">&larr; Back to Bugs</a>
    <div id="bug-detail-content"></div>
  </div>

  <!-- MODULES VIEW -->
  <div id="view-modules" class="view">
    <div class="page-header"><div><h1>Modules</h1><div class="subtitle">Application modules and workflows</div></div></div>
    <div class="modules-grid" id="modules-grid"></div>
    <div style="margin-top:24px;">
      <div class="page-header"><div><h1 style="font-size:16px;">Inter-Module Workflows</h1></div></div>
      <div id="workflows-list"></div>
    </div>
  </div>

</div>

<!-- TEST MODAL -->
<div class="modal-overlay" id="test-modal">
  <div class="modal">
    <div class="modal-header">
      <h3 id="test-modal-title">New Test</h3>
      <button class="btn-icon" onclick="closeTestModal()" style="font-size:20px;">&times;</button>
    </div>
    <div class="modal-body">
      <div id="test-form-error" class="form-error" style="margin-bottom:10px;display:none;"></div>
      <input type="hidden" id="test-form-id">
      <div class="form-group">
        <label>Name</label>
        <input type="text" id="test-form-name" placeholder="e.g. auth_login_valid_credentials">
      </div>
      <div class="form-group">
        <label>Description</label>
        <textarea id="test-form-desc" rows="2" placeholder="What does this test verify?"></textarea>
      </div>
      <div style="display:flex;gap:10px;">
        <div class="form-group" style="flex:1;">
          <label>Type</label>
          <select id="test-form-type">
            <option value="smoke">Smoke</option>
            <option value="critical">Critical</option>
            <option value="regression">Regression</option>
          </select>
        </div>
        <div class="form-group" style="flex:1;">
          <label>Scope</label>
          <select id="test-form-scope">
            <option value="module">Module</option>
            <option value="inter_module">Inter-Module</option>
          </select>
        </div>
      </div>
      <div class="form-group">
        <label>Steps</label>
        <textarea id="test-form-steps" rows="4" placeholder="Step-by-step instructions..."></textarea>
      </div>
      <div class="form-group">
        <label>Expected Result</label>
        <textarea id="test-form-expected" rows="2" placeholder="What should happen?"></textarea>
      </div>
      <div class="form-group">
        <label>Target URL</label>
        <input type="text" id="test-form-url" placeholder="https://...">
      </div>
      <div class="form-group">
        <label>Modules</label>
        <div class="checkbox-grid" id="test-form-modules"></div>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="closeTestModal()">Cancel</button>
      <button class="btn btn-primary" onclick="saveTest()">Save Test</button>
    </div>
  </div>
</div>

<script>
// ── State ──────────────────────────────────────────────────
let currentView = 'dashboard';
let allModules = [];
let searchTimeout = null;

// ── Navigation ─────────────────────────────────────────────
function navigate(view, id) {
  currentView = view;
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('#sidebar nav a').forEach(a => a.classList.remove('active'));

  const viewEl = document.getElementById('view-' + view);
  if (viewEl) viewEl.classList.add('active');

  const navLink = document.querySelector('#sidebar nav a[href="#' + view.split('/')[0] + '"]');
  // For detail views, highlight the parent nav
  const parentView = view.replace('-detail', '').replace('run-detail', 'runs').replace('bug-detail', 'bugs');
  const parentLink = document.querySelector('#sidebar nav a[href="#' + parentView + '"]');
  if (parentLink) parentLink.classList.add('active');
  else if (navLink) navLink.classList.add('active');

  // Update hash
  if (id) {
    window.location.hash = view + '/' + id;
  } else {
    window.location.hash = view;
  }

  // Load data
  switch(view) {
    case 'dashboard': loadDashboard(); break;
    case 'tests': loadTests(); break;
    case 'runs': loadRuns(); break;
    case 'run-detail': loadRunDetail(id); break;
    case 'bugs': loadBugs(); break;
    case 'bug-detail': loadBugDetail(id); break;
    case 'modules': loadModules(); break;
  }
}

// ── Helpers ────────────────────────────────────────────────
function esc(str) {
  if (str == null) return '';
  const d = document.createElement('div');
  d.textContent = String(str);
  return d.innerHTML;
}

function badgeFor(status) {
  return '<span class="badge badge-' + esc(status) + '">' + esc(status) + '</span>';
}

function sevBadge(severity) {
  return '<span class="badge badge-sev-' + esc(severity) + '">' + esc(severity) + '</span>';
}

function typeBadge(type) {
  return '<span class="badge badge-' + esc(type) + '">' + esc(type) + '</span>';
}

function progressBar(passed, failed, errored, skipped, total) {
  if (!total) return '<div class="progress-bar"></div>';
  const p = (passed/total*100), f = (failed/total*100),
        e = (errored/total*100), s = (skipped/total*100);
  return '<div class="progress-bar">' +
    '<div class="seg-pass" style="width:' + p + '%"></div>' +
    '<div class="seg-fail" style="width:' + f + '%"></div>' +
    '<div class="seg-error" style="width:' + e + '%"></div>' +
    '<div class="seg-skipped" style="width:' + s + '%"></div>' +
    '</div>';
}

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) +
    ' ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function formatDuration(start, end) {
  if (!start || !end) return '—';
  const ms = new Date(end) - new Date(start);
  if (ms < 0) return '—';
  const s = Math.floor(ms/1000), m = Math.floor(s/60), h = Math.floor(m/60);
  if (h > 0) return h + 'h ' + (m%60) + 'm';
  if (m > 0) return m + 'm ' + (s%60) + 's';
  return s + 's';
}

function emptyState(title, text) {
  return '<div class="empty-state">' +
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>' +
    '<div class="empty-title">' + esc(title) + '</div>' +
    '<div class="empty-text">' + esc(text) + '</div></div>';
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  return res.json();
}

// ── Dashboard ──────────────────────────────────────────────
async function loadDashboard() {
  const d = await api('/api/summary');

  // Summary cards
  document.getElementById('summary-cards').innerHTML =
    '<div class="card card-shadow summary-card"><div class="label">Total Tests</div>' +
    '<div class="value">' + d.active_tests + '</div>' +
    '<div class="sub">' + d.total_tests + ' total (' + (d.total_tests - d.active_tests) + ' inactive)</div></div>' +

    '<div class="card card-shadow summary-card"><div class="label">Last Run</div>' +
    '<div class="value">' + (d.last_run ? '#' + d.last_run.id : '—') + '</div>' +
    '<div class="sub">' + (d.last_run ? esc(d.last_run.name || 'Unnamed') : 'No runs yet') + '</div></div>' +

    '<div class="card card-shadow summary-card"><div class="label">Open Bugs</div>' +
    '<div class="value" style="color:' + (d.open_bugs_total > 0 ? 'var(--fail)' : 'inherit') + '">' +
    d.open_bugs_total + '</div>' +
    '<div class="sub">' + Object.entries(d.open_bugs_by_severity).map(
      ([k,v]) => v + ' ' + k).join(', ') + (d.open_bugs_total === 0 ? 'None' : '') + '</div></div>' +

    '<div class="card card-shadow summary-card"><div class="label">Pass Rate</div>' +
    '<div class="value" style="color:' + (d.pass_rate !== null ? (d.pass_rate >= 90 ? 'var(--pass)' : d.pass_rate >= 70 ? 'var(--error)' : 'var(--fail)') : 'inherit') + '">' +
    (d.pass_rate !== null ? d.pass_rate + '%' : '—') + '</div>' +
    '<div class="sub">From last completed run</div></div>';

  // Recent runs
  if (d.recent_runs.length === 0) {
    document.getElementById('dash-recent-runs').innerHTML =
      emptyState('No runs yet', 'Test runs will appear here after execution.');
  } else {
    let html = '<table><thead><tr><th>Run</th><th>Type</th><th>Status</th><th>Results</th><th>Date</th></tr></thead><tbody>';
    d.recent_runs.forEach(r => {
      html += '<tr class="clickable" onclick="navigate(\'run-detail\',' + r.id + ')">' +
        '<td><strong>#' + r.id + '</strong> ' + esc(r.name || '') + '</td>' +
        '<td>' + typeBadge(r.run_type) + '</td>' +
        '<td>' + badgeFor(r.status) + '</td>' +
        '<td>' + progressBar(r.passed, r.failed, r.errored, r.skipped, r.total) +
        ' <span style="font-size:12px;color:var(--text-muted)">' + r.passed + '/' + r.total + '</span></td>' +
        '<td style="font-size:12px;color:var(--text-secondary)">' + formatDate(r.started_at) + '</td></tr>';
    });
    html += '</tbody></table>';
    document.getElementById('dash-recent-runs').innerHTML = html;
  }

  // Open bugs
  if (d.open_bugs_list.length === 0) {
    document.getElementById('dash-open-bugs').innerHTML =
      '<div class="empty-state" style="padding:24px"><div class="empty-title" style="color:var(--pass)">All clear</div><div class="empty-text">No open bugs.</div></div>';
  } else {
    let html = '';
    d.open_bugs_list.forEach(b => {
      html += '<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border-light);cursor:pointer;" onclick="navigate(\'bug-detail\',' + b.id + ')">' +
        sevBadge(b.severity) +
        '<span style="font-size:13px;flex:1;">' + esc(b.title) + '</span>' +
        '<span style="font-size:11px;color:var(--text-muted)">' + esc(b.module_name || '') + '</span></div>';
    });
    document.getElementById('dash-open-bugs').innerHTML = html;
  }

  // Module coverage
  if (d.by_module.length === 0) {
    document.getElementById('dash-module-coverage').innerHTML =
      emptyState('No modules', 'Modules will appear after database initialization.');
  } else {
    let html = '';
    d.by_module.forEach(m => {
      html += '<div class="card" style="padding:12px;text-align:center;">' +
        '<div style="font-size:13px;font-weight:600;">' + esc(m.name) + '</div>' +
        '<div style="font-size:22px;font-weight:700;margin:4px 0;">' + (m.test_count || 0) + '</div>' +
        '<div style="font-size:11px;color:var(--text-muted);">tests</div></div>';
    });
    document.getElementById('dash-module-coverage').innerHTML = html;
  }
}

// ── Tests ──────────────────────────────────────────────────
function debounceLoadTests() {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(loadTests, 300);
}

async function loadTests() {
  const params = new URLSearchParams();
  const search = document.getElementById('test-search').value;
  const type = document.getElementById('test-type-filter').value;
  const scope = document.getElementById('test-scope-filter').value;
  const showInactive = document.getElementById('test-show-inactive').checked;

  if (search) params.set('search', search);
  if (type) params.set('type', type);
  if (scope) params.set('scope', scope);
  if (!showInactive) params.set('active', '1');

  const tests = await api('/api/tests?' + params);
  const container = document.getElementById('tests-table');

  if (tests.length === 0) {
    container.innerHTML = emptyState('No tests found',
      showInactive ? 'No tests match your filters.' : 'No active tests found. Create one or adjust filters.');
    return;
  }

  let html = '<table><thead><tr><th>#</th><th>Name</th><th>Type</th><th>Scope</th><th>Modules</th><th>History</th><th style="width:80px">Actions</th></tr></thead><tbody>';
  tests.forEach(t => {
    const rowClass = t.is_active ? '' : ' class="inactive"';
    const modules = t.modules.map(m => '<span style="font-size:11px;background:var(--bg-secondary);padding:1px 6px;border-radius:4px;">' + esc(m.key) + '</span>').join(' ');
    const history = t.last_results.map(r => '<span class="badge badge-' + r.status + '" style="font-size:9px;padding:1px 5px;">' + r.status[0].toUpperCase() + '</span>').join(' ');

    html += '<tr' + rowClass + '>' +
      '<td>' + t.id + '</td>' +
      '<td><strong style="cursor:pointer" onclick="toggleTestDetail(' + t.id + ', this)">' + esc(t.name) + '</strong></td>' +
      '<td>' + typeBadge(t.test_type) + '</td>' +
      '<td><span style="font-size:12px;">' + esc(t.scope) + '</span></td>' +
      '<td>' + (modules || '<span style="color:var(--text-muted);font-size:12px">—</span>') + '</td>' +
      '<td>' + (history || '<span style="color:var(--text-muted);font-size:12px">—</span>') + '</td>' +
      '<td>' +
      '<button class="btn-icon" title="Edit" onclick="editTest(' + t.id + ')">&#9998;</button> ' +
      (t.is_active
        ? '<button class="btn-icon" title="Deactivate" onclick="deactivateTest(' + t.id + ')">&#9744;</button>'
        : '<button class="btn-icon" title="Reactivate" onclick="reactivateTest(' + t.id + ')">&#9745;</button>') +
      '</td></tr>';

    // Hidden detail row
    html += '<tr id="test-detail-' + t.id + '" style="display:none"><td colspan="7" style="padding:12px 20px;background:var(--bg-secondary);">' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">' +
      '<div><div style="font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:2px;">DESCRIPTION</div><div style="font-size:13px;">' + esc(t.description || 'No description') + '</div></div>' +
      '<div><div style="font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:2px;">TARGET URL</div><div style="font-size:13px;">' + esc(t.target_url || 'Not set') + '</div></div>' +
      '</div>' +
      '<div style="margin-top:10px;"><div style="font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:2px;">STEPS</div>' +
      '<pre style="font-size:12px;background:#1e293b;color:#e2e8f0;padding:10px;border-radius:6px;white-space:pre-wrap;max-height:150px;overflow-y:auto;">' + esc(t.steps) + '</pre></div>' +
      '<div style="margin-top:8px;"><div style="font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:2px;">EXPECTED RESULT</div><div style="font-size:13px;">' + esc(t.expected_result || 'Not specified') + '</div></div>' +
      '</td></tr>';
  });
  html += '</tbody></table>';
  container.innerHTML = html;
}

function toggleTestDetail(id, el) {
  const row = document.getElementById('test-detail-' + id);
  if (row) row.style.display = row.style.display === 'none' ? '' : 'none';
}

async function openTestModal(testId) {
  // Load modules for checkboxes
  if (allModules.length === 0) {
    allModules = await api('/api/modules');
  }
  let checkboxes = '';
  allModules.forEach(m => {
    checkboxes += '<label><input type="checkbox" value="' + m.id + '"> ' + esc(m.name) + '</label>';
  });
  document.getElementById('test-form-modules').innerHTML = checkboxes;

  // Reset form
  document.getElementById('test-form-id').value = '';
  document.getElementById('test-form-name').value = '';
  document.getElementById('test-form-desc').value = '';
  document.getElementById('test-form-type').value = 'smoke';
  document.getElementById('test-form-scope').value = 'module';
  document.getElementById('test-form-steps').value = '';
  document.getElementById('test-form-expected').value = '';
  document.getElementById('test-form-url').value = '';
  document.getElementById('test-form-error').style.display = 'none';
  document.getElementById('test-modal-title').textContent = 'New Test';

  if (testId) {
    document.getElementById('test-modal-title').textContent = 'Edit Test';
    const t = await api('/api/tests/' + testId);
    if (t) {
      document.getElementById('test-form-id').value = t.id;
      document.getElementById('test-form-name').value = t.name || '';
      document.getElementById('test-form-desc').value = t.description || '';
      document.getElementById('test-form-type').value = t.test_type;
      document.getElementById('test-form-scope').value = t.scope;
      document.getElementById('test-form-steps').value = t.steps || '';
      document.getElementById('test-form-expected').value = t.expected_result || '';
      document.getElementById('test-form-url').value = t.target_url || '';
      const modIds = (t.modules || []).map(m => m.id);
      document.querySelectorAll('#test-form-modules input[type="checkbox"]').forEach(cb => {
        cb.checked = modIds.includes(parseInt(cb.value));
      });
    }
  }

  document.getElementById('test-modal').classList.add('open');
}

function closeTestModal() {
  document.getElementById('test-modal').classList.remove('open');
}

function editTest(id) { openTestModal(id); }

async function saveTest() {
  const id = document.getElementById('test-form-id').value;
  const data = {
    name: document.getElementById('test-form-name').value.trim(),
    description: document.getElementById('test-form-desc').value.trim(),
    test_type: document.getElementById('test-form-type').value,
    scope: document.getElementById('test-form-scope').value,
    steps: document.getElementById('test-form-steps').value.trim(),
    expected_result: document.getElementById('test-form-expected').value.trim(),
    target_url: document.getElementById('test-form-url').value.trim(),
    module_ids: []
  };
  document.querySelectorAll('#test-form-modules input:checked').forEach(cb => {
    data.module_ids.push(parseInt(cb.value));
  });

  const errEl = document.getElementById('test-form-error');

  if (!data.name || !data.steps) {
    errEl.textContent = 'Name and Steps are required.';
    errEl.style.display = 'block';
    return;
  }

  const url = id ? '/api/tests/' + id : '/api/tests';
  const method = id ? 'PUT' : 'POST';
  const res = await fetch(url, {
    method, headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
  const result = await res.json();

  if (result.error) {
    errEl.textContent = result.error;
    errEl.style.display = 'block';
    return;
  }

  closeTestModal();
  loadTests();
}

async function deactivateTest(id) {
  if (!confirm('Deactivate this test? It will be hidden from active views.')) return;
  await fetch('/api/tests/' + id, { method: 'DELETE' });
  loadTests();
}

async function reactivateTest(id) {
  await fetch('/api/tests/' + id, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ is_active: 1 })
  });
  loadTests();
}

// ── Runs ───────────────────────────────────────────────────
async function loadRuns() {
  const params = new URLSearchParams();
  const type = document.getElementById('run-type-filter').value;
  const status = document.getElementById('run-status-filter').value;
  if (type) params.set('type', type);
  if (status) params.set('status', status);

  const runs = await api('/api/runs?' + params);
  const container = document.getElementById('runs-table');

  if (runs.length === 0) {
    container.innerHTML = emptyState('No runs yet', 'Test runs will appear here after execution via Claude Code.');
    return;
  }

  let html = '<table><thead><tr><th>Run</th><th>Type</th><th>Status</th><th>Results</th><th>Browser / OS</th><th>Triggered By</th><th>Date</th></tr></thead><tbody>';
  runs.forEach(r => {
    html += '<tr class="clickable" onclick="navigate(\'run-detail\',' + r.id + ')">' +
      '<td><strong>#' + r.id + '</strong> ' + esc(r.name || '') + '</td>' +
      '<td>' + typeBadge(r.run_type) + '</td>' +
      '<td>' + badgeFor(r.status) + '</td>' +
      '<td style="min-width:140px">' + progressBar(r.passed, r.failed, r.errored, r.skipped, r.total) +
      ' <span style="font-size:12px;color:var(--text-muted)">' + (r.passed||0) + '/' + (r.total||0) + '</span></td>' +
      '<td style="font-size:12px">' + esc(r.browser || '—') + ' / ' + esc(r.device_os || '—') + '</td>' +
      '<td style="font-size:12px">' + esc(r.triggered_by || '—') + '</td>' +
      '<td style="font-size:12px;color:var(--text-secondary)">' + formatDate(r.started_at) + '</td></tr>';
  });
  html += '</tbody></table>';
  container.innerHTML = html;
}

async function loadRunDetail(id) {
  const r = await api('/api/runs/' + id);
  if (!r || r.error) {
    document.getElementById('run-detail-content').innerHTML =
      emptyState('Run not found', 'This run does not exist.');
    return;
  }

  let html = '<div class="detail-header">' +
    '<h2>Run #' + r.id + (r.name ? ': ' + esc(r.name) : '') + '</h2>' +
    '<div class="detail-meta">' +
    '<div class="meta-item">' + badgeFor(r.status) + '</div>' +
    '<div class="meta-item">Browser: <strong>' + esc(r.browser || '—') + '</strong></div>' +
    '<div class="meta-item">OS: <strong>' + esc(r.device_os || '—') + '</strong></div>' +
    '<div class="meta-item">By: <strong>' + esc(r.triggered_by || '—') + '</strong></div>' +
    '<div class="meta-item">Duration: <strong>' + formatDuration(r.started_at, r.completed_at) + '</strong></div>' +
    '<div class="meta-item">Started: <strong>' + formatDate(r.started_at) + '</strong></div>' +
    '</div>' +
    (r.notes ? '<div style="margin-top:8px;font-size:13px;color:var(--text-secondary);font-style:italic;">' + esc(r.notes) + '</div>' : '') +
    '</div>';

  // Results bar
  html += '<div class="card card-shadow results-bar">' +
    '<div style="flex:1">' + progressBar(r.passed, r.failed, r.errored, r.skipped, r.total) + '</div>' +
    '<div class="counts">' +
    '<div class="count-item"><div class="count-dot" style="background:var(--pass)"></div>' + (r.passed||0) + ' pass</div>' +
    '<div class="count-item"><div class="count-dot" style="background:var(--fail)"></div>' + (r.failed||0) + ' fail</div>' +
    '<div class="count-item"><div class="count-dot" style="background:var(--error)"></div>' + (r.errored||0) + ' error</div>' +
    '<div class="count-item"><div class="count-dot" style="background:var(--skipped)"></div>' + (r.skipped||0) + ' skip</div>' +
    '</div></div>';

  // Status filter
  html += '<div class="filters">' +
    '<button class="btn btn-sm btn-ghost run-filter-btn active" onclick="filterRunResults(\'all\', this)">All (' + r.total + ')</button>' +
    '<button class="btn btn-sm btn-ghost run-filter-btn" onclick="filterRunResults(\'pass\', this)">Pass (' + (r.passed||0) + ')</button>' +
    '<button class="btn btn-sm btn-ghost run-filter-btn" onclick="filterRunResults(\'fail\', this)">Fail (' + (r.failed||0) + ')</button>' +
    '<button class="btn btn-sm btn-ghost run-filter-btn" onclick="filterRunResults(\'error\', this)">Error (' + (r.errored||0) + ')</button>' +
    '<button class="btn btn-sm btn-ghost run-filter-btn" onclick="filterRunResults(\'skipped\', this)">Skip (' + (r.skipped||0) + ')</button>' +
    '</div>';

  // Test results
  if (r.test_results.length === 0) {
    html += emptyState('No test results', 'No tests were executed in this run.');
  } else {
    r.test_results.forEach(tr => {
      const expanded = (tr.status === 'fail' || tr.status === 'error') ? ' expanded' : '';
      html += '<div class="test-result' + expanded + '" data-status="' + tr.status + '">' +
        '<div class="test-result-header" onclick="this.parentElement.classList.toggle(\'expanded\')">' +
        badgeFor(tr.status) +
        '<span class="test-result-name">' + esc(tr.test_name) + '</span>' +
        '<span style="font-size:12px;color:var(--text-muted)">' + formatDuration(tr.started_at, tr.completed_at) + '</span>' +
        '<span class="chevron">&#9656;</span>' +
        '</div>' +
        '<div class="test-result-body">';

      if (tr.output) {
        html += '<div class="section-label">Output</div><div class="output-block">' + esc(tr.output) + '</div>';
      }
      if (tr.remarks) {
        html += '<div class="section-label">Remarks</div><div class="remarks-block">' + esc(tr.remarks) + '</div>';
      }
      if (tr.bugs && tr.bugs.length > 0) {
        html += '<div class="section-label">Linked Bugs</div>';
        tr.bugs.forEach(b => {
          html += '<div class="bug-link" onclick="navigate(\'bug-detail\',' + b.bug_id + ')">' +
            sevBadge(b.severity) + ' ' + esc(b.title) + ' ' + badgeFor(b.status) + '</div>';
        });
      }
      html += '</div></div>';
    });
  }

  document.getElementById('run-detail-content').innerHTML = html;
}

function filterRunResults(status, btn) {
  document.querySelectorAll('.run-filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.test-result').forEach(el => {
    if (status === 'all' || el.dataset.status === status) {
      el.style.display = '';
    } else {
      el.style.display = 'none';
    }
  });
}

// ── Bugs ───────────────────────────────────────────────────
async function loadBugs() {
  const params = new URLSearchParams();
  const sev = document.getElementById('bug-severity-filter').value;
  const status = document.getElementById('bug-status-filter').value;
  if (sev) params.set('severity', sev);
  if (status) params.set('status', status);

  const bugs = await api('/api/bugs?' + params);
  const container = document.getElementById('bugs-table');

  if (bugs.length === 0) {
    container.innerHTML = emptyState('No bugs tracked',
      'Bugs are logged automatically when tests fail. All clear for now.');
    return;
  }

  let html = '<table><thead><tr><th>#</th><th>Title</th><th>Severity</th><th>Status</th><th>Module</th><th>Seen</th><th>First Seen</th></tr></thead><tbody>';
  bugs.forEach(b => {
    html += '<tr class="clickable" onclick="navigate(\'bug-detail\',' + b.id + ')">' +
      '<td>' + b.id + '</td>' +
      '<td><strong>' + esc(b.title) + '</strong></td>' +
      '<td>' + sevBadge(b.severity) + '</td>' +
      '<td>' + badgeFor(b.status) + '</td>' +
      '<td style="font-size:12px">' + esc(b.module_name || '—') + '</td>' +
      '<td style="font-size:12px">' + (b.times_seen || 0) + 'x</td>' +
      '<td style="font-size:12px;color:var(--text-secondary)">' + formatDate(b.first_seen_at) + '</td></tr>';
  });
  html += '</tbody></table>';
  container.innerHTML = html;
}

async function loadBugDetail(id) {
  const b = await api('/api/bugs/' + id);
  if (!b || b.error) {
    document.getElementById('bug-detail-content').innerHTML =
      emptyState('Bug not found', 'This bug does not exist.');
    return;
  }

  let html = '<div class="detail-header">' +
    '<h2>BUG-' + b.id + ': ' + esc(b.title) + '</h2>' +
    '<div class="detail-meta">' +
    '<div class="meta-item">' + sevBadge(b.severity) + '</div>' +
    '<div class="meta-item">' + badgeFor(b.status) + '</div>' +
    '<div class="meta-item">Module: <strong>' + esc(b.module_name || '—') + '</strong></div>' +
    '<div class="meta-item">First seen: <strong>' + formatDate(b.first_seen_at) + '</strong></div>' +
    (b.resolved_at ? '<div class="meta-item">Resolved: <strong>' + formatDate(b.resolved_at) + '</strong></div>' : '') +
    '</div></div>';

  if (b.description) {
    html += '<div class="card card-shadow" style="margin-bottom:16px;"><div style="font-size:13px;font-weight:600;margin-bottom:6px;">Description</div>' +
      '<div style="font-size:13px;line-height:1.5;">' + esc(b.description) + '</div></div>';
  }

  html += '<div class="card card-shadow"><div style="font-size:13px;font-weight:600;margin-bottom:10px;">Occurrences (' + b.occurrences.length + ')</div>';
  if (b.occurrences.length === 0) {
    html += '<div style="font-size:13px;color:var(--text-muted)">No linked test runs.</div>';
  } else {
    html += '<table><thead><tr><th>Run</th><th>Test</th><th>Status</th><th>Notes</th><th>Date</th></tr></thead><tbody>';
    b.occurrences.forEach(o => {
      html += '<tr class="clickable" onclick="navigate(\'run-detail\',' + o.run_id + ')">' +
        '<td><strong>#' + o.run_id + '</strong> ' + esc(o.run_name || '') + '</td>' +
        '<td style="font-size:12px">' + esc(o.test_name) + '</td>' +
        '<td>' + badgeFor(o.status) + '</td>' +
        '<td style="font-size:12px">' + esc(o.notes || '—') + '</td>' +
        '<td style="font-size:12px;color:var(--text-secondary)">' + formatDate(o.created_at) + '</td></tr>';
    });
    html += '</tbody></table>';
  }
  html += '</div>';

  document.getElementById('bug-detail-content').innerHTML = html;
}

// ── Modules ────────────────────────────────────────────────
async function loadModules() {
  const [modules, workflows] = await Promise.all([
    api('/api/modules'),
    api('/api/workflows')
  ]);

  const container = document.getElementById('modules-grid');
  if (modules.length === 0) {
    container.innerHTML = emptyState('No modules', 'Run init_db.py to seed modules.');
  } else {
    let html = '';
    modules.forEach(m => {
      html += '<div class="card card-shadow module-card">' +
        '<div class="module-name">' + esc(m.name) + '</div>' +
        '<div class="module-key">' + esc(m.key) + '</div>' +
        '<div class="module-desc">' + esc(m.description || '') + '</div>' +
        '<div class="module-stats">' +
        '<div class="module-stat"><span style="color:var(--accent);font-weight:700;">' + (m.test_count||0) + '</span> tests</div>' +
        '<div class="module-stat"><span style="color:' + (m.open_bug_count > 0 ? 'var(--fail)' : 'var(--pass)') + ';font-weight:700;">' + (m.open_bug_count||0) + '</span> open bugs</div>' +
        '</div></div>';
    });
    container.innerHTML = html;
  }

  const wfContainer = document.getElementById('workflows-list');
  if (workflows.length === 0) {
    wfContainer.innerHTML = emptyState('No workflows', 'No inter-module workflows defined.');
  } else {
    let html = '';
    workflows.forEach(wf => {
      html += '<div class="card card-shadow workflow-card">' +
        '<div class="wf-name">' + esc(wf.name) + '</div>' +
        '<div class="wf-desc">' + esc(wf.description || '') + '</div>' +
        '<div class="wf-modules">' +
        wf.modules.map(m => '<span class="wf-module-pill">' + esc(m.name) + '</span>').join('') +
        '</div></div>';
    });
    wfContainer.innerHTML = html;
  }
}

// ── Init ───────────────────────────────────────────────────
function handleHash() {
  const hash = window.location.hash.replace('#', '') || 'dashboard';
  const parts = hash.split('/');
  const view = parts[0];
  const id = parts[1] ? parseInt(parts[1]) : undefined;
  navigate(view, id);
}

window.addEventListener('hashchange', handleHash);
window.addEventListener('load', handleHash);

// Close modal on overlay click
document.getElementById('test-modal').addEventListener('click', function(e) {
  if (e.target === this) closeTestModal();
});

// Close modal on Escape
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') closeTestModal();
});
</script>
</body>
</html>"""


# ─── HTTP Server ────────────────────────────────────────────────────────────────

class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Quieter logging
        pass

    def send_html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def send_404(self, msg="Not found"):
        self.send_json({"error": msg}, 404)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        return json.loads(body) if body else {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = urllib.parse.parse_qs(parsed.query)

        if path == "" or path == "/":
            self.send_html(HTML)
        elif path == "/api/summary":
            self.send_json(api_summary())
        elif path == "/api/tests":
            self.send_json(api_tests(params))
        elif path.startswith("/api/tests/"):
            try:
                tid = int(path.split("/")[-1])
            except ValueError:
                return self.send_404()
            result = api_test_detail(tid)
            if result is None:
                return self.send_404("Test not found")
            self.send_json(result)
        elif path == "/api/runs":
            self.send_json(api_runs(params))
        elif path.startswith("/api/runs/"):
            try:
                rid = int(path.split("/")[-1])
            except ValueError:
                return self.send_404()
            result = api_run_detail(rid)
            if result is None:
                return self.send_404("Run not found")
            self.send_json(result)
        elif path == "/api/bugs":
            self.send_json(api_bugs(params))
        elif path.startswith("/api/bugs/"):
            try:
                bid = int(path.split("/")[-1])
            except ValueError:
                return self.send_404()
            result = api_bug_detail(bid)
            if result is None:
                return self.send_404("Bug not found")
            self.send_json(result)
        elif path == "/api/modules":
            self.send_json(api_modules())
        elif path == "/api/workflows":
            self.send_json(api_workflows())
        else:
            self.send_404()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        data = self.read_body()

        if path == "/api/tests":
            result = api_create_test(data)
            if isinstance(result, tuple):
                self.send_json(result[0], result[1])
            else:
                self.send_json(result, 201)
        else:
            self.send_404()

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        data = self.read_body()

        if path.startswith("/api/tests/"):
            try:
                tid = int(path.split("/")[-1])
            except ValueError:
                return self.send_404()
            result = api_update_test(tid, data)
            if isinstance(result, tuple):
                self.send_json(result[0], result[1])
            else:
                self.send_json(result)
        else:
            self.send_404()

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path.startswith("/api/tests/"):
            try:
                tid = int(path.split("/")[-1])
            except ValueError:
                return self.send_404()
            result = api_delete_test(tid)
            if isinstance(result, tuple):
                self.send_json(result[0], result[1])
            else:
                self.send_json(result)
        else:
            self.send_404()


# ─── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        print("Run 'python3 init_db.py' first to initialize the database.")
        sys.exit(1)

    server = http.server.HTTPServer(("127.0.0.1", PORT), DashboardHandler)
    print(f"HB QA Dashboard running at http://localhost:{PORT}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()
