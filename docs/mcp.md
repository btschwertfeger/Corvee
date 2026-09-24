# MCP server

The CLI stays the primary interface. The MCP server is a second, additive
surface for hosts that speak MCP natively but expose no shell/exec tool to
the agent (Claude Desktop outside of Code, several IDE-integrated
assistants), and for subagent-to-subagent handoffs where brokering every
call through a parent agent's shell is itself the friction. Use the CLI
directly whenever your harness already shells out to `corvee ...`; reach
for the MCP server only when it can't.

## Install

The MCP dependency is an optional extra, not part of the base install:

```bash
uv tool install 'corvee[mcp]'
```

If `corvee` is already installed without it:

```bash
uv tool install --upgrade 'corvee[mcp]'
```

## Start the server

```bash
corvee mcp serve
```

With no flags at all, this auto-detects a project exactly the way the CLI
does: it walks up from the server's own working directory looking for
`.corvee/config.toml`, the same lookup `corvee task list` does. If your
MCP host lets you set the spawned process's working directory (most host
configs do, via a `cwd` field, or you can wrap the command in `cd
/path/to/your/project && corvee mcp serve`), that's all you need.

If your host doesn't set the working directory correctly — Claude Desktop,
for one, commonly launches from `/` — use `--project-root` as an explicit
override:

```bash
corvee mcp serve --project-root /path/to/your/project
```

`--project-root` is resolved once, at startup, and the server refuses to
start if it's given but doesn't resolve to a valid project. Auto-detection
never fails that hard: if nothing is found at cwd, the server falls back
to global-only mode below instead of refusing to start.

Either way, the server prints one line to stderr naming what it resolved
(the project's path, or that it's in global-only mode) before it starts
accepting calls, and folds the same into the `instructions` it hands the
MCP client. Neither touches stdout, which stays pure JSON-RPC framing.

`--actor` works like the CLI's own `--actor` flag or `$CORVEE_ACTOR` (see
[Quickstart](quickstart.md#identify-yourself)): a stable identity for
whatever is running this server, read once at startup.

```bash
corvee mcp serve --actor agent:claude
```

`--session-id` (or `$CORVEE_SESSION_ID`) sets the server's default
session id, used by any write tool call that leaves out its own
`session_id` argument. Omit both and the server mints one itself, unique
to that process — every write tool still has something to stamp on the
events it writes even if you never touch this flag.

```bash
corvee mcp serve --session-id session-42
```

**Run one server process per agent conversation.** A single process can
technically outlive one conversation, but everything it writes shares one
actor identity for as long as it's alive — two unrelated conversations
sharing a process share claim ownership, the same collision two people
sharing one `$CORVEE_ACTOR` on a machine would hit (see
[Specification §10.1](spec.md#101-process-model)). If your host restarts
the server per conversation already, you get this for free.

### Working without a project

**Global-only mode** is reached either way: no project found at cwd with
`--project-root` omitted, or explicitly by pointing the host at a
directory with no `.corvee/config.toml` anywhere above it. It's the MCP
equivalent of `corvee --global task add ...` from such a directory:

```bash
corvee mcp serve
```

In this mode only `TASK-GLOBAL-<n>`/`FACT-GLOBAL-<n>` ids and
global-scoped calls work; anything that needs a local project fails with a
clear error.

## Configure your host

Register the command once and it works across every project: both hosts
below spawn the server with your terminal's own working directory as its
cwd, which auto-detection (above) then walks up from — no `--project-root`
needed, and nothing to re-register when you switch projects.

### Claude Code

```bash
claude mcp add --transport stdio --scope user corvee -- corvee mcp serve
```

`--scope user` registers it once for every project rather than just the
one you're in when you run this. Verify it registered with `claude mcp
list` or `claude mcp get corvee` — see `claude mcp add --help` for the
full set of scopes.

### Codex CLI

```bash
codex mcp add corvee -- corvee mcp serve
```

Or add the equivalent block directly to `~/.codex/config.toml`:

```toml
[mcp_servers.corvee]
command = "corvee"
args = ["mcp", "serve"]
```

Confirm it loaded with `codex mcp list` or `/mcp` inside a Codex session.

### Desktop apps

Claude Desktop and Codex Desktop are a different case: both are known to
spawn stdio MCP servers with cwd set to `/` or your home directory rather
than whatever project you have open, so auto-detection never finds
anything there. Pass `--project-root` explicitly for these:

```bash
corvee mcp serve --project-root /path/to/your/project
```

Since a desktop app config can't vary "the project you currently have
open," this only really works for one project at a time per registered
entry — register one `corvee`-named entry per project if you work on
several, or prefer a terminal-based host instead.

### Any other host

Most hosts read a JSON config naming the command to spawn. The shape is
host-specific — check your host's own docs for where this file lives —
but the entry itself is just the command and its arguments:

```json
{
  "mcpServers": {
    "corvee": {
      "command": "corvee",
      "args": ["mcp", "serve"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

If your host's config has no `cwd` field, pass `--project-root` explicitly
instead:

```json
{
  "mcpServers": {
    "corvee": {
      "command": "corvee",
      "args": ["mcp", "serve", "--project-root", "/path/to/your/project"]
    }
  }
}
```

## What it exposes

Seventeen tools, narrow and single-purpose rather than one wide `task_update`
(see [Specification §10.4](spec.md#104-trust-and-error-handling) for why).
Every tool that writes something accepts an optional `session_id`
argument — a per-conversation token, distinct from the actor set at
startup (see [Specification §10.1](spec.md#101-process-model)) — falling
back to the server's own default (`--session-id`/`$CORVEE_SESSION_ID`, or
a generated id) when a call leaves it out. If you do pass your own,
keep it stable across your calls in one conversation.

| Tool | Writes? | What it does |
|---|---|---|
| `task_show` | no | Read one task by id |
| `task_search` | no | Search tasks (default 20 results) |
| `brief` | no | Session-start snapshot: mine, ready, stale, labels |
| `task_add` | yes | File a new task (never claims it) |
| `task_claim` | yes | Claim a task (`force` to steal someone else's) |
| `task_unclaim` | yes | Release a claim (`force` to release someone else's stale one) |
| `task_comment` | yes | Leave a note on a task |
| `task_start` | yes | Claim and move to `in_progress` |
| `task_done` | yes | Move to `done` |
| `task_cancel` | yes | Move to `cancelled` |
| `task_review` | yes | Move to `review`, keeping the current claim |
| `task_reopen` | yes | Move a `cancelled`/`done` task back to `open` |
| `task_block` | yes | Move to `blocked` — requires a comment explaining why |
| `fact_show` | no | Read one fact by id |
| `fact_search` | no | Search facts (default 20 results) |
| `fact_add` | yes | Record a new fact |
| `fact_verify` | yes | Mark a fact checked-true, with proof |

`force` lives only on `task_claim`/`task_unclaim` — not on `task_start`/
`task_done`/`task_cancel`/`task_review`/`task_reopen`/`task_block`, whose
names should never quietly let a caller steal someone else's claim. Call
`task_claim(force=true)` first if you need to take one over.

No `purge`, `delete`, `import`, or `export` on this surface — those stay
CLI-only. Nor is there a `task_update`/`task_label`/`task_link`/
`task_assign`, or a `fact_revise`/`fact_retract`/`fact_unverify`: once a
task or fact is filed, this surface can only work it forward (claim,
comment, transition it, verify a fact) or leave it as-is, never correct
a mistake in its title, description, claim, or labels/links. Reach for
the CLI (or a human) for that. See
[Specification §10.3](spec.md#103-tool-list) for full argument shapes
and the reasoning behind each tool.

## Responses

A successful call's return value lands in the tool result's
`structuredContent`. Most tools return one object — `task_claim`, for
instance:

```json
{
  "id": "TASK-14",
  "title": "Fix the flaky auth test",
  "description": "repro: run make test twice in a row",
  "type": "bug",
  "priority": "high",
  "state": "open",
  "claimed_by": "agent:claude",
  "claimed_at": "2026-01-01T00:00:00.000Z",
  "assigned_to": null,
  "created_at": "2026-01-01T00:00:00.000Z",
  "updated_at": "2026-01-01T00:00:00.000Z",
  "scope": "local"
}
```

`fact_search`/`task_search` return an object too, not a bare array — the
matches live under `result`, alongside `omitted`, a count of further
matches `limit` cut off (`0` when nothing was cut off):

```json
{
  "result": [
    {"id": "TASK-14", "title": "Fix the flaky auth test", "...": "..."}
  ],
  "omitted": 0
}
```

## Errors

A failed call comes back as an `isError` tool result carrying the same
JSON body a CLI caller gets on stderr, plus one field the CLI's exit
status normally covers:

```json
{
  "error": {
    "code": "claim_conflict",
    "message": "TASK-14 is claimed by agent:other",
    "exit_code": 4
  }
}
```

`exit_code` maps to the same [exit codes](commands.md#exit-codes) the CLI
documents. No raw traceback is ever passed through — an unexpected error
raised inside a tool's own handler still comes back in this shape, with
`exit_code: 1`. A value of a JSON type a parameter's schema rejects
outright (a list or object where a task ref or duration is expected)
never reaches the handler at all; that argument-validation failure
surfaces as the MCP SDK's own error shape instead.

A `claim_conflict` carries one more field, `hint`, phrased for this
surface rather than the CLI's own `--force` flag. Every tool but
`task_unclaim` points at `task_claim(force=true)`, which takes over the
claim so the call can proceed. `task_unclaim` points at
`task_unclaim(force=true)`, since stealing a claim would reassign it
instead of releasing it:

```json
{
  "error": {
    "code": "claim_conflict",
    "message": "TASK-14 is claimed by agent:other",
    "exit_code": 4,
    "hint": "call task_claim(force=true) on this ref to steal the claim, then retry"
  }
}
```

## Learn the rest

[Specification §10](spec.md#10-mcp-server) is the exact contract: process
model, output shape, every tool's arguments, and the testing plan.
