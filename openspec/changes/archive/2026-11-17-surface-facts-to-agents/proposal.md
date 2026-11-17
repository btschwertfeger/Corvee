# Proposal

## Why

An agent orients with `brief`, `doctor`, and `explain`, yet `brief` lists no facts, `doctor` counts stale tasks but not stale facts, and `explain` omits the `fact verify` example its own spec requires. An agent that does not think to run `fact list` never learns what the project already knows or which facts need re-checking.

## What Changes

- `brief` gains a fifth section named `facts` that holds the newest 5 non-retracted facts. It merges across scope like `mine`, `ready`, and `stale`, renders with the same columns and claim cut as `fact list`, and drops out of plain-text output when empty.
- `doctor` reports a `stale` count under `facts`, using the `--stale` window and the `fact list --stale` rule, and prints it in table output.
- The `FACTS` block in `explain` gains a `fact verify` example, tells the reader to check `fact search` before asserting or re-deriving something, and shows `fact list --stale` with a long duration for re-verifying. The `brief` example in `TASKS` stops describing the snapshot as only "mine + ready + stale".

Pointing at facts from `task claim`, `task start`, `task done`, or `task show` and a separate default stale window for facts stay out of scope.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `session-brief`: `brief` composes five sections instead of four, with a capped, scope-following `facts` section rendered like `fact list`.
- `mcp-tools`: the `brief` tool returns the `facts` section and its cap.
- `project-health`: `doctor`'s `facts` object gains a `stale` count tied to the `--stale` window.
- `explain-command`: the `FACTS` block carries the read-side rule, a `fact verify` example, and a pointer to stale facts, and the `brief` example names facts.

## Impact

- Code: the section functions in `src/corvee/cli/commands/brief.py`, the MCP `brief` tool in `src/corvee/mcp/tools_read.py`, the fact table rendering in `src/corvee/output.py` (shared with `brief`), `src/corvee/db/stats.py` and the `doctor` command, and `EXPLAIN_TEXT` in `src/corvee/cli/commands/explain.py`.
- Docs: the `brief` row in `docs/mcp.md`.
- Output shapes: `brief -o json` and the MCP `brief` result gain a `facts` key, and `doctor -o json` gains `facts.stale`. Both additions leave existing keys untouched.
- Tests: `test_cli_brief.py`, the MCP read-tool and tool-description tests, the MCP protocol e2e test, and the `doctor` and `explain` acceptance tests. The two existing assertions that pin the four-key `brief` result change with it.
