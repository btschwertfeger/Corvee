# Quickstart

## Install

```bash
uv tool install corvee
```

## Set up a project

Run once per project, from the project root:

```bash
corvee init
```

This creates `.corvee/config.toml` (analogous to `.git`) and adds `.corvee/`
to `.gitignore`. It also prints two short pointer blocks: one to paste into
this project's own `AGENTS.md`, and one worded for a global agents config
such as `~/.claude/CLAUDE.md`, to apply across every project instead. The
task database itself (`.corvee/corvee.db`) is never committed. It is local,
per-machine state, the same way `.git/` on its own is not the thing you
push.

## Identify yourself

Two values identify the caller: a stable actor, unchanged across sessions,
and an optional per-session token. Set them with global flags, before the
subcommand:

```bash
corvee --actor agent:claude --session-id session-42 task list --json
```

or with environment variables, which the flags override when both are
present:

```bash
export CORVEE_ACTOR=agent:claude
export CORVEE_SESSION_ID=session-42
```

The flags exist for agent harnesses with a permission allowlist that
matches on the literal command text (e.g. anything starting with `corvee`):
`CORVEE_ACTOR=... corvee task list` or `export CORVEE_ACTOR=... && corvee
task list` doesn't start with `corvee`, so a `corvee ...` allowlist rule
never matches it, forcing manual approval on every call. The flag form
does start with `corvee`, so it does.

If neither is set, the actor defaults to `human:$USER`, so interactive
shell use needs no setup.

## The core loop

```bash
corvee task mine --json                             # what am I already working on?
corvee task ready --json                             # what could I start right now?
corvee task search "auth token" --json               # does a task for this exist already?
corvee task add "Fix the flaky auth test" --description "..." --json  # file one if not
corvee task claim TASK-14 --json                     # start it
corvee task update TASK-14 --state in_progress --json
corvee task comment TASK-14 "found the root cause" --json
corvee task update TASK-14 --state done --json       # finish it, claim clears automatically
```

Every command accepts `--json` (except `explain`) and, on success, prints a
JSON array of objects to stdout. On failure, nothing is written to stdout
and a JSON error object goes to stderr instead, so a caller can parse
stdout unconditionally.

## What the output looks like

Without `--json`, mutating commands print a fixed-width table of the
affected row(s):

```
$ corvee task add "Fix the flaky auth test" --description "Retry logic in test_auth.py::test_login_retry is racy under load"
ID      TITLE                    TYPE  PRIORITY  STATE  CLAIMED_BY  CLAIMED_AT  ASSIGNED_TO  CREATED_AT                UPDATED_AT                SCOPE
TASK-1  Fix the flaky auth test  task  medium    open   None        None        None         2026-09-15T06:28:27.641Z  2026-09-15T06:28:27.641Z  local
```

`task show` prints the full record instead, including every claim, state
change, and comment against it, in order, under `events:`. This is the
audit trail a later session (or a different agent entirely) reads instead
of re-deriving what happened:

```
$ corvee task show TASK-1
id: TASK-1
title: Fix the flaky auth test
type: task
priority: medium
state: done
claimed_by: None
claimed_at: None
assigned_to: None
created_at: 2026-09-15T06:28:27.641Z
updated_at: 2026-09-15T06:28:27.810Z
scope: local

description:
Retry logic in test_auth.py::test_login_retry is racy under load

labels: (none)
links: (none)
subtasks: (none)
referenced: (none)
events:
  2026-09-15T06:28:27.683Z  agent:claude  field_change  claimed_by: None -> agent:claude
  2026-09-15T06:28:27.725Z  agent:claude  field_change  claimed_at: 2026-09-15T06:28:27.683Z -> 2026-09-15T06:28:27.725Z
  2026-09-15T06:28:27.725Z  agent:claude  field_change  state: open -> in_progress
  2026-09-15T06:28:27.768Z  agent:claude  comment  Root cause: the retry loop doesn't back off, so it hammers the endpoint before the rate limiter resets.
  2026-09-15T06:28:27.810Z  agent:claude  field_change  claimed_at: 2026-09-15T06:28:27.769Z -> 2026-09-15T06:28:27.810Z
  2026-09-15T06:28:27.810Z  agent:claude  field_change  state: in_progress -> done
  2026-09-15T06:28:27.810Z  agent:claude  field_change  claimed_by: agent:claude -> None
```

Facts follow the same two shapes. `fact add --proof` verifies immediately;
`fact show` carries the proof and its own `events:` trail:

```
$ corvee fact add "requests is Apache-2.0 licensed" --proof "pip show requests | grep License"
ID      CLAIM                            STATUS    VERIFIED_AT               VERIFIED_BY   CREATED_AT                UPDATED_AT                SCOPE
FACT-1  requests is Apache-2.0 licensed  verified  2026-09-15T06:28:27.892Z  agent:claude  2026-09-15T06:28:27.892Z  2026-09-15T06:28:27.892Z  local

$ corvee fact show FACT-1
id: FACT-1
claim: requests is Apache-2.0 licensed
status: verified
verified_at: 2026-09-15T06:28:27.892Z
verified_by: agent:claude
created_at: 2026-09-15T06:28:27.892Z
updated_at: 2026-09-15T06:28:27.892Z
scope: local

proof:
pip show requests | grep License

referenced: (none)
events:
  2026-09-15T06:28:27.892Z  agent:claude  created  requests is Apache-2.0 licensed
  2026-09-15T06:28:27.892Z  agent:claude  verified  proof: pip show requests | grep License
```

## Recording a checked-true fact

Separately from tasks, corvee holds a standalone store of checked-true
claims (a place to record something as verified, with proof and a date), so
an agent can retrieve it later instead of re-deriving or hallucinating it:

```bash
corvee fact search "license" --json    # does a fact for this exist already?
corvee fact add "requests is Apache-2.0 licensed" --json --proof \
  "pip download requests --no-deps -d /tmp && unzip -q /tmp/requests-*.whl -d /tmp/requests-whl \
  && grep -i '^License:' /tmp/requests-whl/*/METADATA"
corvee fact verify FACT-1 --json --proof \
  "pip download requests --no-deps -d /tmp && unzip -q /tmp/requests-*.whl -d /tmp/requests-whl \
  && grep -i '^License:' /tmp/requests-whl/*/METADATA"   # re-verify later
```

Facts are not linked to tasks by the schema. Mention a fact's id in a task
comment if you want to connect the two.

## Tasks and facts that aren't project-specific

`--global` files a task or fact into one database shared across every
project on the machine (`~/.corvee/corvee.db`), created on first use, with
no extra setup:

```bash
corvee task add "renew the CA cert" --description "expires yearly" --global --json
corvee task list --json                    # merges local and global by default
corvee task list --scope local --json      # this project's backlog only
```

Every id-based command (`claim`, `show`, `update`, ...) works on a global
id exactly the same as a local one. `TASK-GLOBAL-<n>`/`FACT-GLOBAL-<n>`
in the response tells you which database it came from, so `--global` is
only ever needed on `add`.

## Learn the rest

```bash
corvee explain          # an ~85-line cheat sheet, no DB access needed
corvee <command> --help # full flag reference with runnable examples
```

## Shell completion

```bash
eval "$(corvee completion bash)"   # or zsh / fish; add to your shell's rc file to keep it
```

Completes subcommands, flags, `--state`/`--priority`/`--type` choices, and
`TASK-<n>`/`FACT-<n>` arguments against real ids in the current project.
