# Spec Delta

## MODIFIED Requirements

### Requirement: `brief` takes only a scope
`brief` SHALL accept an optional `scope` and nothing else, and SHALL behave as `corvee brief` (see `session-brief`), including its caps of 5 `ready` rows and 5 `facts` rows.

#### Scenario: No arguments
- **WHEN** `brief` is called with no arguments
- **THEN** it returns the `mine`, `ready`, `stale`, `facts`, and `labels` sections
