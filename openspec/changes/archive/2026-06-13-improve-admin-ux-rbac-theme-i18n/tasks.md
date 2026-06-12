## 1. Phase 1 - RBAC and navigation alignment

- [x] 1.1 Update `base.html` sidebar rendering to hide Backups, Users, and Teams for non-admin roles.
- [x] 1.2 Audit authenticated templates and hide or disable mutation controls where user lacks team write permissions.
- [x] 1.3 Add/adjust `tests/test_admin_web.py` cases for role-based navigation visibility and restricted control rendering.

## 2. Phase 1 - Masking UX cleanup

- [x] 2.1 Add mask view-model aggregation in `admin_app.py` to represent one logical row per pair + Telegram user ID.
- [x] 2.2 Refactor `pair_form.html` masking table to remove direction column and show one "user -> masked as" row.
- [x] 2.3 Update mask delete flow to remove both directional records for the selected user mapping.
- [x] 2.4 Add/adjust tests for aggregated masking list rendering and bidirectional create/delete consistency.

## 3. Phase 2 - Localization foundation (Vietnamese default)

- [x] 3.1 Introduce locale resolution helper with precedence (explicit switch -> cookie/session -> default `vi`).
- [x] 3.2 Add translation catalog structure for Vietnamese and English and expose translation helper to templates.
- [x] 3.3 Localize shared layout and core pages (`login`, `dashboard`, `pairs`, `pair_form`, `backups`, `users`, `teams`).
- [x] 3.4 Localize `luna.js` user-facing messages (toasts and action feedback) using active locale context.
- [x] 3.5 Add tests confirming Vietnamese default rendering and persistence of language choice.

## 4. Phase 2 - Theme switch foundation

- [x] 4.1 Add theme control UI in topbar with persisted preference (dark/light; optional system mode if included).
- [x] 4.2 Extend `luna.css` with tokenized light theme variables and root attribute switching.
- [x] 4.3 Add JS/bootstrap logic to apply stored theme preference on initial render and on navigation.
- [x] 4.4 Add regression checks for contrast and readability on key screens in both themes.

## 5. End-to-end verification and docs

- [x] 5.1 Run targeted admin web tests covering RBAC, masking, localization, and theme changes.
- [x] 5.2 Perform manual smoke checks for user/admin role differences, mask CRUD UX, locale switch, and theme switch.
- [x] 5.3 Update operator documentation for language/theme controls and clarified role-based UI behavior.
