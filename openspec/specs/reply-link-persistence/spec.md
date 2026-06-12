# reply-link-persistence

## Purpose
Specify how forwarded-message reply links are persisted and resolved bidirectionally from the database.

## Requirements

### Requirement: Reply links are persisted bidirectionally in database
The system SHALL persist reply link mappings in both directions so that cross-group replies can resolve from either side.

#### Scenario: Record forwarded message mapping
- **WHEN** a message is forwarded from source group to destination group
- **THEN** the system stores a source-to-destination link and a destination-to-source link

#### Scenario: Update existing mapping for same source
- **WHEN** a mapping is recorded for an existing source message with a different destination
- **THEN** the system updates link consistency so lookup returns only the current mapping pair

### Requirement: Reply lookup resolves destination reply target
The system SHALL resolve destination reply target IDs from persisted mappings during forwarding.

#### Scenario: Mapped reply exists
- **WHEN** a forwarded message replies to a source message that has a stored mapping
- **THEN** the system sets reply target on the destination message to the mapped destination message ID

#### Scenario: No mapping exists
- **WHEN** a forwarded reply references a source message with no persisted mapping
- **THEN** the system forwards without a reply target and continues processing
