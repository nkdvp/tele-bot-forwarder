# database-backup-operations

## Purpose
Describe scheduled and manual database backup behavior, including retention cleanup.

## Requirements

### Requirement: System supports scheduled database backups with retention
The system SHALL create scheduled backups of the SQLite database and SHALL enforce a retention policy for old backup files.

#### Scenario: Scheduled backup run succeeds
- **WHEN** the scheduled backup job executes
- **THEN** the system creates a timestamped backup artifact in the configured backup location

#### Scenario: Retention cleanup runs
- **WHEN** backups exceed configured retention limits
- **THEN** the system removes expired backup artifacts and keeps only retained backups

### Requirement: System supports manual backup trigger
The system SHALL provide an operator-invokable manual backup operation.

#### Scenario: Manual backup trigger
- **WHEN** an authenticated admin triggers manual backup
- **THEN** the system creates a new backup artifact and reports operation result
