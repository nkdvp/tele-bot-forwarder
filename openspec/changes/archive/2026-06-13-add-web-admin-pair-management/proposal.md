## Why

The bot currently stores operational state across local files (`config.yaml`, `data/reply_map.json`, `data/stats.json`) and is managed primarily through Telegram commands. This makes pair administration, search, and safe operational workflows harder as usage grows and creates risk from dual/manual edits.

## What Changes

- Add a web admin interface for pair management with login-protected access.
- Introduce SQLite as the primary datastore for pairs and reply-link mapping used by forwarding.
- Provide searchable pair management (name, chat IDs, enabled state, directionality) and CRUD operations.
- Add a migration flow to import existing file-based data into SQLite while preserving rollback ability.
- Add backup operations for the SQLite database with retention policy.
- Keep advanced RBAC (multi-role authorization matrix) out of V1; deliver basic authenticated admin access first.

## Capabilities

### New Capabilities
- `web-admin-auth`: Login-based access control for web administration in V1.
- `pair-management-web`: Web UI and APIs for searching and managing forwarding pairs.
- `pair-config-store`: Database-backed configuration store that becomes the source of truth for pair config.
- `reply-link-persistence`: Database-backed reply-link mapping for cross-group reply threading continuity.
- `database-backup-operations`: Scheduled and manual backup workflows for the SQLite datastore.
- `file-to-db-migration`: One-time migration and rollback controls from file-based state to DB-backed state.

### Modified Capabilities
- None.

## Impact

- Affected code areas: config loading/writing, reply mapping, command mutation behavior, deployment/runtime scripts.
- New components: web app routes/pages, persistence layer, DB schema/migration scripts, backup jobs.
- Operational impact: introduces DB lifecycle and backup/restore routines; reduces direct YAML/JSON operational edits.
- Dependency impact: adds SQLite access library and password-hashing/session management dependencies for web login.
