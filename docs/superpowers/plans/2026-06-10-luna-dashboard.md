# Luna Admin Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the bare-bones inline-HTML admin web UI with a polished Luna-branded dark dashboard (dark navy + teal, sidebar nav, stat cards, table with toggles and modals).

**Architecture:** Add `aiohttp-jinja2` rendering to the existing `bot/web/admin_app.py` backend. Create Jinja2 templates in `bot/web/templates/` and static assets in `bot/web/static/`. All existing API endpoints stay unchanged; only page handlers are updated to call `aiohttp_jinja2.render_template`.

**Tech Stack:** Python/aiohttp, aiohttp-jinja2, Jinja2, vanilla CSS (custom properties), vanilla JS (no framework or CDN).

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `requirements.txt` | Add aiohttp-jinja2, jinja2 |
| Modify | `bot/web/admin_app.py` | Template setup, new routes, updated handlers |
| Create | `bot/web/templates/base.html` | Sidebar shell shared by all auth pages |
| Create | `bot/web/templates/login.html` | Standalone login card |
| Create | `bot/web/templates/dashboard.html` | Stat cards + system info |
| Create | `bot/web/templates/pairs.html` | Searchable pair table |
| Create | `bot/web/templates/pair_form.html` | Create/edit pair (shared) |
| Create | `bot/web/templates/backups.html` | Backup list + trigger |
| Create | `bot/web/static/luna.css` | Full dark-navy/teal theme |
| Create | `bot/web/static/luna.js` | Delete modal, enable toggle, backup trigger |
| Modify | `tests/test_admin_web.py` | Tests for new routes and /api/stats |

---

## Task 1: Add aiohttp-jinja2 + wire template/static infrastructure

**Files:**
- Modify: `requirements.txt`
- Modify: `bot/web/admin_app.py`

- [ ] **Step 1: Add dependencies to requirements.txt**

Replace the existing requirements.txt content:

```
python-telegram-bot[rate-limiter]==21.6
PyYAML==6.0.2
python-dotenv==1.0.1
aiohttp==3.11.11
aiohttp-jinja2==1.6
jinja2==3.1.4
pytest==8.3.3
pytest-asyncio==0.24.0
```

- [ ] **Step 2: Install the new dependencies**

```bash
pip install aiohttp-jinja2==1.6 jinja2==3.1.4
```

Expected: installation completes without errors.

- [ ] **Step 3: Create the templates and static directories**

```bash
mkdir -p bot/web/templates bot/web/static
```

- [ ] **Step 4: Add template loader and static route to create_admin_app**

In `bot/web/admin_app.py`, add these imports at the top:

```python
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import aiohttp_jinja2
import jinja2
from aiohttp import web

from bot.storage.auth_store import AuthStore, verify_password
from bot.storage.backup_ops import create_backup
from bot.storage.config_store import PairFilters, PairRecord, SQLiteConfigStore
```

Add a new app key after the existing ones:

```python
SESSION_COOKIE = "admin_session"
DB_PATH_KEY: web.AppKey[str] = web.AppKey("db_path")
CONFIG_STORE_KEY: web.AppKey[SQLiteConfigStore] = web.AppKey("config_store")
AUTH_STORE_KEY: web.AppKey[AuthStore] = web.AppKey("auth_store")
BACKUP_DIR_KEY: web.AppKey[str] = web.AppKey("backup_dir")
BACKUP_RETENTION_DAYS_KEY: web.AppKey[int] = web.AppKey("backup_retention_days")
STATS_PATH_KEY: web.AppKey[str] = web.AppKey("stats_path")
```

Update `create_admin_app` signature and body to wire up jinja2, static files, and the new key:

```python
def create_admin_app(
    *,
    db_path: str,
    config_store: SQLiteConfigStore,
    auth_store: AuthStore,
    backup_dir: str = "backups",
    backup_retention_days: int = 30,
    stats_path: str = "data/stats.json",
) -> web.Application:
    app = web.Application(middlewares=[auth_middleware])
    app[DB_PATH_KEY] = db_path
    app[CONFIG_STORE_KEY] = config_store
    app[AUTH_STORE_KEY] = auth_store
    app[BACKUP_DIR_KEY] = backup_dir
    app[BACKUP_RETENTION_DAYS_KEY] = backup_retention_days
    app[STATS_PATH_KEY] = stats_path

    _templates_dir = Path(__file__).parent / "templates"
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(str(_templates_dir)))

    _static_dir = Path(__file__).parent / "static"
    app.router.add_static("/static/", path=str(_static_dir), name="static")

    app.router.add_get("/", index_handler)
    app.router.add_get("/login", login_page)
    app.router.add_post("/api/login", api_login)
    app.router.add_post("/api/logout", api_logout)
    app.router.add_get("/pairs", pairs_page)
    app.router.add_get("/pairs/new", pair_create_page)
    app.router.add_post("/pairs/new", pair_create_submit)
    app.router.add_get("/pairs/{name}/edit", pair_edit_page)
    app.router.add_post("/pairs/{name}/edit", pair_edit_submit)
    app.router.add_post("/pairs/{name}/delete", pair_delete_submit)
    app.router.add_get("/api/pairs", api_list_pairs)
    app.router.add_post("/api/pairs", api_create_pair)
    app.router.add_put("/api/pairs/{name}", api_update_pair)
    app.router.add_delete("/api/pairs/{name}", api_delete_pair)
    app.router.add_post("/api/backup", api_backup_now)
    return app
```

- [ ] **Step 5: Verify existing tests still pass**

```bash
pytest tests/test_admin_web.py -v
```

Expected: all 4 existing tests PASS (no template rendering yet, just infrastructure wired).

- [ ] **Step 6: Commit**

```bash
git add requirements.txt bot/web/admin_app.py bot/web/templates/.gitkeep bot/web/static/.gitkeep
git commit -m "feat: add aiohttp-jinja2 dependency and wire template/static infrastructure"
```

---

## Task 2: Add /api/stats endpoint

**Files:**
- Modify: `bot/web/admin_app.py`
- Modify: `tests/test_admin_web.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_admin_web.py` (after the existing `_make_client` helper, update it first):

```python
async def _make_client(tmp_path: Path) -> tuple[TestClient, str]:
    db_path = str(tmp_path / "forwarder.db")
    initialize_database(db_path)
    config_store = SQLiteConfigStore(db_path)
    auth_store = AuthStore(db_path)
    auth_store.ensure_admin_user("admin", "secret")
    app = create_admin_app(
        db_path=db_path,
        config_store=config_store,
        auth_store=auth_store,
        backup_dir=str(tmp_path / "backups"),
        backup_retention_days=30,
        stats_path=str(tmp_path / "stats.json"),
    )
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    return client, db_path
```

Then add the test:

```python
@pytest.mark.asyncio
async def test_api_stats_returns_aggregated_counts(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        await _login(client)

        stats_file = tmp_path / "stats.json"
        stats_file.write_text(json.dumps({
            "pair-a": {"date": "2026-06-10", "week_key": "2026-W24", "today": 5, "week": 20},
            "pair-b": {"date": "2026-06-10", "week_key": "2026-W24", "today": 3, "week": 15},
        }))

        resp = await client.get("/api/stats")
        assert resp.status == 200
        data = await resp.json()
        assert data["today"] == 8
        assert data["week"] == 35
        assert "pairs_total" in data
        assert "pairs_active" in data
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_api_stats_returns_zeros_when_no_stats_file(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        await _login(client)
        resp = await client.get("/api/stats")
        assert resp.status == 200
        data = await resp.json()
        assert data["today"] == 0
        assert data["week"] == 0
    finally:
        await client.close()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_admin_web.py::test_api_stats_returns_aggregated_counts tests/test_admin_web.py::test_api_stats_returns_zeros_when_no_stats_file -v
```

Expected: FAIL — `/api/stats` route doesn't exist yet.

- [ ] **Step 3: Implement api_stats handler**

Add this function to `bot/web/admin_app.py` (after `api_backup_now`):

```python
async def api_stats(request: web.Request) -> web.Response:
    stats_path = request.app[STATS_PATH_KEY]
    try:
        with open(stats_path) as f:
            raw: dict = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        raw = {}

    today = sum(v.get("today", 0) for v in raw.values())
    week = sum(v.get("week", 0) for v in raw.values())

    store = request.app[CONFIG_STORE_KEY]
    pairs = store.list_pairs()
    pairs_total = len(pairs)
    pairs_active = sum(1 for p in pairs if p.enabled)

    return web.json_response({
        "today": today,
        "week": week,
        "pairs_total": pairs_total,
        "pairs_active": pairs_active,
    })
```

Register it in `create_admin_app` (add before the `return app` line):

```python
    app.router.add_get("/api/stats", api_stats)
```

Also update `auth_middleware` to protect `/api/stats` (already covered by the `/api` prefix check — no change needed).

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_admin_web.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/web/admin_app.py tests/test_admin_web.py
git commit -m "feat: add GET /api/stats endpoint for dashboard aggregated counts"
```

---

## Task 3: Create luna.css

**Files:**
- Create: `bot/web/static/luna.css`

No unit tests for CSS. Visual correctness is verified when the dashboard pages are rendered in Task 5+.

- [ ] **Step 1: Create bot/web/static/luna.css with the full theme**

```css
:root {
  --bg: #0f172a;
  --surface: #1e293b;
  --border: #334155;
  --accent: #06b6d4;
  --accent-hover: #0891b2;
  --text: #f1f5f9;
  --text-muted: #94a3b8;
  --success: #10b981;
  --danger: #ef4444;
  --sidebar-width: 240px;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 14px;
  display: flex;
  min-height: 100vh;
}

/* ── Sidebar ── */
.sidebar {
  width: var(--sidebar-width);
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  position: fixed;
  top: 0; left: 0; bottom: 0;
  z-index: 100;
}

.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 24px 20px;
  border-bottom: 1px solid var(--border);
}

.sidebar-logo span {
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.5px;
}

.sidebar-nav {
  list-style: none;
  padding: 16px 0;
  flex: 1;
}

.sidebar-nav a {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 20px;
  color: var(--text-muted);
  text-decoration: none;
  font-size: 14px;
  transition: color 0.15s, background 0.15s;
  border-left: 3px solid transparent;
}

.sidebar-nav a:hover {
  color: var(--text);
  background: rgba(255,255,255,0.04);
}

.sidebar-nav a.active {
  color: var(--accent);
  border-left-color: var(--accent);
  background: rgba(6,182,212,0.08);
}

/* ── Main wrapper ── */
.main-wrapper {
  margin-left: var(--sidebar-width);
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

/* ── Topbar ── */
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 32px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  position: sticky;
  top: 0;
  z-index: 50;
}

.page-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text);
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.username {
  color: var(--text-muted);
  font-size: 13px;
}

/* ── Content area ── */
.content {
  padding: 32px;
  max-width: 1200px;
  width: 100%;
}

/* ── Cards ── */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 24px;
}

.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-top: 3px solid var(--accent);
  border-radius: 8px;
  padding: 20px 24px;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  color: var(--text);
  line-height: 1;
  margin-bottom: 6px;
}

.stat-label {
  font-size: 12px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 32px;
}

/* ── Badges ── */
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.badge-success {
  background: rgba(16,185,129,0.15);
  color: var(--success);
}

.badge-danger {
  background: rgba(239,68,68,0.15);
  color: var(--danger);
}

/* ── Buttons ── */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  text-decoration: none;
  transition: background 0.15s, color 0.15s;
  white-space: nowrap;
}

.btn-primary { background: var(--accent); color: #fff; }
.btn-primary:hover { background: var(--accent-hover); }

.btn-danger { background: var(--danger); color: #fff; }
.btn-danger:hover { background: #dc2626; }

.btn-ghost {
  background: transparent;
  color: var(--text-muted);
  border: 1px solid var(--border);
}
.btn-ghost:hover { color: var(--text); border-color: var(--text-muted); }

.btn-sm { padding: 4px 10px; font-size: 12px; }

/* ── Table ── */
.table-wrapper {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

table { width: 100%; border-collapse: collapse; }

thead th {
  text-align: left;
  padding: 12px 16px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border);
  background: rgba(255,255,255,0.02);
}

tbody tr {
  border-bottom: 1px solid var(--border);
  transition: background 0.1s;
}
tbody tr:last-child { border-bottom: none; }
tbody tr:hover { background: rgba(6,182,212,0.04); }

tbody td { padding: 12px 16px; color: var(--text); font-size: 13px; }

.td-muted {
  color: var(--text-muted);
  font-size: 12px;
  font-family: 'SF Mono', 'Fira Code', monospace;
}

.td-actions { display: flex; gap: 8px; align-items: center; }

/* ── Forms ── */
.form-group { margin-bottom: 20px; }

.form-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}

.form-input, .form-textarea {
  width: 100%;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 9px 12px;
  color: var(--text);
  font-size: 13px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s;
}

.form-input:focus, .form-textarea:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(6,182,212,0.2);
}

.form-textarea { resize: vertical; min-height: 80px; }
.form-hint { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
.form-error { font-size: 12px; color: var(--danger); margin-top: 4px; }

/* ── Checkbox group ── */
.checkbox-group { display: flex; flex-wrap: wrap; gap: 8px; }

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-muted);
}

.checkbox-item input[type="checkbox"] {
  width: 14px; height: 14px;
  accent-color: var(--accent);
  cursor: pointer;
}

/* ── Toggle switch ── */
.toggle-wrapper { display: flex; align-items: center; gap: 10px; }

.toggle { position: relative; width: 36px; height: 20px; display: inline-block; }
.toggle input { opacity: 0; width: 0; height: 0; }

.toggle-track {
  position: absolute;
  inset: 0;
  background: var(--border);
  border-radius: 9999px;
  cursor: pointer;
  transition: background 0.2s;
}

.toggle input:checked + .toggle-track { background: var(--accent); }

.toggle-track::after {
  content: '';
  position: absolute;
  width: 14px; height: 14px;
  background: #fff;
  border-radius: 50%;
  top: 3px; left: 3px;
  transition: transform 0.2s;
}

.toggle input:checked + .toggle-track::after { transform: translateX(16px); }

/* ── Filter / page header ── */
.filter-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }

.search-input {
  flex: 1; max-width: 300px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 12px;
  color: var(--text);
  font-size: 13px;
  outline: none;
}
.search-input:focus { border-color: var(--accent); }

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.section-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}

/* ── System info grid ── */
.system-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.system-item {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}

.system-label {
  font-size: 11px;
  text-transform: uppercase;
  color: var(--text-muted);
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}

.system-value { font-size: 14px; font-weight: 600; }

/* ── Alerts ── */
.alert {
  padding: 12px 16px;
  border-radius: 6px;
  font-size: 13px;
  margin-bottom: 20px;
}

.alert-error {
  background: rgba(239,68,68,0.1);
  border: 1px solid rgba(239,68,68,0.3);
  color: var(--danger);
}

.alert-success {
  background: rgba(16,185,129,0.1);
  border: 1px solid rgba(16,185,129,0.3);
  color: var(--success);
}

/* ── Modal ── */
.modal-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  z-index: 200;
  align-items: center;
  justify-content: center;
}
.modal-overlay.open { display: flex; }

.modal {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 28px;
  max-width: 420px;
  width: 90%;
}

.modal h3 { font-size: 16px; font-weight: 600; margin-bottom: 10px; }
.modal p { color: var(--text-muted); font-size: 13px; margin-bottom: 24px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; }

/* ── Empty state ── */
.empty-state {
  text-align: center;
  padding: 48px 24px;
  color: var(--text-muted);
}
.empty-state p { margin-bottom: 16px; }

/* ── Login page ── */
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
}

.login-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 40px;
  width: 100%;
  max-width: 380px;
}

.login-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  justify-content: center;
}
.login-logo span { font-size: 24px; font-weight: 700; }

.login-subtitle {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  margin-bottom: 28px;
}

/* ── Misc ── */
form.inline { display: inline; }
.file-size { color: var(--text-muted); font-size: 12px; }

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

- [ ] **Step 2: Commit**

```bash
git add bot/web/static/luna.css
git commit -m "feat: add Luna dark-navy/teal CSS theme"
```

---

## Task 4: Create base.html + login.html + POST /login handler

**Files:**
- Create: `bot/web/templates/base.html`
- Create: `bot/web/templates/login.html`
- Modify: `bot/web/admin_app.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_admin_web.py`:

```python
@pytest.mark.asyncio
async def test_login_page_renders_html(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        resp = await client.get("/login")
        assert resp.status == 200
        assert "text/html" in resp.content_type
        body = await resp.text()
        assert "Luna" in body
        assert "Sign in" in body
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_post_login_valid_credentials_redirects(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        resp = await client.post(
            "/login",
            data={"username": "admin", "password": "secret"},
            allow_redirects=False,
        )
        assert resp.status == 302
        assert resp.headers["Location"] == "/dashboard"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_post_login_invalid_credentials_shows_error(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        resp = await client.post(
            "/login",
            data={"username": "admin", "password": "wrong"},
        )
        assert resp.status == 200
        body = await resp.text()
        assert "Invalid" in body
    finally:
        await client.close()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_admin_web.py::test_login_page_renders_html tests/test_admin_web.py::test_post_login_valid_credentials_redirects tests/test_admin_web.py::test_post_login_invalid_credentials_shows_error -v
```

Expected: FAIL — templates don't exist yet, `POST /login` route doesn't exist.

- [ ] **Step 3: Create bot/web/templates/base.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{% block title %}Luna{% endblock %} — Luna Admin</title>
  <link rel="stylesheet" href="/static/luna.css" />
</head>
<body>
  <nav class="sidebar">
    <div class="sidebar-logo">
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M14 2C7.373 2 2 7.373 2 14s5.373 12 12 12c1.354 0 2.658-.225 3.875-.637C14.13 23.88 11 19.35 11 14c0-5.35 3.13-9.88 6.875-11.363A11.956 11.956 0 0014 2z" fill="#06b6d4"/>
      </svg>
      <span>Luna</span>
    </div>
    <ul class="sidebar-nav">
      <li>
        <a href="/dashboard" class="{% if active_page == 'dashboard' %}active{% endif %}">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
            <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
          </svg>
          Dashboard
        </a>
      </li>
      <li>
        <a href="/pairs" class="{% if active_page == 'pairs' %}active{% endif %}">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 014-4h14"/>
            <path d="M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 01-4 4H3"/>
          </svg>
          Pairs
        </a>
      </li>
      <li>
        <a href="/backups" class="{% if active_page == 'backups' %}active{% endif %}">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          Backups
        </a>
      </li>
    </ul>
  </nav>

  <div class="main-wrapper">
    <header class="topbar">
      <h1 class="page-title">{% block page_title %}{% endblock %}</h1>
      <div class="topbar-right">
        <span class="username">{{ user.username }}</span>
        <form method="post" action="/api/logout" class="inline">
          <button type="submit" class="btn btn-ghost btn-sm">Logout</button>
        </form>
      </div>
    </header>
    <main class="content">
      {% block content %}{% endblock %}
    </main>
  </div>

  <script src="/static/luna.js"></script>
</body>
</html>
```

- [ ] **Step 4: Create bot/web/templates/login.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Login — Luna Admin</title>
  <link rel="stylesheet" href="/static/luna.css" />
</head>
<body class="login-page">
  <div class="login-card">
    <div class="login-logo">
      <svg width="32" height="32" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M14 2C7.373 2 2 7.373 2 14s5.373 12 12 12c1.354 0 2.658-.225 3.875-.637C14.13 23.88 11 19.35 11 14c0-5.35 3.13-9.88 6.875-11.363A11.956 11.956 0 0014 2z" fill="#06b6d4"/>
      </svg>
      <span>Luna</span>
    </div>
    <p class="login-subtitle">Admin Dashboard</p>

    {% if error %}
    <div class="alert alert-error">{{ error }}</div>
    {% endif %}

    <form method="post" action="/login">
      <div class="form-group">
        <label class="form-label" for="username">Username</label>
        <input class="form-input" type="text" id="username" name="username"
               autocomplete="username" autofocus required />
      </div>
      <div class="form-group">
        <label class="form-label" for="password">Password</label>
        <input class="form-input" type="password" id="password" name="password"
               autocomplete="current-password" required />
      </div>
      <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center;">
        Sign in
      </button>
    </form>
  </div>
</body>
</html>
```

- [ ] **Step 5: Add post_login handler and update login_page in admin_app.py**

Replace the existing `login_page` function and add `post_login` right after it:

```python
async def login_page(request: web.Request) -> web.Response:
    return aiohttp_jinja2.render_template("login.html", request, {"error": None})


async def post_login(request: web.Request) -> web.StreamResponse:
    auth_store = request.app[AUTH_STORE_KEY]
    form = await request.post()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))

    user = auth_store.get_user_by_username(username)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return aiohttp_jinja2.render_template(
            "login.html", request, {"error": "Invalid username or password"}
        )

    session_id = auth_store.create_session(user.id)
    response = web.HTTPFound("/dashboard")
    response.set_cookie(SESSION_COOKIE, session_id, httponly=True, samesite="Lax")
    return response
```

Register the new route in `create_admin_app` (add after `app.router.add_get("/login", login_page)`):

```python
    app.router.add_post("/login", post_login)
```

Also add `"/login"` POST to public paths in auth_middleware — it's already covered since `public_paths = {"/login", "/api/login"}` matches both GET and POST on `/login`. No change needed.

- [ ] **Step 6: Run tests to confirm they pass**

```bash
pytest tests/test_admin_web.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add bot/web/templates/base.html bot/web/templates/login.html bot/web/admin_app.py tests/test_admin_web.py
git commit -m "feat: add Luna login page template and POST /login form handler"
```

---

## Task 5: Create dashboard.html + /dashboard route + update auth middleware

**Files:**
- Create: `bot/web/templates/dashboard.html`
- Modify: `bot/web/admin_app.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_admin_web.py`:

```python
@pytest.mark.asyncio
async def test_dashboard_page_renders_html(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        await _login(client)
        resp = await client.get("/dashboard")
        assert resp.status == 200
        assert "text/html" in resp.content_type
        body = await resp.text()
        assert "Dashboard" in body
        assert "Total Pairs" in body
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_dashboard_requires_auth(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        resp = await client.get("/dashboard", allow_redirects=False)
        assert resp.status == 302
        assert resp.headers["Location"] == "/login"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_index_redirects_to_dashboard(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        await _login(client)
        resp = await client.get("/", allow_redirects=False)
        assert resp.status == 302
        assert resp.headers["Location"] == "/dashboard"
    finally:
        await client.close()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_admin_web.py::test_dashboard_page_renders_html tests/test_admin_web.py::test_dashboard_requires_auth tests/test_admin_web.py::test_index_redirects_to_dashboard -v
```

Expected: FAIL.

- [ ] **Step 3: Add helper functions to admin_app.py**

Add these two helpers after the `_split_csv` function:

```python
def _get_last_backup(backup_dir: str) -> str | None:
    p = Path(backup_dir)
    if not p.exists():
        return None
    files = sorted(p.glob("*.db"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        return None
    return datetime.fromtimestamp(files[0].stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def _list_backups(backup_dir: str) -> list[dict]:
    p = Path(backup_dir)
    if not p.exists():
        return []
    result = []
    for f in sorted(p.glob("*.db"), key=lambda f: f.stat().st_mtime, reverse=True):
        size = f.stat().st_size
        if size < 1024:
            size_str = f"{size} B"
        elif size < 1024 * 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        result.append({
            "name": f.name,
            "size": size_str,
            "created_at": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return result
```

- [ ] **Step 4: Update auth_middleware and index_handler**

Replace the existing `auth_middleware` with:

```python
@web.middleware
async def auth_middleware(request: web.Request, handler):
    public_paths = {"/login", "/api/login"}
    if request.path in public_paths:
        return await handler(request)

    is_protected = (
        request.path.startswith("/pairs")
        or request.path.startswith("/api")
        or request.path in {"/dashboard", "/backups"}
    )
    if not is_protected:
        return await handler(request)

    auth_store = request.app[AUTH_STORE_KEY]
    session_id = request.cookies.get(SESSION_COOKIE)
    user = auth_store.get_user_by_session(session_id) if session_id else None
    if user is None:
        if request.path.startswith("/api"):
            return web.json_response({"error": "unauthorized"}, status=401)
        raise web.HTTPFound("/login")

    request["user"] = user
    return await handler(request)
```

Replace the existing `index_handler` with:

```python
async def index_handler(_: web.Request) -> web.StreamResponse:
    raise web.HTTPFound("/dashboard")
```

- [ ] **Step 5: Add dashboard_page handler**

Add this function after `index_handler`:

```python
async def dashboard_page(request: web.Request) -> web.Response:
    stats_path = request.app[STATS_PATH_KEY]
    try:
        with open(stats_path) as f:
            raw: dict = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        raw = {}

    store = request.app[CONFIG_STORE_KEY]
    pairs = store.list_pairs()
    backup_dir = request.app[BACKUP_DIR_KEY]

    return aiohttp_jinja2.render_template("dashboard.html", request, {
        "active_page": "dashboard",
        "user": request["user"],
        "today": sum(v.get("today", 0) for v in raw.values()),
        "week": sum(v.get("week", 0) for v in raw.values()),
        "pairs_total": len(pairs),
        "pairs_active": sum(1 for p in pairs if p.enabled),
        "last_backup": _get_last_backup(backup_dir),
    })
```

Register the route in `create_admin_app` (add after the `/` route):

```python
    app.router.add_get("/dashboard", dashboard_page)
```

- [ ] **Step 6: Create bot/web/templates/dashboard.html**

```html
{% extends "base.html" %}
{% block title %}Dashboard{% endblock %}
{% block page_title %}Dashboard{% endblock %}

{% block content %}
<div class="stats-grid">
  <div class="stat-card">
    <div class="stat-value">{{ pairs_total }}</div>
    <div class="stat-label">Total Pairs</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">{{ pairs_active }}</div>
    <div class="stat-label">Active Pairs</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">{{ today }}</div>
    <div class="stat-label">Messages Today</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">{{ week }}</div>
    <div class="stat-label">Messages This Week</div>
  </div>
</div>

<div class="section-title">System</div>
<div class="system-grid">
  <div class="system-item">
    <div class="system-label">Storage</div>
    <div class="system-value"><span class="badge badge-success">DB Mode</span></div>
  </div>
  <div class="system-item">
    <div class="system-label">Last Backup</div>
    <div class="system-value">{{ last_backup or "Never" }}</div>
  </div>
  <div class="system-item">
    <div class="system-label">Status</div>
    <div class="system-value"><span class="badge badge-success">Running</span></div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 7: Run tests to confirm they pass**

```bash
pytest tests/test_admin_web.py -v
```

Expected: all 12 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add bot/web/templates/dashboard.html bot/web/admin_app.py tests/test_admin_web.py
git commit -m "feat: add Luna dashboard page with stat cards and system info"
```

---

## Task 6: Create pairs.html + update pairs_page handler

**Files:**
- Create: `bot/web/templates/pairs.html`
- Modify: `bot/web/admin_app.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_admin_web.py`:

```python
@pytest.mark.asyncio
async def test_pairs_page_renders_pairs(tmp_path):
    client, db_path = await _make_client(tmp_path)
    try:
        await _login(client)
        store = SQLiteConfigStore(db_path)
        store.create_pair(PairRecord(
            id=None, name="test-pair",
            group_a_chat_id=-100111, group_b_chat_id=-100222,
            bidirectional=True, enabled=True,
            filters=PairFilters(types_allow=["text"], keywords_block=[], keywords_allow=[]),
        ))

        resp = await client.get("/pairs")
        assert resp.status == 200
        assert "text/html" in resp.content_type
        body = await resp.text()
        assert "test-pair" in body
        assert "Pairs" in body
    finally:
        await client.close()
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/test_admin_web.py::test_pairs_page_renders_pairs -v
```

Expected: FAIL (pairs_page returns inline HTML that doesn't use the template yet — this test checks for the template's "Pairs" heading structure).

- [ ] **Step 3: Create bot/web/templates/pairs.html**

```html
{% extends "base.html" %}
{% block title %}Pairs{% endblock %}
{% block page_title %}Pairs{% endblock %}

{% block content %}
<div class="page-header">
  <form method="get" action="/pairs" class="filter-bar">
    <input class="search-input" name="q" placeholder="Search by name…" value="{{ q or '' }}" />
    <button type="submit" class="btn btn-ghost btn-sm">Search</button>
    {% if q %}<a href="/pairs" class="btn btn-ghost btn-sm">Clear</a>{% endif %}
  </form>
  <a href="/pairs/new" class="btn btn-primary">+ New Pair</a>
</div>

<div class="table-wrapper">
  <table>
    <thead>
      <tr>
        <th>Name</th>
        <th>Group A</th>
        <th>Group B</th>
        <th>Direction</th>
        <th>Status</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody>
      {% for pair in pairs %}
      <tr data-pair="{{ pair.name }}">
        <td><strong>{{ pair.name }}</strong></td>
        <td class="td-muted">{{ pair.group_a_chat_id }}</td>
        <td class="td-muted">{{ pair.group_b_chat_id }}</td>
        <td>
          {% if pair.bidirectional %}
            <span style="color:var(--accent)">⇄ Bidirectional</span>
          {% else %}
            <span style="color:var(--text-muted)">→ One-way</span>
          {% endif %}
        </td>
        <td>
          <span class="badge {% if pair.enabled %}badge-success{% else %}badge-danger{% endif %}"
                data-enabled-badge="{{ pair.name }}">
            {% if pair.enabled %}Enabled{% else %}Disabled{% endif %}
          </span>
        </td>
        <td>
          <div class="td-actions">
            <label class="toggle" title="Toggle enabled">
              <input type="checkbox" {% if pair.enabled %}checked{% endif %}
                     onchange="togglePairEnabled('{{ pair.name }}', this)" />
              <span class="toggle-track"></span>
            </label>
            <a href="/pairs/{{ pair.name }}/edit" class="btn btn-ghost btn-sm">Edit</a>
            <button class="btn btn-danger btn-sm"
                    onclick="openDeleteModal('{{ pair.name }}')">Delete</button>
          </div>
        </td>
      </tr>
      {% else %}
      <tr>
        <td colspan="6">
          <div class="empty-state">
            <p>No pairs configured yet.</p>
            <a href="/pairs/new" class="btn btn-primary">Create your first pair</a>
          </div>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<!-- Delete confirmation modal -->
<div id="delete-modal" class="modal-overlay">
  <div class="modal">
    <h3>Delete pair?</h3>
    <p>Are you sure you want to delete <strong id="modal-pair-name"></strong>?
       This action cannot be undone.</p>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeDeleteModal()">Cancel</button>
      <button id="modal-confirm" class="btn btn-danger">Delete</button>
    </div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 4: Update pairs_page in admin_app.py**

Replace the existing `pairs_page` function with:

```python
async def pairs_page(request: web.Request) -> web.Response:
    store = request.app[CONFIG_STORE_KEY]
    q = request.query.get("q")
    chat_raw = request.query.get("chat_id")
    chat_id = int(chat_raw) if chat_raw else None
    enabled_raw = request.query.get("enabled")
    bidir_raw = request.query.get("bidirectional")
    enabled = None if enabled_raw is None or enabled_raw == "" else _to_bool(enabled_raw)
    bidirectional = None if bidir_raw is None or bidir_raw == "" else _to_bool(bidir_raw)
    pairs = store.list_pairs(
        name_query=q,
        chat_id=chat_id,
        enabled=enabled,
        bidirectional=bidirectional,
    )
    return aiohttp_jinja2.render_template("pairs.html", request, {
        "active_page": "pairs",
        "user": request["user"],
        "pairs": pairs,
        "q": q,
    })
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_admin_web.py -v
```

Expected: all 13 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add bot/web/templates/pairs.html bot/web/admin_app.py tests/test_admin_web.py
git commit -m "feat: add Luna pairs page template with table, toggle, and delete modal"
```

---

## Task 7: Create pair_form.html + update form page handlers

**Files:**
- Create: `bot/web/templates/pair_form.html`
- Modify: `bot/web/admin_app.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_admin_web.py`:

```python
@pytest.mark.asyncio
async def test_pair_create_page_renders_form(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        await _login(client)
        resp = await client.get("/pairs/new")
        assert resp.status == 200
        assert "text/html" in resp.content_type
        body = await resp.text()
        assert "New Pair" in body
        assert "Group A Chat ID" in body
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_pair_edit_page_renders_existing_values(tmp_path):
    client, db_path = await _make_client(tmp_path)
    try:
        await _login(client)
        store = SQLiteConfigStore(db_path)
        store.create_pair(PairRecord(
            id=None, name="edit-me",
            group_a_chat_id=-100111, group_b_chat_id=-100222,
            bidirectional=False, enabled=True,
            filters=PairFilters(types_allow=["text"], keywords_block=["spam"], keywords_allow=[]),
        ))

        resp = await client.get("/pairs/edit-me/edit")
        assert resp.status == 200
        body = await resp.text()
        assert "edit-me" in body
        assert "-100111" in body
        assert "spam" in body
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_pair_form_submit_creates_pair_and_redirects(tmp_path):
    client, db_path = await _make_client(tmp_path)
    try:
        await _login(client)
        resp = await client.post(
            "/pairs/new",
            data={
                "name": "form-pair",
                "group_a_chat_id": "-100111",
                "group_b_chat_id": "-100222",
                "bidirectional": "true",
                "enabled": "true",
                "types_allow": ["text", "photo"],
                "keywords_block": "spam, ads",
                "keywords_allow": "",
            },
            allow_redirects=False,
        )
        assert resp.status == 302
        assert resp.headers["Location"] == "/pairs"
        store = SQLiteConfigStore(db_path)
        pair = store.get_pair_by_name("form-pair")
        assert pair is not None
        assert pair.group_a_chat_id == -100111
        assert "photo" in pair.filters.types_allow
        assert "spam" in pair.filters.keywords_block
    finally:
        await client.close()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_admin_web.py::test_pair_create_page_renders_form tests/test_admin_web.py::test_pair_edit_page_renders_existing_values tests/test_admin_web.py::test_pair_form_submit_creates_pair_and_redirects -v
```

Expected: FAIL.

- [ ] **Step 3: Create bot/web/templates/pair_form.html**

```html
{% extends "base.html" %}
{% block title %}{{ "Edit" if pair else "New" }} Pair{% endblock %}
{% block page_title %}{{ "Edit" if pair else "New" }} Pair{% endblock %}

{% block content %}
{% if error %}
<div class="alert alert-error">{{ error }}</div>
{% endif %}

<div class="card" style="max-width:640px">
  <form method="post" action="{{ '/pairs/' + pair.name + '/edit' if pair else '/pairs/new' }}">

    <div class="form-group">
      <label class="form-label" for="name">Pair Name</label>
      <input class="form-input" type="text" id="name" name="name"
             value="{{ pair.name if pair else '' }}"
             {% if pair %}readonly{% endif %}
             placeholder="e.g. customer-internal" required />
      {% if pair %}
        <div class="form-hint">Name cannot be changed after creation.</div>
      {% endif %}
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div class="form-group">
        <label class="form-label" for="group_a_chat_id">Group A Chat ID</label>
        <input class="form-input" type="number" id="group_a_chat_id" name="group_a_chat_id"
               value="{{ pair.group_a_chat_id if pair else '' }}"
               placeholder="-1001234567890" required />
      </div>
      <div class="form-group">
        <label class="form-label" for="group_b_chat_id">Group B Chat ID</label>
        <input class="form-input" type="number" id="group_b_chat_id" name="group_b_chat_id"
               value="{{ pair.group_b_chat_id if pair else '' }}"
               placeholder="-1009876543210" required />
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div class="form-group">
        <label class="form-label">Bidirectional</label>
        <div class="toggle-wrapper">
          <label class="toggle">
            <input type="checkbox" name="bidirectional" value="true"
                   {% if pair is none or pair.bidirectional %}checked{% endif %} />
            <span class="toggle-track"></span>
          </label>
          <span style="font-size:13px;color:var(--text-muted)">Forward both ways</span>
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">Enabled</label>
        <div class="toggle-wrapper">
          <label class="toggle">
            <input type="checkbox" name="enabled" value="true"
                   {% if pair is none or pair.enabled %}checked{% endif %} />
            <span class="toggle-track"></span>
          </label>
          <span style="font-size:13px;color:var(--text-muted)">Active forwarding</span>
        </div>
      </div>
    </div>

    <div class="form-group">
      <label class="form-label">Allowed Message Types</label>
      <div class="checkbox-group">
        {% set allowed_types = pair.filters.types_allow if pair else ["text","photo","video","sticker","document","voice","animation"] %}
        {% for t in ["text","photo","video","sticker","document","voice","animation"] %}
        <label class="checkbox-item">
          <input type="checkbox" name="types_allow" value="{{ t }}"
                 {% if t in allowed_types %}checked{% endif %} />
          {{ t }}
        </label>
        {% endfor %}
      </div>
    </div>

    <div class="form-group">
      <label class="form-label" for="keywords_block">Keywords — Block List</label>
      <textarea class="form-textarea" id="keywords_block" name="keywords_block"
                placeholder="spam, ads, promo">{{ pair.filters.keywords_block | join(", ") if pair else "" }}</textarea>
      <div class="form-hint">Comma-separated. Messages containing these words are blocked.</div>
    </div>

    <div class="form-group">
      <label class="form-label" for="keywords_allow">Keywords — Allow List</label>
      <textarea class="form-textarea" id="keywords_allow" name="keywords_allow"
                placeholder="Leave empty to allow all">{{ pair.filters.keywords_allow | join(", ") if pair else "" }}</textarea>
      <div class="form-hint">Comma-separated. If non-empty, only messages with these words pass.</div>
    </div>

    <div style="display:flex;gap:12px;margin-top:8px">
      <button type="submit" class="btn btn-primary">
        {{ "Save changes" if pair else "Create pair" }}
      </button>
      <a href="/pairs" class="btn btn-ghost">Cancel</a>
    </div>

  </form>
</div>
{% endblock %}
```

- [ ] **Step 4: Update form page handlers and _pair_payload_from_form in admin_app.py**

Replace `_pair_payload_from_form` to handle multi-value checkboxes:

```python
def _pair_payload_from_form(form) -> dict[str, Any]:
    types_allow = form.getall("types_allow", []) or ["text"]
    return {
        "name": form.get("name"),
        "group_a_chat_id": form.get("group_a_chat_id"),
        "group_b_chat_id": form.get("group_b_chat_id"),
        "bidirectional": _to_bool(form.get("bidirectional"), default=False),
        "enabled": _to_bool(form.get("enabled"), default=False),
        "filters": {
            "types_allow": list(types_allow),
            "keywords_block": _split_csv(form.get("keywords_block", "")),
            "keywords_allow": _split_csv(form.get("keywords_allow", "")),
        },
    }
```

Replace `pair_create_page`:

```python
async def pair_create_page(request: web.Request) -> web.Response:
    return aiohttp_jinja2.render_template("pair_form.html", request, {
        "active_page": "pairs",
        "user": request["user"],
        "pair": None,
        "error": None,
    })
```

Replace `pair_edit_page`:

```python
async def pair_edit_page(request: web.Request) -> web.StreamResponse:
    store = request.app[CONFIG_STORE_KEY]
    name = request.match_info["name"]
    pair = store.get_pair_by_name(name)
    if pair is None:
        return web.Response(status=404, text="pair not found")
    return aiohttp_jinja2.render_template("pair_form.html", request, {
        "active_page": "pairs",
        "user": request["user"],
        "pair": pair,
        "error": None,
    })
```

Replace `pair_create_submit`:

```python
async def pair_create_submit(request: web.Request) -> web.StreamResponse:
    store = request.app[CONFIG_STORE_KEY]
    form = await request.post()
    payload = _pair_payload_from_form(form)
    try:
        pair = _pair_from_payload(payload)
        store.create_pair(pair)
    except ValueError as exc:
        return aiohttp_jinja2.render_template("pair_form.html", request, {
            "active_page": "pairs",
            "user": request["user"],
            "pair": None,
            "error": str(exc),
        })
    raise web.HTTPFound("/pairs")
```

Replace `pair_edit_submit`:

```python
async def pair_edit_submit(request: web.Request) -> web.StreamResponse:
    store = request.app[CONFIG_STORE_KEY]
    old_name = request.match_info["name"]
    existing = store.get_pair_by_name(old_name)
    if existing is None:
        return web.Response(status=404, text="pair not found")
    form = await request.post()
    payload = _pair_payload_from_form(form)
    try:
        updated = _pair_from_payload(payload, pair_id=existing.id)
        store.update_pair(updated)
    except ValueError as exc:
        return aiohttp_jinja2.render_template("pair_form.html", request, {
            "active_page": "pairs",
            "user": request["user"],
            "pair": existing,
            "error": str(exc),
        })
    raise web.HTTPFound("/pairs")
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_admin_web.py -v
```

Expected: all 16 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add bot/web/templates/pair_form.html bot/web/admin_app.py tests/test_admin_web.py
git commit -m "feat: add pair create/edit form template with checkbox types and toggle fields"
```

---

## Task 8: Create backups.html + /backups route

**Files:**
- Create: `bot/web/templates/backups.html`
- Modify: `bot/web/admin_app.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_admin_web.py`:

```python
@pytest.mark.asyncio
async def test_backups_page_renders_html(tmp_path):
    client, db_path = await _make_client(tmp_path)
    try:
        await _login(client)

        # Create a backup file so the table has a row
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        (backup_dir / "forwarder-20260610-120000.db").write_bytes(b"x" * 2048)

        resp = await client.get("/backups")
        assert resp.status == 200
        assert "text/html" in resp.content_type
        body = await resp.text()
        assert "Backups" in body
        assert "forwarder-20260610-120000.db" in body
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_backups_requires_auth(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        resp = await client.get("/backups", allow_redirects=False)
        assert resp.status == 302
        assert resp.headers["Location"] == "/login"
    finally:
        await client.close()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_admin_web.py::test_backups_page_renders_html tests/test_admin_web.py::test_backups_requires_auth -v
```

Expected: FAIL — `/backups` route doesn't exist.

- [ ] **Step 3: Create bot/web/templates/backups.html**

```html
{% extends "base.html" %}
{% block title %}Backups{% endblock %}
{% block page_title %}Backups{% endblock %}

{% block content %}
<div class="page-header">
  <div></div>
  <button id="backup-btn" class="btn btn-primary">Create backup now</button>
</div>

<div id="backup-message"></div>

<div class="table-wrapper">
  <table>
    <thead>
      <tr>
        <th>Filename</th>
        <th>Size</th>
        <th>Created</th>
      </tr>
    </thead>
    <tbody id="backup-table-body">
      {% for backup in backups %}
      <tr>
        <td>{{ backup.name }}</td>
        <td class="file-size">{{ backup.size }}</td>
        <td class="td-muted">{{ backup.created_at }}</td>
      </tr>
      {% else %}
      <tr>
        <td colspan="3">
          <div class="empty-state">
            <p>No backups yet. Use the button above to create your first backup.</p>
          </div>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 4: Add backups_page handler and route to admin_app.py**

Add this function after `dashboard_page`:

```python
async def backups_page(request: web.Request) -> web.Response:
    backup_dir = request.app[BACKUP_DIR_KEY]
    return aiohttp_jinja2.render_template("backups.html", request, {
        "active_page": "backups",
        "user": request["user"],
        "backups": _list_backups(backup_dir),
    })
```

Register the route in `create_admin_app` (add after the `/dashboard` route):

```python
    app.router.add_get("/backups", backups_page)
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_admin_web.py -v
```

Expected: all 18 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add bot/web/templates/backups.html bot/web/admin_app.py tests/test_admin_web.py
git commit -m "feat: add backups page with file list and manual backup trigger button"
```

---

## Task 9: Create luna.js

**Files:**
- Create: `bot/web/static/luna.js`

No unit tests — the JS behaviors (delete modal, toggle, backup trigger) are exercised by integration/manual testing. The underlying API calls (`DELETE /api/pairs/{name}`, `PUT /api/pairs/{name}`, `POST /api/backup`) are covered by existing tests.

- [ ] **Step 1: Create bot/web/static/luna.js**

```javascript
// ── Delete confirmation modal ──────────────────────────────────────────────

const deleteModal = document.getElementById('delete-modal');
const modalPairName = document.getElementById('modal-pair-name');
const modalConfirmBtn = document.getElementById('modal-confirm');

function openDeleteModal(name) {
  if (!deleteModal) return;
  modalPairName.textContent = name;
  deleteModal.dataset.pairName = name;
  deleteModal.classList.add('open');
}

function closeDeleteModal() {
  if (!deleteModal) return;
  deleteModal.classList.remove('open');
}

if (modalConfirmBtn) {
  modalConfirmBtn.addEventListener('click', async () => {
    const name = deleteModal.dataset.pairName;
    try {
      const res = await fetch(`/api/pairs/${encodeURIComponent(name)}`, { method: 'DELETE' });
      if (res.ok) {
        const row = document.querySelector(`tr[data-pair="${name}"]`);
        if (row) row.remove();
        closeDeleteModal();
        showToast(`Pair "${name}" deleted`, 'success');
      } else {
        closeDeleteModal();
        showToast('Delete failed', 'error');
      }
    } catch {
      closeDeleteModal();
      showToast('Request failed', 'error');
    }
  });
}

// Close modal on overlay click
if (deleteModal) {
  deleteModal.addEventListener('click', (e) => {
    if (e.target === deleteModal) closeDeleteModal();
  });
}

// ── Enable/disable toggle ──────────────────────────────────────────────────

async function togglePairEnabled(name, checkbox) {
  const originalState = !checkbox.checked;
  try {
    const listRes = await fetch(`/api/pairs?q=${encodeURIComponent(name)}`);
    if (!listRes.ok) throw new Error('fetch failed');
    const listData = await listRes.json();
    const pair = listData.pairs.find(p => p.name === name);
    if (!pair) throw new Error('pair not found');

    pair.enabled = checkbox.checked;
    const res = await fetch(`/api/pairs/${encodeURIComponent(name)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(pair),
    });

    if (!res.ok) throw new Error('update failed');

    const badge = document.querySelector(`[data-enabled-badge="${name}"]`);
    if (badge) {
      badge.textContent = checkbox.checked ? 'Enabled' : 'Disabled';
      badge.className = `badge ${checkbox.checked ? 'badge-success' : 'badge-danger'}`;
    }
  } catch {
    checkbox.checked = originalState;
    showToast('Could not update pair', 'error');
  }
}

// ── Backup trigger ─────────────────────────────────────────────────────────

const backupBtn = document.getElementById('backup-btn');
const backupMessage = document.getElementById('backup-message');

if (backupBtn) {
  backupBtn.addEventListener('click', async () => {
    backupBtn.disabled = true;
    backupBtn.textContent = 'Creating…';
    try {
      const res = await fetch('/api/backup', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        const filename = data.backup_path.split('/').pop();
        showToast(`Backup created: ${filename}`, 'success');
        setTimeout(() => location.reload(), 1500);
      } else {
        showToast(data.error || 'Backup failed', 'error');
        backupBtn.disabled = false;
        backupBtn.textContent = 'Create backup now';
      }
    } catch {
      showToast('Request failed', 'error');
      backupBtn.disabled = false;
      backupBtn.textContent = 'Create backup now';
    }
  });
}

// ── Toast notification ─────────────────────────────────────────────────────

function showToast(message, type) {
  const toast = document.createElement('div');
  toast.className = `alert alert-${type}`;
  toast.style.cssText = [
    'position:fixed',
    'bottom:24px',
    'right:24px',
    'z-index:999',
    'max-width:320px',
    'animation:fadeIn 0.2s ease',
    'pointer-events:none',
  ].join(';');
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}
```

- [ ] **Step 2: Run full test suite to confirm nothing broke**

```bash
pytest tests/test_admin_web.py -v
```

Expected: all 18 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add bot/web/static/luna.js
git commit -m "feat: add luna.js for delete modal, enable toggle, and backup trigger"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by task |
|-----------------|----------------|
| Add aiohttp-jinja2 | Task 1 |
| luna.css dark navy/teal theme | Task 3 |
| base.html sidebar shell | Task 4 |
| login.html + POST /login | Task 4 |
| dashboard.html + /dashboard | Task 5 |
| stat cards (pairs, active, today, week) | Task 5 |
| system section (last backup, storage mode) | Task 5 |
| GET /api/stats | Task 2 |
| pairs.html + update pairs_page | Task 6 |
| Delete confirmation modal | Task 6 (template) + Task 9 (JS) |
| Enable/disable toggle | Task 6 (template) + Task 9 (JS) |
| pair_form.html + form handlers | Task 7 |
| Multi-value checkbox for types_allow | Task 7 |
| backups.html + /backups | Task 8 |
| Backup trigger button | Task 8 (template) + Task 9 (JS) |
| Static file serving at /static/ | Task 1 |
| Auth middleware protects /dashboard, /backups | Task 5 |
| / redirects to /dashboard | Task 5 |
| Luna crescent moon SVG logo | Tasks 3, 4 |
| No CDN dependencies | All tasks (self-hosted CSS/JS only) |

**No gaps found.** All spec sections covered.

**Type consistency check:** `_get_last_backup` returns `str | None`, and `dashboard.html` handles `None` with `{{ last_backup or "Never" }}`. `_list_backups` returns `list[dict]` with keys `name`, `size`, `created_at` — all three used in `backups.html`. `STATS_PATH_KEY` added in Task 1 and consumed in Tasks 2 and 5. `_pair_payload_from_form` updated in Task 7 uses `form.getall()` — aiohttp's `MultiDictProxy` supports `.getall()`. Consistent throughout.
