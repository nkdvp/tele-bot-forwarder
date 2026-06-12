# file-to-db-migration

## Purpose
Define migration and cutover behavior for moving from file-backed pair/reply-link data to database-backed storage.

## Requirements

### Requirement: Migration imports pair config and reply links from files
The system SHALL provide a migration command that imports pair configuration and reply-link data from existing file-based artifacts into the database.

#### Scenario: Import from existing files
- **WHEN** migration runs with valid `config.yaml` and `data/reply_map.json` inputs
- **THEN** the system persists equivalent pair records and reply-link records in database tables

#### Scenario: Migration validation failure
- **WHEN** migration input contains invalid records
- **THEN** the system reports validation errors and MUST NOT partially apply invalid records

### Requirement: Runtime supports controlled cutover and rollback
The system SHALL support an explicit runtime switch between file-backed and DB-backed configuration modes.

#### Scenario: Cutover to DB mode
- **WHEN** the runtime DB mode flag is enabled after successful migration
- **THEN** the system reads pair configuration from database on startup

#### Scenario: Rollback to file mode
- **WHEN** the runtime DB mode flag is disabled
- **THEN** the system resumes file-backed configuration behavior after restart
