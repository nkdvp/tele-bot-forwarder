## ADDED Requirements

### Requirement: Admin can list and search forwarding pairs
The system SHALL provide a pair listing interface and API that supports filtering by pair name, chat ID, enabled state, and directionality.

#### Scenario: Search by pair name
- **WHEN** an authenticated admin searches with a partial pair name
- **THEN** the system returns only pairs whose names match the query

#### Scenario: Filter by enabled state
- **WHEN** an authenticated admin filters pairs by enabled status
- **THEN** the system returns only pairs with the selected enabled value

### Requirement: Admin can create and update pair definitions
The system SHALL allow authenticated admins to create and update pair definitions including chat IDs, directionality, enablement, and filter settings.

#### Scenario: Create new pair
- **WHEN** an authenticated admin submits a valid new pair payload
- **THEN** the system persists the pair and it appears in subsequent list responses

#### Scenario: Update existing pair
- **WHEN** an authenticated admin updates an existing pair configuration
- **THEN** the system persists the changes and exposes updated values in reads

### Requirement: Admin can remove pair definitions
The system SHALL allow authenticated admins to delete an existing pair definition.

#### Scenario: Delete pair
- **WHEN** an authenticated admin requests deletion for an existing pair
- **THEN** the system removes the pair and it no longer appears in list/search results
