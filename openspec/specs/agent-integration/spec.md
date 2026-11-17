# agent-integration Specification

## Purpose

`AGENTS.md` is a shared convention file that other agents, tools, and humans read, unlike `.corvee/`'s self-contained, git-ignored footprint. Whether a project adopts corvee's guidance there is a human decision, so `corvee init` prints pointer blocks for a human to paste in and never writes them.

## Requirements

### Requirement: `init` never writes `AGENTS.md`
`corvee init` SHALL NOT write to `AGENTS.md` and SHALL NOT create one, whether or not one exists. It SHALL NOT inspect `AGENTS.md` at all.

#### Scenario: Existing AGENTS.md untouched
- **WHEN** `corvee init` runs in a directory with an `AGENTS.md`
- **THEN** the file's content is unchanged

#### Scenario: No AGENTS.md created
- **WHEN** `corvee init` runs in a directory without an `AGENTS.md`
- **THEN** no `AGENTS.md` exists afterward

### Requirement: `init` prints two pointer blocks
Every `corvee init` run SHALL print two Markdown blocks headed `## Task tracking and facts (corvee)`, unconditionally and identically, for a human to paste. With `-o json` they SHALL be the keys `agents_block_local` and `agents_block_global`.

#### Scenario: Re-run prints again
- **WHEN** `corvee init -o json` runs twice in one project
- **THEN** both runs return identical `agents_block_local` and `agents_block_global` values

### Requirement: The local block states this project uses corvee
`agents_block_local` SHALL be for this project's own `AGENTS.md`. It SHALL say the project tracks tasks and facts with `corvee`, tell the reader to identify with `corvee --actor agent:claude --session-id <token> <command>` (or the `CORVEE_ACTOR` and `CORVEE_SESSION_ID` variables, which the flags override), and tell the reader to run `corvee explain` before anything else.

#### Scenario: Identity guidance
- **WHEN** `corvee init -o json` runs
- **THEN** `agents_block_local` mentions `--actor`, `--session-id`, and `corvee explain`

### Requirement: Both blocks set a fact discipline
Both blocks SHALL tell the reader to check `corvee fact search` for an existing `verified` fact before asserting something uncertain, and to mark a fact `verified` only when `--proof` names something reproducible, such as a command's output, a test run, or a file and line. A fact that cannot be backed that way stays `unverified`.

#### Scenario: Proof guidance
- **WHEN** `corvee init -o json` runs
- **THEN** both blocks mention `corvee fact search` and `--proof`

### Requirement: The global block assumes nothing about the project
`agents_block_global` SHALL carry the same guidance for a cross-project config such as `~/.claude/CLAUDE.md`, but SHALL drop "this project" and "this codebase" framing. It SHALL tell the reader to check for `.corvee/config.toml`, or run `corvee doctor`, before assuming the current project uses corvee.

#### Scenario: Global framing
- **WHEN** `corvee init -o json` runs
- **THEN** `agents_block_global` mentions `.corvee/config.toml` and `corvee doctor` and does not say "This project tracks"

### Requirement: Blocks are pointers
Both blocks SHALL be pointers and not a full instruction set. Volatile detail such as exact commands and flags SHALL live in `corvee explain`, which ships with the code and stays current, and not in text frozen wherever it is pasted.

#### Scenario: Detail deferred
- **WHEN** `corvee init` prints the blocks
- **THEN** each points at `corvee explain` for the full usage guide
