# pair-config-store

## Purpose
Define how active forwarding pairs are persisted and validated in the database-backed configuration store.

## Requirements

### Requirement: Bot reads active pair configuration from database store
The system SHALL resolve active forwarding pairs from the database-backed configuration store when DB mode is enabled.

#### Scenario: DB mode enabled
- **WHEN** runtime configuration indicates DB-backed mode is enabled
- **THEN** pair lookup for forwarding uses persisted DB records as the source of truth

#### Scenario: Pair disabled in store
- **WHEN** a pair is marked disabled in the configuration store
- **THEN** messages from that pair are not forwarded

### Requirement: Configuration store enforces pair identity constraints
The system SHALL enforce unique pair names and valid pair chat ID structure at persistence boundaries.

#### Scenario: Duplicate pair name rejected
- **WHEN** an operation attempts to create a pair with an existing pair name
- **THEN** the system rejects the write with a validation error

#### Scenario: Invalid chat identifiers rejected
- **WHEN** an operation attempts to store non-numeric or malformed chat IDs
- **THEN** the system rejects the write and does not mutate persisted configuration
