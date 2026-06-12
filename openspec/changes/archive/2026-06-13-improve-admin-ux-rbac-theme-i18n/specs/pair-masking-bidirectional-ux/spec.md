## ADDED Requirements

### Requirement: Masking list presents one logical mapping per user
The pair masking UI SHALL present one row per masked Telegram user showing the masked output, even when storage keeps directional records.

#### Scenario: Bidirectional directional records render as one row
- **WHEN** both `a_to_b` and `b_to_a` mask rows exist for the same pair and Telegram user ID
- **THEN** the pair edit masking table renders one logical row for that user mapping instead of two directional rows

### Requirement: Direction is not required in masking UX
The pair masking UI SHALL not require operators to choose or read direction for pair-level masking where policy enforces bidirectional behavior.

#### Scenario: Operator creates a mask from pair UI
- **WHEN** an operator submits a mask in pair edit UI
- **THEN** the form captures user ID and masking output fields without any direction input

### Requirement: Pair-level masking writes remain bidirectionally consistent
Pair-level masking writes initiated from web UI SHALL create or update both directional records for the same user with equivalent mode and alias semantics.

#### Scenario: Alias mask save from UI
- **WHEN** an operator saves an alias mask for a Telegram user in pair edit UI
- **THEN** the system persists matching `a_to_b` and `b_to_a` rules for that pair and user

#### Scenario: Anonymous mask save from UI
- **WHEN** an operator saves an anonymous mask for a Telegram user in pair edit UI
- **THEN** the system persists matching `a_to_b` and `b_to_a` anonymous rules with no alias value

### Requirement: Logical mask deletion removes both directional rules
Deleting a logical pair-level mask mapping from UI SHALL remove all directional records for that pair and Telegram user.

#### Scenario: Delete mapping from masking table
- **WHEN** an operator clicks delete for a masking row in pair edit UI
- **THEN** both `a_to_b` and `b_to_a` mask records for that pair and user are removed
