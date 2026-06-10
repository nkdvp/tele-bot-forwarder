## Context

The current bot persists mutable state in flat files and updates that state from Telegram commands. Pair operations and reply-link state are operationally critical but not easy to search, validate, or back up as the system grows. The change introduces a minimal web admin and a SQLite-backed store while preserving current forwarding behavior and minimizing migration risk.

Primary constraints:
- Keep V1 small enough to ship quickly.
- Avoid dual-write drift between web updates and Telegram command updates.
- Preserve reply threading behavior across restarts.
- Provide clear rollback if production issues occur after migration.

## Goals / Non-Goals

**Goals:**
- Introduce SQLite as source of truth for pair config and reply-link persistence.
- Provide authenticated web administration for pair CRUD, toggles, and search.
- Migrate existing file-based state into DB with deterministic import.
- Add scheduled/manual DB backups with retention.
- Keep forwarding runtime behavior unchanged from an operator perspective.

**Non-Goals:**
- Full RBAC with role matrix (owner/operator/viewer) in V1.
- OAuth/SSO integrations.
- Multi-node distributed deployment architecture.
- Postgres migration in V1.
- Full historical audit log for all config mutations.

## Decisions

### 1) Source of truth: SQLite in V1
- **Decision**: Use `data/forwarder.db` as the single source of truth for pair config and reply links.
- **Rationale**: SQLite reduces operational complexity while enabling structured queries, constraints, and backups.
- **Alternatives considered**:
  - Keep YAML/JSON and add web wrappers: rejected due to weak consistency guarantees and difficult querying.
  - Introduce Postgres now: rejected for V1 due to deployment and operational overhead.

### 2) Consistency model: single write path
- **Decision**: Route mutating admin flows through the DB store and disable or convert mutating Telegram commands to read-only guidance in V1.
- **Rationale**: Prevents conflicts between web writes and file/legacy command writes.
- **Alternatives considered**:
  - Dual-write DB + YAML for compatibility: rejected due to drift and rollback complexity.

### 3) Integration seam: `ConfigStore` abstraction
- **Decision**: Introduce a storage interface consumed by both bot handlers and web handlers.
- **Rationale**: Contains migration impact and enables future backend swaps (e.g., Postgres) without rewriting business logic.
- **Alternatives considered**:
  - Embed SQL queries directly into handlers: rejected due to coupling and testability cost.

### 4) Authentication scope for V1
- **Decision**: Implement simple username/password login with session cookies for web admin.
- **Rationale**: Meets immediate access control needs with low implementation burden.
- **Alternatives considered**:
  - Skip auth for internal network only: rejected due to avoidable security risk.
  - Implement RBAC immediately: deferred to V2 to keep V1 deliverable.

### 5) Migration and rollback strategy
- **Decision**: Add explicit migration tooling from `config.yaml` and `data/reply_map.json`, guarded by `USE_DB_CONFIG` runtime flag.
- **Rationale**: Enables controlled cutover and fast rollback to file mode if issues arise.
- **Alternatives considered**:
  - One-way irreversible migration: rejected due to operational risk.

## Risks / Trade-offs

- **[Risk] Migration data mismatch (file shape vs DB schema)** → Mitigation: strict validation and dry-run mode before write.
- **[Risk] Runtime behavior drift after config-store swap** → Mitigation: integration tests around pair lookup, forwarding direction, and reply threading.
- **[Risk] SQLite file corruption or accidental deletion** → Mitigation: atomic writes, scheduled backups, retention, restore drill.
- **[Risk] Reduced Telegram command flexibility during V1** → Mitigation: clear command responses that direct operators to the web admin.
- **[Risk] Basic auth limitations** → Mitigation: document V2 RBAC/SSO roadmap and keep auth boundary modular.

## Migration Plan

1. Add DB schema and data-access layer behind `ConfigStore`.
2. Build migration command to import pair config and reply links from existing files.
3. Seed initial admin web user through bootstrap command/env.
4. Deploy with `USE_DB_CONFIG=false` and run migration in dry-run and real modes.
5. Enable `USE_DB_CONFIG=true` and restart service.
6. Validate forwarding and reply-thread mapping with smoke tests.
7. Disable mutating Telegram commands (or return read-only notice).

Rollback:
1. Set `USE_DB_CONFIG=false`.
2. Restart bot to return to file-backed behavior.
3. Investigate DB path and rerun migration/cutover when safe.

## Open Questions

- Should `stats` remain JSON in V1 or move to DB as part of the same cutover?
- Should the web admin support two admin accounts by default at bootstrap?
- What backup schedule should be default for production (daily only vs daily + weekly)?
