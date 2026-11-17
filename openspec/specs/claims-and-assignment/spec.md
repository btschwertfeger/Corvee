# claims-and-assignment Specification

## Purpose

Defines how corvee identifies the caller, how a claim records that an actor is working on a task right now, and how a task can be routed to an actor without asserting anyone is working on it. Claims are the mechanism that keeps two actors from editing one task at once.

## Requirements

### Requirement: Actor is the stable caller identity
The actor SHALL be the stable identity of an agent or human, such as `agent:claude` or `human:btschwertfeger`, unchanged across restarts and sessions. If unset, the actor SHALL default to `human:$USER`.

#### Scenario: Interactive default
- **WHEN** neither `--actor` nor `CORVEE_ACTOR` is set and `corvee task claim TASK-1` runs as user `ada`
- **THEN** the claim is held by `human:ada`

### Requirement: Session id is volatile and optional
The session id SHALL be an optional per-session token such as `claude-session-7`, defaulting to NULL. corvee SHALL stamp it onto every `task_events` and `fact_events` row an invocation writes, comments and field changes alike.

#### Scenario: Session recorded
- **WHEN** `corvee --session-id s1 task comment TASK-1 "note"` runs
- **THEN** the new event row has `session_id` `s1`

### Requirement: Flags override environment variables
The global `--actor` and `--session-id` options (given before the subcommand) SHALL take precedence over `CORVEE_ACTOR` and `CORVEE_SESSION_ID`. Both mechanisms SHALL resolve to the same values in every command, including `task mine`.

The flags keep a command a plain `corvee ...` invocation that a permission allowlist can match.

#### Scenario: Flag beats environment
- **WHEN** `CORVEE_ACTOR=agent:a` is set and `corvee --actor agent:b task claim TASK-1` runs
- **THEN** the claim is held by `agent:b`

### Requirement: Claims key off the actor only
Claims SHALL identify the claimant by actor and never by session id, so an agent whose session dies reclaims its own task on the next run as a no-op success, and `task list --claimed-by agent:claude` still finds it after a restart.

#### Scenario: Resume after restart
- **WHEN** `agent:claude` claimed `TASK-1` in one session and claims it again in a new session
- **THEN** the claim succeeds without `--force`

### Requirement: Unconfigured sessions share one identity
corvee SHALL NOT invent a substitute identity for the `human:$USER` fallback. Two sessions on one machine that both skip `CORVEE_ACTOR` therefore resolve to the same actor, and the second session's claim looks like the first actor's own repeat claim. `doctor` SHALL detect this collision after the fact (see `project-health`).

#### Scenario: Two sessions, one actor
- **WHEN** two sessions with no `CORVEE_ACTOR` both claim `TASK-1`
- **THEN** both calls succeed

### Requirement: A claim means active work
A claim SHALL mean an actor is working on the task right now. It is not an assignment, a reservation, or an ownership record. `task add` SHALL NOT claim the task it creates. An actor that stops without finishing SHALL release the claim with `task unclaim`.

#### Scenario: Add does not claim
- **WHEN** `corvee task add "x" --description "y" -o json` runs
- **THEN** the returned task has `claimed_by` null

### Requirement: Claiming is atomic
`corvee task claim <id> [<id> ...]` SHALL set `claimed_by` to the actor and `claimed_at` to now with a single conditional `UPDATE ... WHERE claimed_by IS NULL`, checked by rows affected. Multiple ids SHALL apply in one transaction, all-or-nothing.

#### Scenario: Two processes race
- **WHEN** two processes claim the same unclaimed task at once
- **THEN** exactly one succeeds and the other exits 4

### Requirement: Claim conflicts and force
Claiming a task held by a different actor SHALL fail with a claim conflict (exit 4) unless `--force` is given. `--force` SHALL steal the claim and record the previous claimant in `task_events`. A repeat claim by the current claimant SHALL succeed and refresh `claimed_at`.

#### Scenario: Conflict without force
- **WHEN** `agent:a` holds `TASK-1` and `agent:b` runs `corvee task claim TASK-1`
- **THEN** the exit code is 4 and the error carries `claimed_by` `agent:a`

#### Scenario: Forced steal
- **WHEN** `agent:b` runs `corvee task claim TASK-1 --force`
- **THEN** the claim is held by `agent:b` and `task_events` records `agent:a` as the previous claimant

### Requirement: Terminal tasks cannot be claimed
Claiming a task in `done` or `cancelled` SHALL fail with a guard violation (exit 5, error code `task_terminal`), `--force` included, since `--force` only overrides a conflicting claimant.

#### Scenario: Claim a done task
- **WHEN** `corvee task claim TASK-1 --force` runs on a `done` task
- **THEN** the exit code is 5 with error code `task_terminal`

### Requirement: Unclaim releases a claim
`corvee task unclaim <id> [<id> ...]` SHALL clear `claimed_by` and `claimed_at`. Only the current claimant SHALL do this without `--force`. Unclaiming an unclaimed task SHALL be a no-op success. Multiple ids SHALL apply in one transaction, all-or-nothing.

#### Scenario: Foreign unclaim
- **WHEN** `agent:b` runs `corvee task unclaim TASK-1` on a task held by `agent:a`
- **THEN** the exit code is 4

### Requirement: Update is claim-gated
`corvee task update <id>` SHALL fail with a claim conflict (exit 4, message pointing at `--force`) if the task is claimed by a different actor.

#### Scenario: Update a foreign claim
- **WHEN** `agent:b` runs `corvee task update TASK-1 --priority high` on a task held by `agent:a`
- **THEN** the exit code is 4 and the message names `--force`

### Requirement: Updating an unclaimed task takes a transient claim
Updating an unclaimed task SHALL take the claim, apply the change, and release the claim inside one transaction, recording the claim and unclaim pair in `task_events`. A `--state in_progress` update SHALL keep the claim. A `--force` update that steals a claim SHALL follow the same rule, releasing it afterward unless the update set `--state in_progress`. An update that changes nothing SHALL take no claim and write no event.

#### Scenario: Reprioritize without leaving a claim
- **WHEN** `corvee task update TASK-1 --priority high` runs on an unclaimed task
- **THEN** the task is unclaimed afterward and `task_events` holds the claim and unclaim rows

#### Scenario: Starting work keeps the claim
- **WHEN** `corvee task update TASK-1 --state in_progress` runs on an unclaimed task
- **THEN** the task stays claimed by the caller

### Requirement: Only update is claim-gated
`comment`, `label`, `link`, and `unlink` SHALL be open to any actor at any time, since none touches the content a claim guards and a second agent's most useful act on another's task is leaving a note. Facts SHALL have no claim gate.

#### Scenario: Bystander comment
- **WHEN** `agent:b` runs `corvee task comment TASK-1 "note"` on a task held by `agent:a`
- **THEN** the comment is added

### Requirement: `task start` is update to `in_progress`
`corvee task start <id> [<id> ...] [--force]` SHALL behave as `corvee task update <id> --state in_progress [--force]`, following `update`'s claim-conflict (exit 4) and transition (exit 5) rules, including the `done` to `in_progress` transition. It SHALL NOT apply `claim`'s terminal check. Multiple ids SHALL apply in one transaction, all-or-nothing.

#### Scenario: Start a done task
- **WHEN** `corvee task start TASK-1` runs on a `done` task
- **THEN** the task becomes `in_progress` and claimed by the caller

### Requirement: Terminal states clear claims
Reaching `done` or `cancelled` SHALL clear `claimed_by` and `claimed_at` in the same transaction, recorded as a normal `field_change` event.

#### Scenario: Finish a claimed task
- **WHEN** the claimant runs `corvee task update TASK-1 --state done`
- **THEN** the task is unclaimed afterward

### Requirement: `claimed_at` means claim last asserted
`claimed_at` SHALL be refreshed by a repeat `task claim` from the current claimant, by a `task update` from the claimant, and by a `task comment` from the claimant. A comment from any other actor SHALL NOT refresh it. The time a claim was first taken SHALL stay recoverable from the `field_change` row in `task_events`.

#### Scenario: Bystander comment does not refresh
- **WHEN** `agent:b` comments on a task held by `agent:a`
- **THEN** `claimed_at` is unchanged

### Requirement: Claims never expire but staleness is surfaced
Claims SHALL NOT expire on their own, and there SHALL be no TTL or heartbeat process. `corvee task list --stale [<duration>]` SHALL list tasks whose `claimed_at` is older than the duration, defaulting to `4h`, as the input to a deliberate `claim --force`.

#### Scenario: Stale listing
- **WHEN** a task was last claimed or touched by its claimant five hours ago and `corvee task list --stale` runs
- **THEN** the task is listed

### Requirement: Assignment routes without claiming
`corvee task assign <id> [<id> ...] --to <actor>` SHALL set `assigned_to` and `corvee task unassign <id> [<id> ...]` SHALL clear it, each in one transaction across all ids. Neither SHALL be claim-gated, and assigning SHALL NOT claim the task. Reassigning SHALL overwrite the previous value with no history check, and every change SHALL be recorded as a `field_change` event. Assigning to the actor already assigned, or unassigning an unassigned task, SHALL be a no-op success.

#### Scenario: Assign a claimed task
- **WHEN** `corvee task assign TASK-1 --to agent:b` runs on a task claimed by `agent:a`
- **THEN** `assigned_to` is `agent:b` and the claim is unchanged
