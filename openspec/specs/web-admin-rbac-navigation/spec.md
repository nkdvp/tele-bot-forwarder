## Purpose

Define role-aware navigation and pair action visibility rules for the web admin UI while preserving backend authorization as the source of truth.

## Requirements

### Requirement: Role-aware navigation visibility
The web admin UI SHALL render navigation items based on effective global role permissions so users only see destinations they are allowed to access.

#### Scenario: Non-admin user does not see admin-only navigation
- **WHEN** an authenticated user with global role `user` opens any authenticated web admin page
- **THEN** the sidebar does not render links for Backups, Users, or Teams

#### Scenario: Admin user sees admin-only navigation
- **WHEN** an authenticated user with global role `admin` or `super_admin` opens an authenticated web admin page
- **THEN** the sidebar renders links for Backups, Users, and Teams

### Requirement: Pair action controls reflect team write permissions
The pair list and pair edit UI SHALL only render mutation controls for teams that the current user can write.

#### Scenario: Viewer sees read-only pair controls
- **WHEN** an authenticated user can view a pair but lacks write permission to its team
- **THEN** the UI hides or disables mutation controls such as enabled toggle, delete actions, and mask mutation actions for that pair

#### Scenario: Manager or owner sees writable pair controls
- **WHEN** an authenticated user has write permission for the pair's team
- **THEN** the UI renders enabled toggle, delete actions, and mask mutation actions for that pair

### Requirement: Authorization and visibility remain consistent
The system SHALL maintain backend authorization checks even when UI hides restricted navigation and controls.

#### Scenario: Direct request to restricted admin route by non-admin
- **WHEN** a user with global role `user` directly requests `/backups`, `/users`, or `/teams`
- **THEN** the request is denied by backend authorization and no protected operation is executed
