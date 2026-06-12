## Why

The current admin web UX exposes role-inappropriate navigation, displays masking data in a way that conflicts with enforced bidirectional behavior, and lacks localization/theme flexibility for daily operators. This change is needed now to reduce operator confusion, improve trust in permissions, and make Vietnamese-first usage the default without a frontend rewrite.

## What Changes

- Introduce a two-phase UX improvement rollout for the existing server-rendered admin web:
  - Phase 1: RBAC/navigation clarity and masking UX cleanup.
  - Phase 2: Theme switcher and Vietnamese-first localization foundation.
- Update navigation and page affordances so non-admin users no longer see admin-only backup entry points.
- Simplify masking management in pair edit screens to show one logical mask record per user ("who" -> "masked as what"), removing direction from visible UI where behavior is always bidirectional.
- Add language switching controls and translation plumbing with Vietnamese as default locale.
- Add theme preference controls (at minimum light/dark with persistent user preference; optional system mode support in design).

## Capabilities

### New Capabilities
- `web-admin-rbac-navigation`: Role-aware navigation and page affordance visibility aligned with backend authorization.
- `pair-masking-bidirectional-ux`: Masking UI model that represents enforced bidirectional rules as a single logical user mapping.
- `web-theme-and-localization`: Theme switching and i18n foundation with Vietnamese as default presentation language.

### Modified Capabilities
- None.

## Impact

- Affected code areas:
  - `bot/web/templates/base.html` (role-aware nav and language/theme controls)
  - `bot/web/templates/pair_form.html` (masking table and form UX)
  - `bot/web/templates/*.html` (translated labels/messages)
  - `bot/web/admin_app.py` (view models, locale resolution, template context)
  - `bot/web/static/luna.css` (theme tokens and theme variants)
  - `bot/web/static/luna.js` (language/theme interaction and localized client messages)
- Affected tests:
  - `tests/test_admin_web.py` (RBAC visibility, masking behavior, localized rendering defaults)
- No breaking API contract expected for external callers; behavior changes are primarily UX-level and server-rendered output-level.
