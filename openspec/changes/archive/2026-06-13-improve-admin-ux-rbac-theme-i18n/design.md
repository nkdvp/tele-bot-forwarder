## Context

The web admin is currently server-rendered with `aiohttp + jinja2` templates and a small amount of vanilla JS/CSS. Authorization checks in handlers are stricter than what navigation currently communicates, causing non-admin users to see links they cannot access (notably Backups). Pair masking UI also exposes directional rows even though web creation always writes both directions, which creates duplicate-looking records and operator confusion.

At the same time, the UI has a single dark theme and hardcoded English strings across templates and client-side toasts. The product direction is to support Vietnamese-first operations and optional theming without migrating to a frontend framework.

Constraints:
- Keep runtime forwarding and DB schema behavior compatible.
- Prioritize low-risk incremental changes in server-rendered UI.
- Avoid broad architectural migration (no React migration in this change).

## Goals / Non-Goals

**Goals:**
- Align UI visibility with effective RBAC so users only see navigation/actions they can access.
- Represent bidirectional masking as one logical user mapping in UI.
- Introduce a stable localization foundation with Vietnamese default.
- Add theme selection with persisted preference.
- Deliver in two small phases:
  - Phase 1: RBAC/nav + masking UX cleanup
  - Phase 2: Theme switch + Vietnamese i18n foundation

**Non-Goals:**
- Changing forwarding semantics for masking or direction enforcement.
- Replacing server-rendered templates with SPA architecture.
- Full enterprise i18n workflow (pluralization/ICU tooling) in this phase.
- Per-user DB-backed UI preferences (cookie/session persistence is enough).

## Decisions

### 1) Keep storage model directional; aggregate for presentation
- **Decision**: Preserve `pair_mask_rules` directional rows in DB and aggregate them into one UI row per `(pair_id, telegram_user_id)`.
- **Rationale**: Avoids schema migration and relay regressions while removing duplicate records in UX.
- **Alternatives considered**:
  - Migrate DB to single row per user: rejected due to migration complexity and runtime risk.
  - Leave duplicated UI rows: rejected due to operator confusion.

### 2) Enforce role-aware navigation and action visibility in templates
- **Decision**: Use current `user.global_role` and team write checks to conditionally render sidebar entries and page-level controls.
- **Rationale**: Backend already enforces permissions; UI should mirror it to prevent dead-end actions.
- **Alternatives considered**:
  - Keep links visible and rely on 403: rejected due to poor UX.

### 3) Add lightweight i18n service in backend template context
- **Decision**: Add a translation dictionary + helper function exposed to templates and JS bootstrap payload.
- **Rationale**: Small codebase, server-rendered architecture, fast adoption without external dependency.
- **Alternatives considered**:
  - Full i18n framework: rejected as unnecessary overhead for current scope.
  - Hardcode Vietnamese only: rejected to keep bilingual toggle and future extensibility.

### 4) Locale resolution and default policy
- **Decision**: Resolve locale in this order: explicit query/form switch -> cookie -> default `vi`.
- **Rationale**: Meets requirement for Vietnamese default while allowing user override.
- **Alternatives considered**:
  - Browser Accept-Language default: rejected because product requires deterministic Vietnamese-first behavior.

### 5) Theme system via CSS custom properties
- **Decision**: Use `data-theme` on document root and define theme token sets in CSS (`dark`, `light`, optional `system`).
- **Rationale**: Minimal code changes and no component rewrite.
- **Alternatives considered**:
  - Separate stylesheet per theme: rejected due to duplication and maintenance cost.

## Risks / Trade-offs

- **[Risk] Aggregation mismatch if directional rows diverge** -> Mitigation: enforce upsert/delete operations to manage both directions together; surface integrity fallback in UI.
- **[Risk] Missing translations lead to mixed language UI** -> Mitigation: key coverage checklist in tasks and fallback-to-key logging for development.
- **[Risk] Theme contrast regressions** -> Mitigation: token-based palette review across key templates (dashboard/pairs/forms/tables).
- **[Risk] JS toasts remain untranslated** -> Mitigation: expose localized string map in base template and consume in `luna.js`.

## Migration Plan

1. Phase 1 (RBAC + masking):
   - Hide Backups nav for non-admin roles.
   - Ensure page/action controls reflect role/team writability consistently.
   - Add mask rule view-model aggregation (single row per user).
   - Update mask delete behavior to remove paired directional records together.
   - Add/adjust tests for visibility and masking behavior.

2. Phase 2 (theme + i18n):
   - Introduce locale helper and translation catalog (`vi`, `en`).
   - Default locale to `vi`; add switch control in topbar and persistence.
   - Localize shared template text and JS toasts.
   - Add theme switch control with persisted preference.
   - Extend tests for locale default and language switching behavior.

Rollback:
- UI-level rollback by reverting template/static/admin handler changes.
- No DB schema migration required for this change; data remains compatible.

## Open Questions

- Should locale preference be user/session-scoped only, or shared globally per browser cookie is sufficient for now?
- Should `system` theme mode ship in this change or defer to follow-up after dark/light stabilization?
- For mask aggregation conflicts (different alias/mode between directions), should UI block edits and force reconciliation, or auto-heal to latest updated rule?
