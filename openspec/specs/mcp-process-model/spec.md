# mcp-process-model Specification

## Purpose

corvee is CLI-first. The MCP server is a second, additive surface for hosts that speak MCP but expose no shell to the agent, and for subagent handoffs where brokering every call through a parent's shell is the friction. It lets a subagent read and write corvee's shared state through typed tool calls. This capability defines how the server process runs, resolves its identity and project, and reports its mode.

## Requirements

### Requirement: One stdio process per conversation
A host session SHALL be one `corvee mcp serve [--project-root <path>] [--actor <id>] [--session-id <id>]` process lifetime, a stdio subprocess and not a daemon. A host SHALL be expected to spawn one process per conversation, which scopes claims and the actor to one agent. There SHALL be no per-call actor override.

#### Scenario: Two conversations, two processes
- **WHEN** a host starts two `corvee mcp serve --actor agent:a` and `--actor agent:b` processes
- **THEN** claims taken through each are held by that process's actor

### Requirement: Multiplexed conversations share one identity
A host that multiplexes several conversations onto one process SHALL share one actor identity among them. This is the shared-identity collision `claims-and-assignment` describes, and `doctor` SHALL detect it from the session ids.

#### Scenario: Shared process
- **WHEN** two conversations use one server process and both claim the same task
- **THEN** both claims succeed, because they share one actor

### Requirement: Network transports are out of scope
The server SHALL NOT offer an HTTP or SSE transport serving several independent hosts. That is a different concurrency and trust problem and would need its own design.

#### Scenario: Transport
- **WHEN** `corvee mcp serve` starts
- **THEN** it speaks MCP over stdio only

### Requirement: One connection and transaction per tool call
Each tool call SHALL open one connection, run one transaction (`BEGIN IMMEDIATE` for a mutating tool, a plain `BEGIN` for a read), and close the connection before returning, exactly like a CLI invocation.

#### Scenario: Read tool
- **WHEN** `task_show` is called
- **THEN** it reads under a plain `BEGIN` and holds no connection afterward

### Requirement: Database work is serialized on one worker thread
All per-call database work SHALL run serialized on one dedicated worker thread for the process's lifetime, never a thread-per-call pool, with a call's whole sequence (including a multi-connection read like `brief`) in one unit of work. Concurrent tool calls SHALL queue, and the async layer SHALL NOT do database work.

SQLite connections must be created, used, and closed on one thread, and a pool would bring `SQLITE_BUSY` contention inside one process.

#### Scenario: Concurrent calls
- **WHEN** several tool calls arrive at once against one project
- **THEN** they all complete with no `SQLITE_BUSY` or thread-affinity error and no lost write

### Requirement: Actor is resolved once and passed explicitly
`--actor`, falling back to `CORVEE_ACTOR` and then `human:$USER`, SHALL be read once at launch into a plain string. The server SHALL pass that string explicitly into every call's database work and SHALL NOT re-resolve it from ambient state inside the worker thread.

Re-resolving there silently discards the launched `--actor`, because click's context is thread-local.

#### Scenario: Launched actor survives the worker thread
- **WHEN** the server is launched with `--actor agent:claude` and a write tool runs
- **THEN** the written event's actor is `agent:claude`

### Requirement: Session id resolves once with a per-call override
The server session id SHALL come from `--session-id`, then `$CORVEE_SESSION_ID`, then a `uuid4` minted once for the process. Every tool that writes an event SHALL accept an optional per-call `session_id` that overrides the server default. The server default SHALL be the one stamped when a call omits it.

A per-call value with no server default would let each call mint its own, making every call look like a different run to `doctor`.

#### Scenario: Default stamp
- **WHEN** the server runs with no session flag or variable and a write tool is called without `session_id`
- **THEN** the event's session id is the process's minted uuid

#### Scenario: Override
- **WHEN** a write tool is called with `session_id` `s9`
- **THEN** the event's session id is `s9`

### Requirement: Explicit `--project-root` must resolve
With `--project-root <path>` the server SHALL resolve the project once at launch from that path. If it does not resolve to a valid `.corvee/config.toml`, the server SHALL refuse to start with exit 6 and a stderr message, and register no tools.

#### Scenario: Wrong path
- **WHEN** `corvee mcp serve --project-root /nonexistent` runs
- **THEN** the exit code is 6 and no tool is served

### Requirement: Omitted `--project-root` auto-detects or goes global-only
Without `--project-root` the server SHALL resolve the project from its current directory exactly as the CLI does, once at launch. If none resolves it SHALL fall back to global-only mode instead of refusing to start. A resolution that fails mid-session SHALL surface as a per-call `isError` result with the `ConfigError` shape and exit code 6, without crashing the process.

#### Scenario: Started from inside a project
- **WHEN** the server starts with its current directory inside an initialized project
- **THEN** local tools operate on that project without any flag

#### Scenario: Config deleted mid-session
- **WHEN** `.corvee/config.toml` is deleted after launch and a local-scope tool is called
- **THEN** that call returns an `isError` result with exit code 6 and the server keeps running

### Requirement: Global-only mode serves global scope
In global-only mode a tool call given a bare `TASK-<n>` or `FACT-<n>` SHALL fail with an `isError` result with error code `no_project` and exit code 6. `TASK-GLOBAL-<n>` and `FACT-GLOBAL-<n>` ids and `is_global: true` SHALL work as with a project. An explicit `local` scope SHALL fail with `no_project`, `all` SHALL silently drop the missing local side, and `global` SHALL work.

#### Scenario: Local id without a project
- **WHEN** the server has no project and `task_show` is called with `TASK-3`
- **THEN** the result is an error with code `no_project` and exit code 6

#### Scenario: Brief with scope all
- **WHEN** the server has no project and `brief` is called with scope `all`
- **THEN** it succeeds and reports only global rows

### Requirement: A newer schema ends the process
Every call SHALL still read `schema_migrations` before anything else. If a newer binary has migrated the database, the call SHALL return an `isError` result with the exit-6 shape naming both versions, the same message SHALL be printed to stderr, and the server SHALL then exit nonzero, since every later call would repeat the same error until a restart.

#### Scenario: Version skew mid-session
- **WHEN** `schema_migrations` is bumped past the binary's version and a tool is called
- **THEN** the call returns an exit-6 error naming both versions and the process exits nonzero

### Requirement: Upgrades need a restart
Installing a new corvee while the server runs SHALL NOT change its tools or behavior until the process restarts.

#### Scenario: Package upgraded in place
- **WHEN** corvee is upgraded on disk while a server runs
- **THEN** the running server keeps the tool set it loaded at launch

### Requirement: Startup reports the resolved mode
Once at startup the server SHALL print one line to stderr, never stdout, naming either the resolved project's path or that no project was found and it is in global-only mode. The same information SHALL be part of the `instructions` string given to the MCP client at initialization.

#### Scenario: Startup line
- **WHEN** `corvee mcp serve` starts outside any project
- **THEN** stderr carries one line stating global-only mode and stdout carries only protocol frames
