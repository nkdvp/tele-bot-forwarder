# Luna Admin Dashboard — Design Spec
**Date:** 2026-06-10  
**Status:** Approved  
**Scope:** Upgrade existing `bot/web/` admin UI to a polished Luna-branded dashboard

---

## 1. Overview

Replace the existing bare-bones HTML in `bot/web/admin_app.py` with a full Jinja2 template layer and static assets. The Python backend (routes, API endpoints, auth middleware) stays unchanged except for one new endpoint. The result is a dark-themed, Luna-branded admin dashboard for managing the Telegram forwarder bot.

**Storage mode:** DB mode only (`USE_DB_CONFIG=true`). The web admin is already gated behind this flag.

---

## 2. Architecture

### What changes
- `bot/web/admin_app.py`: Switch route handlers from returning inline HTML strings to rendering Jinja2 templates via `aiohttp_jinja2`. Add one new API endpoint (`GET /api/stats`).
- Add `bot/web/templates/` with all HTML templates.
- Add `bot/web/static/` with `luna.css` and `luna.js`.

### What stays the same
- All existing API endpoints (`/api/pairs`, `/api/backup`, `/api/login`, `/api/logout`)
- Auth middleware and session cookie logic
- `SQLiteConfigStore`, `AuthStore`, `BackupOps` — zero changes

### New file layout
```
bot/web/
├── admin_app.py              (modified: template rendering + /api/stats)
├── server.py                 (unchanged)
├── templates/
│   ├── base.html             (sidebar nav, header, content slot)
│   ├── login.html
│   ├── dashboard.html        (stat cards + system status)
│   ├── pairs.html            (searchable pair table)
│   ├── pair_form.html        (create + edit, shared)
│   └── backups.html          (backup list + trigger)
└── static/
    ├── luna.css
    └── luna.js
```

---

## 3. Pages

| Page | Route | Method | Auth required |
|------|-------|--------|---------------|
| Login | `/login` | GET | No |
| Dashboard | `/` → redirect to `/dashboard` | GET | Yes |
| Dashboard | `/dashboard` | GET | Yes |
| Pairs list | `/pairs` | GET | Yes |
| Create pair | `/pairs/new` | GET | Yes |
| Edit pair | `/pairs/{name}/edit` | GET | Yes |
| Backups | `/backups` | GET | Yes |

---

## 4. Visual Theme

### Color palette
| Token | Value | Usage |
|-------|-------|-------|
| `--bg` | `#0f172a` | Page background |
| `--surface` | `#1e293b` | Cards, sidebar, inputs |
| `--border` | `#334155` | Dividers, input borders |
| `--accent` | `#06b6d4` | Buttons, links, active nav, focus rings |
| `--accent-hover` | `#0891b2` | Button hover state |
| `--text` | `#f1f5f9` | Primary text |
| `--text-muted` | `#94a3b8` | Labels, secondary text |
| `--success` | `#10b981` | Enabled badge, success toast |
| `--danger` | `#ef4444` | Delete button, disabled badge, error |

### Typography
System sans-serif stack: `-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`. No external font dependencies.

### Layout
- Fixed left sidebar: 240px wide. Contains Luna logo (crescent moon SVG + "Luna" wordmark) and nav links.
- Top bar: page title (left) + username + logout link (right).
- Main content area: scrolls independently. Max-width 1200px, centered with padding.

### Components
- **Stat cards**: `--surface` background, 3px teal top border, large bold number, muted label below.
- **Table**: `--surface` rows, subtle zebra via slight opacity shift, teal row hover, inline badges for enabled/disabled.
- **Badges**: Pill shape. Green background for enabled, red for disabled.
- **Primary button**: Solid `--accent` background, white text, 6px border radius.
- **Danger button**: Solid `--danger` background, white text.
- **Ghost button**: Transparent with `--border` border, `--text` color.
- **Form inputs**: `--surface` background, `--border` border, `--accent` focus ring (2px outline), `--text` color.
- **Nav items**: `--text-muted` text; active state = teal left border (3px) + `--accent` text.

### Luna logo
Inline SVG crescent moon in `--accent` teal, beside the wordmark "Luna" in bold `--text` white. No external image files.

---

## 5. Template Details

### `base.html`
Wraps all authenticated pages. Provides:
- `<head>` with luna.css link
- Sidebar with logo + nav links (Dashboard, Pairs, Backups)
- Top bar with page title block + user/logout
- Main content `{% block content %}` slot
- luna.js script at bottom

### `login.html`
Standalone (no sidebar). Centered card on full-page `--bg`. Luna logo at top, username + password fields, "Sign in" button. On invalid credentials, inline error message below form. Calls `POST /api/login` via form submit (not fetch), redirect handled server-side.

### `dashboard.html`
Four stat cards in a 2×2 (or 4-in-a-row) grid:
- Total pairs
- Active pairs (enabled=true)
- Messages forwarded today (sum across all pairs)
- Messages forwarded this week

Below cards: a "System" section showing:
- Bot uptime (sourced from `/health` endpoint or in-memory start time)
- Last backup timestamp (most recent file in `backups/` dir)
- Storage mode badge (DB / File)

### `pairs.html`
- Search input (filters table client-side by pair name or chat ID)
- Filter chips: All / Active / Inactive
- Table columns: Name | Group A | Group B | Direction | Enabled | Actions
- "New pair" button (top right, primary)
- Enabled column: toggle switch (calls `PUT /api/pairs/{name}` with `{enabled: true/false}`)
- Actions: Edit (ghost button) | Delete (danger button → confirmation modal)
- Empty state: centered illustration + "No pairs configured yet. Create your first pair."

### `pair_form.html`
Shared for create and edit. Fields:
- **Name** (text input; read-only on edit)
- **Group A chat ID** (number input)
- **Group B chat ID** (number input)
- **Bidirectional** (checkbox toggle)
- **Enabled** (checkbox toggle)
- **Allowed message types** (checkbox group: text, photo, video, sticker, document, voice, animation — all checked by default on create)
- **Keywords — block list** (textarea, comma-separated)
- **Keywords — allow list** (textarea, comma-separated; helper text: "Leave empty to allow all")

Submit calls `POST /api/pairs` (create) or `PUT /api/pairs/{name}` (edit) via `luna.js`. On success: redirect to `/pairs`. On error: inline error message.

### `backups.html`
- Table: Filename | Size | Created at | —
- "Create backup now" button → calls `POST /api/backup` via fetch, shows success/error toast, refreshes list
- Table populated server-side by reading `backups/` directory at page render time
- Empty state if no backups exist

---

## 6. New Backend Additions

### `GET /api/stats`
Reads `data/stats.json` (file mode) or equivalent from DB and returns:
```json
{
  "today": 142,
  "week": 890,
  "pairs_total": 5,
  "pairs_active": 4
}
```
Used by `dashboard.html` (rendered server-side, not via client fetch — template receives stats dict directly from route handler).

### Template rendering
Add `aiohttp_jinja2` setup to `admin_app.py`:
```python
aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader('bot/web/templates'))
```
Route handlers return `aiohttp_jinja2.render_template(name, request, context)` instead of `web.Response(text=html)`.

### Static files
Mount `bot/web/static/` at `/static/` using `app.router.add_static('/static/', path='bot/web/static/')`.

### New `/dashboard` route
Redirect `/` → `/dashboard`. The dashboard route handler:
1. Fetches pair list from `SQLiteConfigStore`
2. Reads stats from `data/stats.json`
3. Reads last backup timestamp from `backups/` directory
4. Renders `dashboard.html` with context dict

---

## 7. JavaScript (`luna.js`)

Minimal vanilla JS — no framework. Three behaviors:

1. **Enable/disable toggle** on pairs table: `PATCH`-style call to `PUT /api/pairs/{name}` with current pair data + flipped `enabled` value. Updates badge in-place without reload.

2. **Delete confirmation modal**: Generic modal component. "Delete" button sets `data-pair-name` on modal, confirm button calls `DELETE /api/pairs/{name}`, on success removes table row.

3. **Backup trigger**: Button calls `POST /api/backup`, shows inline success ("Backup created: filename") or error message, refreshes backup table rows via `GET /api/pairs`-equivalent for backups (or full page reload as fallback).

---

## 8. Dependencies

New Python packages needed:
- `aiohttp-jinja2` — Jinja2 template rendering for aiohttp
- `jinja2` — likely already present as aiohttp-jinja2 dependency

No new frontend dependencies. No CDN calls. All CSS and JS are local files.

---

## 9. Out of Scope

- Role-based access control (single admin for now)
- Multiple bot support
- Real-time WebSocket updates
- Masking rules editor (masking remains Telegram-command-only for now)
- Global settings editor (`recovery_window_minutes`, `strip_mentions`) — Telegram commands only for now
- Message log / forwarding history view
