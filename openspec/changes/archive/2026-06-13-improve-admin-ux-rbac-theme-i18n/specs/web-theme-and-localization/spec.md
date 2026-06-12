## ADDED Requirements

### Requirement: Vietnamese is the default web locale
The web admin UI SHALL default to Vietnamese locale when no explicit language preference has been saved for the current browser session context.

#### Scenario: First visit without language preference
- **WHEN** an authenticated user opens the web admin with no stored locale preference
- **THEN** page labels and messages are rendered in Vietnamese

### Requirement: User can switch UI language
The web admin UI SHALL provide a language switch control that allows users to change between Vietnamese and English.

#### Scenario: User switches language to English
- **WHEN** the user selects English in the language switch control
- **THEN** subsequent rendered pages use English strings

#### Scenario: Language preference persists
- **WHEN** a user has selected a language and navigates or refreshes within the admin web
- **THEN** the selected language remains active until changed again

### Requirement: User can switch between dark and light theme
The web admin UI SHALL provide a theme switch control with at least dark and light modes.

#### Scenario: User selects light mode
- **WHEN** the user selects light theme in the theme switch control
- **THEN** the UI applies the light theme token set on the current page

#### Scenario: Theme preference persists
- **WHEN** a user has selected a theme and navigates or refreshes within the admin web
- **THEN** the selected theme remains active until changed again

### Requirement: Client-side status messages follow active locale
User-facing client-side feedback text in admin web SHALL be localized according to the active locale.

#### Scenario: Localized toast in Vietnamese
- **WHEN** the active locale is Vietnamese and a UI action triggers a success or error toast
- **THEN** the toast message is displayed in Vietnamese
