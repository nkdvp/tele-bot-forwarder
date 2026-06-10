## 1. Persistence foundation

- [x] 1.1 Add SQLite schema and migrations for pairs, pair filters, reply links, users, and sessions
- [x] 1.2 Implement a `ConfigStore` interface and SQLite-backed repository methods for pair read/write and search
- [x] 1.3 Implement SQLite-backed reply-link store with bidirectional record/update lookup behavior
- [x] 1.4 Add configuration flagging (`USE_DB_CONFIG`) and dependency wiring to choose file-backed vs DB-backed stores at runtime

## 2. Migration and cutover safety

- [x] 2.1 Build migration command to import pair definitions from `config.yaml` into DB tables with validation
- [x] 2.2 Build migration command to import reply links from `data/reply_map.json` into DB tables with validation
- [x] 2.3 Add dry-run mode and structured error reporting to migration flows
- [x] 2.4 Add rollback runbook and startup behavior for switching back to file mode

## 3. Bot integration changes

- [x] 3.1 Update bot pair lookup path to consume `ConfigStore` when DB mode is enabled
- [x] 3.2 Update forwarding reply lookup/record path to consume DB-backed reply-link persistence
- [x] 3.3 Disable or convert mutating Telegram commands to read-only guidance for V1 single-write-path safety
- [x] 3.4 Add integration tests validating forwarding parity, enable/disable behavior, and reply threading in DB mode

## 4. Web authentication and session management

- [x] 4.1 Implement login/logout endpoints and password-hash verification for admin users
- [x] 4.2 Implement server-side session creation, validation middleware, and session invalidation on logout
- [x] 4.3 Protect all admin routes and APIs with authentication checks and redirect/error behavior
- [x] 4.4 Add tests for unauthenticated access, successful login, and logout invalidation

## 5. Web pair management and search

- [x] 5.1 Implement pairs list API with filters for name, chat ID, enabled state, and directionality
- [x] 5.2 Implement pair create/update/delete APIs with validation and unique-name enforcement
- [x] 5.3 Build web pages/forms for pair list, create, and edit flows using authenticated APIs
- [x] 5.4 Add end-to-end tests for pair CRUD and search/filter behavior

## 6. Backup operations and operational hardening

- [x] 6.1 Implement scheduled SQLite backup job with timestamped artifacts and retention cleanup
- [x] 6.2 Implement manual backup trigger endpoint/action for authenticated admins
- [x] 6.3 Add backup/restore validation script and operational documentation
- [x] 6.4 Execute final smoke tests for migration, cutover, rollback, and backup flows before rollout
