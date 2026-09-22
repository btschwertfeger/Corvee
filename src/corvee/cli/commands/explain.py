#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

EPILOG = """\
\b
Examples:
Print the cheat sheet:
  corvee explain
Page through it if the terminal is too short:
  corvee explain | less
Save it as a file an agent can be pointed at directly:
  corvee explain > AGENTS_corvee_cheatsheet.txt
"""

EXPLAIN_TEXT = """\
corvee: a single-machine, non-git-tracked, persistent, multi-agent-aware
CLI task tracker, plus a standalone store of checked-true facts. Multiple
agents and humans can work the same backlog concurrently — claims prevent
two actors from editing the same task at once.

Operating rule, not an example to adapt: track work as you go, never after
the fact. This applies to any nontrivial piece of work, not just code — a
research task, a writeup, a document review, anything worth resuming.
Before starting, `task add` it (with --description) and `task claim` it —
filing a task once the work is already done gives a resuming session
nothing to resume from, which is the one thing this tool exists to
prevent. The same applies to facts: `fact add`/`fact verify` a claim the
moment you establish it (from research, a source, a computed result — not
only code), not batched in at the end of a session.

TASKS

One task per independently-resolvable item, not one umbrella task: a
batch of distinct, separately-finishable pieces (a batch of FIXMEs, a
list of bugs) gets one `task add` each. Bundling them loses corvee's
resumability and independent-completion value — no way to tell which
piece is actually done, no way to split the batch across agents.

Resuming beats starting something new:
  corvee brief --json                           # mine + ready + stale in one call
  corvee task mine --json                       # what am I already working on?

Check before you file, and see what's startable right now:
  corvee task ready --json                      # unclaimed, unblocked, open tasks
  corvee task search "auth token" --json        # does a task for this exist already?
  corvee task list --fields id,title --json     # cheap session-start overview

File it, claim it, then work it — in that order, every time. Don't skip
steps: stay in_progress while working, comment before marking done — a
task with no claim and no comment leaves nothing for a resuming session
(yours or another agent's) to pick up from.
  corvee task add "Fix the flaky auth test" --description "..." --json
  corvee task claim TASK-14 --json
  corvee task update TASK-14 --state in_progress --json
  corvee task comment TASK-14 "found the root cause, writing a fix" --json
  corvee task update TASK-14 --state done --json
  corvee task show TASK-14 --json             # full detail, incl. the timeline

Don't leave every task at the --type/--priority defaults (task/medium)
when a more specific one is true: a bug found along the way is
--type bug, something genuinely blocking is --priority high or
critical, and a task that can't start until another finishes is a
relation, not just a sentence in the description:
  corvee task link TASK-15 TASK-14 --relation blocks --json

Claims: `corvee task claim <id>` fails if another actor holds the task,
unless --force. Re-running `corvee task claim <id>` on a task already held
refreshes it — the heartbeat. A claim goes stale after 4h of silence and can
then be taken by another agent (see `corvee task list --stale`). See who
currently holds what, and since when:
  corvee task claims --json

Routing work to a specific actor without claiming it on their behalf:
  corvee task assign TASK-14 --to agent:claude --json
`task mine` then shows it for agent:claude the moment it's unclaimed.

FACTS

Facts are a separate, standalone store for checked-true claims with proof —
not tasks, and not linked to them by the schema. Connect the two by
convention if useful, e.g. mentioning a fact id in a task comment:
  corvee fact add "requests is Apache-2.0 licensed" --json --proof \\
    "pip download requests --no-deps -d /tmp && unzip -q /tmp/requests-*.whl -d /tmp/requests-whl \\
    && grep -i '^License:' /tmp/requests-whl/*/METADATA"
  corvee fact search "license" --json           # does a fact for this exist already?

GENERAL

Not project-specific? --global on task/fact add files into one database
shared across every project on the machine instead of this one. Every
other command reads local vs. global from the id itself (TASK-GLOBAL-<n>),
so --global is only ever needed on add:
  corvee task add "renew the CA cert" --description "expires yearly" --global --json
  corvee task list --scope local --json         # this project's backlog only, not merged

Identity: corvee --actor agent:claude --session-id <token> <command> on
every call — passing the flags keeps the command line a plain `corvee ...`
invocation a permission allowlist can match, instead of an `export`
beforehand, which usually needs broader permissions. No --actor given
defaults to human:$USER. Set it explicitly whenever more than one session
might touch this backlog at once: two unconfigured sessions on the same
machine share that identity, and claims stop protecting anything between
them. corvee doctor flags a claimed task with recent activity from more
than one session under one actor string, which is what that collision
looks like after the fact.

Always pass --json, except on explain, completion, and mcp serve (no
--json flag) and export (already emits JSON, no flag needed). Success is
a JSON array of objects on stdout, or a single object for brief, doctor,
init, and task tree. Failure is an object on stderr:
{"error": {"code": ..., "message": ...}}.

Full flag reference for any command: corvee <command> --help
"""


@click.command(epilog=EPILOG)
def explain() -> None:
    """Print a compact, agent-oriented cheat sheet."""
    click.echo(EXPLAIN_TEXT)
