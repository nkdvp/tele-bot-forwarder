# UI Refresh — Warm Theme & Friendly Mask Form

**Date:** 2026-06-16  
**Branch:** v4-custom  
**Scope:** CSS theme overhaul + pair mask form UX improvement. No backend changes.

---

## 1. Goals

- Replace the cold cyan/slate palette with a warm indigo-purple theme that feels lively, not robotic.
- Make the mask user form friendlier: avatar initials on existing masks, pill-button mode toggle, animated alias field, better empty state.
- Keep both dark and light themes working. No structural layout changes.

---

## 2. Theme & Color Palette

All changes are in `bot/web/static/luna.css`.

### Dark theme tokens

| Token | Old | New |
|---|---|---|
| `--bg` | `#0f172a` | `#0f0f1a` |
| `--surface` | `#1e293b` | `#1a1a2e` |
| `--border` | `#334155` | `#2d2d4e` |
| `--accent` | `#06b6d4` | `#818cf8` |
| `--accent-hover` | `#0891b2` | `#6366f1` |
| `--text` | `#f1f5f9` | `#e8e8f8` |
| `--text-muted` | `#94a3b8` | `#9090b8` |
| `--success` | `#10b981` | `#34d399` |
| `--danger` | `#ef4444` | `#f87171` |

### Light theme tokens

| Token | Old | New |
|---|---|---|
| `--bg` | `#f8fafc` | `#f5f5ff` |
| `--surface` | `#ffffff` | `#ffffff` |
| `--border` | `#cbd5e1` | `#c7c7e8` |
| `--accent` | `#0891b2` | `#6366f1` |
| `--accent-hover` | `#0e7490` | `#4f46e5` |
| `--text` | `#0f172a` | `#1a1a3e` |
| `--text-muted` | `#64748b` | `#6060a0` |
| `--success` | `#059669` | `#10b981` |
| `--danger` | `#dc2626` | `#ef4444` |

### Sidebar active state
Change from cyan left-border to indigo glow:
```css
.sidebar-nav a.active {
  color: var(--accent);
  border-left-color: var(--accent);
  background: rgba(129, 140, 248, 0.12);  /* was rgba(6,182,212,0.08) */
}
```

### Stat card top border
Change `--accent` highlight from cyan to indigo (already uses `var(--accent)` — no change needed, inherits automatically).

---

## 3. Mask Form UX (`bot/web/templates/pair_form.html`)

### 3a. Existing masks table — avatar initials

Each mask row gets an avatar circle left of the user ID:
- **Alias mode**: Show initials from alias string (e.g. `"John Doe"` → `JD`). Cap at 2 characters. Indigo background.
- **Anonymous mode**: Show a ghost/incognito icon SVG. Muted background.
- Avatar is a `32×32` circle rendered inline in the `<td>`.

New CSS needed:
```css
.mask-avatar {
  width: 32px; height: 32px;
  border-radius: 50%;
  background: rgba(129,140,248,0.2);
  color: var(--accent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}
.mask-avatar.anon {
  background: rgba(144,144,184,0.15);
  color: var(--text-muted);
}
```

User ID cell becomes a flex row: `[avatar] [user_id]`.

### 3b. Empty state

Replace the bare empty `<td>` with:
```
No masks yet — messages forward with real names.
[+ Add first mask ↓]
```
The link scrolls to / focuses the add form below.

### 3c. Add mask card — redesigned

Replace the 4-column `inline-grid` form with a vertical card layout:

**Step 1 — User ID field** (full width, larger, with hint text below):
> *"Paste the Telegram user ID. To find it: forward their message to @userinfobot"*

**Step 2 — Mode** as pill toggle buttons (replaces `<select>`):
```
[ Alias ]  [ Anonymous ]
```
`Alias` selected by default. Clicking Anonymous hides the alias field.

**Step 3 — Alias field** fades in (CSS transition `opacity + max-height`) when Alias mode is active. Hidden when Anonymous.

**Submit button**: Full-width `btn-primary` at the bottom of the card, label: *"Add Mask"*.

New CSS for pill toggle:
```css
.mode-pills { display: flex; gap: 0; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.mode-pill {
  flex: 1; padding: 8px 0; text-align: center;
  font-size: 13px; font-weight: 500; cursor: pointer;
  background: transparent; color: var(--text-muted);
  border: none; transition: background 0.15s, color 0.15s;
}
.mode-pill.active { background: var(--accent); color: #fff; }
```

JS: clicking a pill sets a hidden `<input name="mode">` value and toggles `.active` class + alias field visibility. No form submission — just UI state.

---

## 4. Files Changed

| File | Change |
|---|---|
| `bot/web/static/luna.css` | Token values, sidebar active, mask avatar styles, mode pill styles |
| `bot/web/templates/pair_form.html` | Mask table rows (avatar), empty state, add-mask form layout |
| `bot/web/static/luna.js` | Pill toggle JS (mode switching + alias field show/hide) |

---

## 5. Out of Scope

- No backend changes.
- No Telegram member lookup (planned for later).
- No layout restructuring (sidebar, topbar, content area unchanged).
- No changes to other pages (users, teams, backups, dashboard).
