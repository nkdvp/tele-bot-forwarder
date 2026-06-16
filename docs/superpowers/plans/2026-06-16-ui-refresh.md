# UI Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace cold cyan/slate theme with warm indigo-purple palette and redesign the pair mask form to be friendlier — avatar initials on existing masks, pill-button mode toggle, animated alias field, better empty state.

**Architecture:** All changes are purely frontend — CSS token swap in `luna.css`, template markup changes in `pair_form.html` and `base.html`, and JS additions in `luna.js` for pill mode toggle. No backend changes. Modern-web-guidance best practices applied: `@starting-style` for alias field animation, `color-scheme` + FOUC-safe inline script for dark mode.

**Tech Stack:** Vanilla CSS custom properties, Jinja2 HTML templates, vanilla JavaScript (no frameworks).

---

## File Map

| File | Change |
|---|---|
| `bot/web/templates/base.html` | Add `<meta name="color-scheme">`, fix FOUC inline script |
| `bot/web/static/luna.css` | Swap color tokens, `color-scheme`+`accent-color` on `:root`, add `.mask-avatar`, `.mode-pills`, `@starting-style` alias animation |
| `bot/web/templates/pair_form.html` | Avatar in mask table rows, empty state message, redesigned add-mask card using `hidden` attribute |
| `bot/web/static/luna.js` | Replace `<select>`-based mode sync with pill-button click handler using `hidden` attribute |

---

## Task 1: Fix base.html for FOUC-safe dark mode (modern-web-guidance)

**Files:**
- Modify: `bot/web/templates/base.html`

- [ ] **Step 1: Add `<meta name="color-scheme">` and FOUC-safe inline script**

In `bot/web/templates/base.html`, find the `<head>` block and add after the `<meta charset>` line:

Old:
```html
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{% block title %}Luna{% endblock %} — Luna Admin</title>
  <link rel="stylesheet" href="/static/luna.css" />
```

New:
```html
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="color-scheme" content="light dark" />
  <title>{% block title %}Luna{% endblock %} — Luna Admin</title>
  <link rel="stylesheet" href="/static/luna.css" />
  <script>
  {
    const t = localStorage.getItem('luna_admin_theme');
    if (t === 'dark' || t === 'light') {
      document.documentElement.dataset.theme = t;
      document.querySelector('meta[name="color-scheme"]').content = t;
    }
  }
  </script>
```

This must be an inline script (NOT `defer`, NOT `type=module`) so it runs before first paint, preventing a flash of unstyled content when a user has pinned a theme.

- [ ] **Step 2: Commit**

```bash
git add bot/web/templates/base.html
git commit -m "feat: add color-scheme meta and FOUC-safe inline theme script"
```

---

## Task 2: Update color tokens and root color-scheme in luna.css

**Files:**
- Modify: `bot/web/static/luna.css:1-25`

- [ ] **Step 1: Replace dark theme tokens**

In `bot/web/static/luna.css`, replace the `html[data-theme="dark"]` block (lines 1–12) with:

```css
html[data-theme="dark"] {
  --bg: #0f0f1a;
  --surface: #1a1a2e;
  --border: #2d2d4e;
  --accent: #818cf8;
  --accent-hover: #6366f1;
  --text: #e8e8f8;
  --text-muted: #9090b8;
  --success: #34d399;
  --danger: #f87171;
  --sidebar-width: 240px;
}
```

- [ ] **Step 2: Replace light theme tokens**

Replace the `html[data-theme="light"]` block (lines 14–25) with:

```css
html[data-theme="light"] {
  --bg: #f5f5ff;
  --surface: #ffffff;
  --border: #c7c7e8;
  --accent: #6366f1;
  --accent-hover: #4f46e5;
  --text: #1a1a3e;
  --text-muted: #6060a0;
  --success: #10b981;
  --danger: #ef4444;
  --sidebar-width: 240px;
}
```

- [ ] **Step 3: Add `color-scheme` and `accent-color` to `:root`**

After the two theme blocks (after line 25), add:

```css
:root {
  color-scheme: light dark;
}

html {
  accent-color: var(--accent);
}
```

This tells the browser to auto-theme native controls (scrollbars, checkboxes) and uses the indigo accent for checkbox ticks and range sliders.

- [ ] **Step 4: Fix sidebar active state background**

Find the `.sidebar-nav a.active` rule and change the background value:

Old:
```css
background: rgba(6,182,212,0.08);
```
New:
```css
background: rgba(129,140,248,0.12);
```

- [ ] **Step 5: Commit**

```bash
git add bot/web/static/luna.css
git commit -m "feat: swap theme tokens to warm indigo-purple palette with color-scheme"
```

---

## Task 3: Add mask avatar and mode pill CSS with @starting-style animation

**Files:**
- Modify: `bot/web/static/luna.css` (append to end)

- [ ] **Step 1: Append new CSS rules**

Add the following to the **end** of `bot/web/static/luna.css`:

```css
/* ── Mask avatar ── */
.mask-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: rgba(129,140,248,0.2);
  color: var(--accent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
  letter-spacing: 0;
}

.mask-avatar.anon {
  background: rgba(144,144,184,0.15);
  color: var(--text-muted);
}

.mask-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* ── Mode pill toggle ── */
.mode-pills {
  display: flex;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}

.mode-pill {
  flex: 1;
  padding: 9px 0;
  text-align: center;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  background: transparent;
  color: var(--text-muted);
  border: none;
  transition: background 0.15s, color 0.15s;
}

.mode-pill.active {
  background: var(--accent);
  color: #fff;
}

/* ── Alias field: modern show/hide with @starting-style (modern-web-guidance) ── */
#alias-field-group {
  display: block;
  opacity: 1;
  translate: 0;
  transition:
    opacity 0.2s ease-out,
    translate 0.2s ease-out,
    display 0.2s;
  transition-behavior: allow-discrete;
}

@starting-style {
  #alias-field-group {
    opacity: 0;
    translate: 0 -8px;
  }
}

#alias-field-group[hidden] {
  display: none;
  opacity: 0;
  translate: 0 -8px;
}

@media (prefers-reduced-motion: reduce) {
  #alias-field-group {
    translate: none;
    transition-duration: 0.1s;
  }

  @starting-style {
    #alias-field-group {
      translate: none;
    }
  }

  #alias-field-group[hidden] {
    translate: none;
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add bot/web/static/luna.css
git commit -m "feat: add mask avatar, mode pill, and @starting-style alias animation CSS"
```

---

## Task 4: Update mask table in pair_form.html

**Files:**
- Modify: `bot/web/templates/pair_form.html:115-154`

- [ ] **Step 1: Add avatar to each mask row**

Find the `{% for mapping in mask_mappings %}` block and replace the first `<td>` (user ID cell):

Old:
```html
      <tr>
        <td class="td-muted">{{ mapping.telegram_user_id }}</td>
        <td>
          {% if mapping.mode == "anonymous" %}
            {{ t("pair_form.mask_anonymous") }}
          {% else %}
            {{ mapping.alias or t("pair_form.mask_alias_placeholder") }}
          {% endif %}
        </td>
```

New:
```html
      <tr>
        <td>
          <div class="mask-cell">
            {% if mapping.mode == "anonymous" %}
              <span class="mask-avatar anon">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
                  <line x1="4" y1="4" x2="20" y2="20"/>
                </svg>
              </span>
            {% else %}
              <span class="mask-avatar">{{ (mapping.alias or "?")[:2].upper() }}</span>
            {% endif %}
            <span class="td-muted">{{ mapping.telegram_user_id }}</span>
          </div>
        </td>
        <td>
          {% if mapping.mode == "anonymous" %}
            {{ t("pair_form.mask_anonymous") }}
          {% else %}
            {{ mapping.alias or t("pair_form.mask_alias_placeholder") }}
          {% endif %}
        </td>
```

- [ ] **Step 2: Improve the empty state**

Find the `{% else %}` branch inside the mask table body and replace:

Old:
```html
      {% else %}
      <tr>
        <td colspan="{{ 3 if can_manage_pair else 2 }}">
          <div class="empty-state">
            <p>{{ t("pair_form.mask_empty") }}</p>
          </div>
        </td>
      </tr>
```

New:
```html
      {% else %}
      <tr>
        <td colspan="{{ 3 if can_manage_pair else 2 }}">
          <div class="empty-state">
            <p>{{ t("pair_form.mask_empty") }}</p>
            {% if can_manage_pair %}
            <a href="#add-mask-card" class="btn btn-ghost btn-sm">+ Add first mask</a>
            {% endif %}
          </div>
        </td>
      </tr>
```

- [ ] **Step 3: Commit**

```bash
git add bot/web/templates/pair_form.html
git commit -m "feat: add avatar initials and improved empty state to mask table"
```

---

## Task 5: Redesign the add-mask card in pair_form.html

**Files:**
- Modify: `bot/web/templates/pair_form.html:156-184`

- [ ] **Step 1: Replace the add-mask form**

Find the `{% if can_manage_pair %}` add-mask block (the card with `inline-grid`) and replace the entire block.

Old:
```html
{% if can_manage_pair %}
<div class="card" style="max-width:900px">
  <form method="post" action="/pairs/{{ pair.name }}/masks">
    <div class="inline-grid">
      <div class="form-group">
        <label class="form-label" for="telegram_user_id">{{ t("pair_form.mask_user_id") }}</label>
        <input class="form-input" type="number" id="telegram_user_id" name="telegram_user_id" required />
      </div>
      <div class="form-group">
        <label class="form-label" for="mode">{{ t("pair_form.mask_mode") }}</label>
        <select class="form-select" id="mode" name="mode">
          <option value="alias" selected>{{ t("pair_form.mask_mode_alias") }}</option>
          <option value="anonymous">{{ t("pair_form.mask_mode_anon") }}</option>
        </select>
      </div>
      <div class="form-group" id="alias-field-group">
        <label class="form-label" for="alias">{{ t("pair_form.mask_alias_label") }}</label>
        <input class="form-input" type="text" id="alias" name="alias" list="alias-suggestions"
               placeholder="{{ t("pair_form.mask_alias_placeholder") }}" />
        <datalist id="alias-suggestions"></datalist>
      </div>
    </div>
    <div class="form-hint" style="margin-bottom:12px">
      {{ t("pair_form.mask_hint_bidirectional") }}
    </div>
    <button type="submit" class="btn btn-primary">{{ t("pair_form.mask_save") }}</button>
  </form>
</div>
{% endif %}
```

New:
```html
{% if can_manage_pair %}
<div class="card" id="add-mask-card" style="max-width:520px">
  <form method="post" action="/pairs/{{ pair.name }}/masks">

    <div class="form-group">
      <label class="form-label" for="telegram_user_id">{{ t("pair_form.mask_user_id") }}</label>
      <input class="form-input" type="number" id="telegram_user_id" name="telegram_user_id"
             placeholder="e.g. 123456789" required />
      <div class="form-hint">Paste the Telegram user ID. To find it: forward their message to @userinfobot</div>
    </div>

    <div class="form-group">
      <label class="form-label">{{ t("pair_form.mask_mode") }}</label>
      <input type="hidden" id="mode" name="mode" value="alias" />
      <div class="mode-pills">
        <button type="button" class="mode-pill active" data-mode="alias">{{ t("pair_form.mask_mode_alias") }}</button>
        <button type="button" class="mode-pill" data-mode="anonymous">{{ t("pair_form.mask_mode_anon") }}</button>
      </div>
    </div>

    <div class="form-group" id="alias-field-group">
      <label class="form-label" for="alias">{{ t("pair_form.mask_alias_label") }}</label>
      <input class="form-input" type="text" id="alias" name="alias" list="alias-suggestions"
             placeholder="{{ t("pair_form.mask_alias_placeholder") }}" />
      <datalist id="alias-suggestions"></datalist>
    </div>

    <div class="form-hint" style="margin-bottom:16px">
      {{ t("pair_form.mask_hint_bidirectional") }}
    </div>

    <button type="submit" class="btn btn-primary" style="width:100%">{{ t("pair_form.mask_save") }}</button>

  </form>
</div>
{% endif %}
```

- [ ] **Step 2: Commit**

```bash
git add bot/web/templates/pair_form.html
git commit -m "feat: redesign add-mask card with pill toggle and friendly layout"
```

---

## Task 6: Update JS for pill mode toggle using `hidden` attribute

**Files:**
- Modify: `bot/web/static/luna.js:104-127`

- [ ] **Step 1: Replace the mask mode sync logic**

Find the section `// ── Mask alias suggestions ──` and replace from `const maskModeInput` through the end of the `if (maskModeInput)` block:

Old:
```js
const maskModeInput = document.getElementById('mode');
const aliasFieldGroup = document.getElementById('alias-field-group');
const aliasInput = document.getElementById('alias');

function syncMaskAliasVisibility() {
  if (!maskModeInput || !aliasFieldGroup || !aliasInput) return;
  const useAlias = maskModeInput.value === 'alias';
  aliasFieldGroup.style.display = useAlias ? '' : 'none';
  aliasInput.disabled = !useAlias;
  aliasInput.required = useAlias;
  if (!useAlias) {
    aliasInput.value = '';
    if (aliasSuggestions) aliasSuggestions.innerHTML = '';
  }
}

if (maskModeInput) {
  syncMaskAliasVisibility();
  maskModeInput.addEventListener('change', syncMaskAliasVisibility);
}
```

New:
```js
const maskModeInput = document.getElementById('mode');
const aliasFieldGroup = document.getElementById('alias-field-group');
const aliasInput = document.getElementById('alias');

function setMaskMode(mode) {
  if (!maskModeInput || !aliasFieldGroup || !aliasInput) return;
  maskModeInput.value = mode;
  const useAlias = mode === 'alias';
  // Use hidden attribute so CSS @starting-style transition fires correctly
  aliasFieldGroup.hidden = !useAlias;
  aliasInput.disabled = !useAlias;
  aliasInput.required = useAlias;
  if (!useAlias) {
    aliasInput.value = '';
    if (aliasSuggestions) aliasSuggestions.innerHTML = '';
  }
  document.querySelectorAll('.mode-pill').forEach(pill => {
    pill.classList.toggle('active', pill.dataset.mode === mode);
  });
}

document.querySelectorAll('.mode-pill').forEach(pill => {
  pill.addEventListener('click', () => setMaskMode(pill.dataset.mode));
});

if (maskModeInput) setMaskMode(maskModeInput.value || 'alias');
```

Note: We use `element.hidden = true` (which sets the `hidden` attribute) instead of a `.hidden` class so that the CSS `#alias-field-group[hidden]` rule fires and the `@starting-style` entry animation triggers correctly on reveal.

- [ ] **Step 2: Commit**

```bash
git add bot/web/static/luna.js
git commit -m "feat: replace select-based mask mode with pill toggle JS"
```

---

## Task 7: Manual verification

- [ ] **Step 1: Start the bot locally**

```bash
cd /Users/ducnguyen/Sandbox/luna-code/bot-forward-msg-tele
source venv/bin/activate
USE_DB_CONFIG=true python main.py
```

- [ ] **Step 2: Open admin UI**

Navigate to `http://localhost:8090` and log in.

- [ ] **Step 3: Verify theme**

Check dark mode: sidebar, cards, buttons, and inputs show warm indigo tones (not cyan). Toggle to light mode — background should be `#f5f5ff` (soft lavender). Native checkboxes should tick in indigo (from `accent-color`). No white flash on page load.

- [ ] **Step 4: Verify mask form**

Open any pair's edit page. Scroll to the masking section:
- Existing masks show avatar circles with initials (alias mode) or ghost icon (anonymous).
- Empty state shows friendly message with `+ Add first mask` button.
- Add-mask card shows two pill buttons (Alias / Anonymous). Clicking Anonymous smoothly hides the alias field (fade + slide up). Clicking Alias reveals it with a fade + slide down entry animation.

- [ ] **Step 5: Final commit if any tweaks made**

```bash
git add -p
git commit -m "fix: ui refresh tweaks from manual verification"
```
