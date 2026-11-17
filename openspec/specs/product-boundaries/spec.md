# product-boundaries Specification

## Purpose

corvee is a single-machine, persistent CLI task tracker for people and AI agents working on one project, including several of them at once. It keeps a session from losing context and keeps two workers from colliding mid-task. It also holds a small store of checked-true facts, so a later session can retrieve a claim that was verified once instead of re-deriving it. This capability states what corvee deliberately does not do.

## Requirements

### Requirement: Single-machine concurrency scope
corvee SHALL support concurrent use by multiple agents and humans on one machine and filesystem (separate terminals, processes, or git worktrees). It SHALL NOT provide hosted sync or access from machines without a shared filesystem.

Supporting such machines would require revisiting the connection model before anything else.

#### Scenario: Two worktrees on one machine
- **WHEN** two git worktrees on the same machine point their `db_path` at one database file
- **THEN** both see and update the same backlog without a server process

### Requirement: Task data stays out of git
The SQLite database holding tasks and facts SHALL NOT be committed to git. Only the small, non-sensitive project-binding file MAY live in a repository.

#### Scenario: Default init output
- **WHEN** a user runs `corvee init` in a directory with a `.gitignore`
- **THEN** `.corvee/` is ignored, so neither the binding file nor the database is committed

### Requirement: No server, interface, or automation layer
corvee SHALL NOT include a web UI, notifications, or built-in scheduling or automation. The CLI SHALL run each command as a single connect-do-work-close invocation with no background process. The MCP server (see `mcp-process-model`) is the one deliberate exception, a stdio subprocess a host opts into per session.

#### Scenario: CLI leaves nothing running
- **WHEN** any `corvee task` or `corvee fact` command finishes
- **THEN** no corvee process remains running and no daemon is required for the next command
