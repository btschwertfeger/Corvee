# Tasks

## 1. `brief` facts section

- [x] 1.1 Add failing tests in `tests/acceptance/test_cli_brief.py` for the `session-brief` scenarios (JSON keys, cap of 5, retracted excluded, merged across scope, `Fact columns`, `Long claim cut`, `Wide fact columns`, clean backlog), update `test_empty_project_returns_empty_sections` to expect the `facts` key, and verify the new tests fail for the missing `facts` section
- [x] 1.2 Extract the table-building part of `emit_facts` in `src/corvee/output.py` into a function that returns the string, have `emit_facts` call it, and verify the existing `fact list` and `fact search` tests still pass unchanged
- [x] 1.3 Add `FACTS_LIMIT` and `facts_section` to `src/corvee/cli/commands/brief.py`, render the section between `stale:` and `labels:` through the 1.2 function, and verify the 1.1 tests pass
- [x] 1.4 Add a failing MCP test in `tests/acceptance/test_mcp_read_tools.py` for the `facts` key, update the four-key assertion in `tests/e2e/test_mcp_protocol.py`, then call `facts_section` from the `brief` tool in `src/corvee/mcp/tools_read.py` and update its docstring, and verify those tests and `tests/acceptance/test_mcp_tool_descriptions.py` pass
- [x] 1.5 Update the `brief` row in `docs/mcp.md` and the `brief` command docstring in `src/corvee/cli/commands/brief.py` to name all five sections, and verify `corvee brief --help` and the row match
- [x] 1.6 Run `hatch run check` and verify it passes

## 2. `doctor` stale facts

- [x] 2.1 Add failing tests in `tests/acceptance/test_db_stats.py` and `tests/acceptance/test_cli_doctor.py` for `facts.stale` (a verified fact past the window counts, `unverified` and `retracted` facts never count, `stale_before=None` yields 0, the `local.facts.stale:` table line) and verify they fail
- [x] 2.2 Add the `stale` count to the `facts` object in `project_stats` (`src/corvee/db/stats.py`) through `list_facts` with `FactFilter(stale_before=...)`, and the `facts.stale` line in `src/corvee/cli/commands/doctor.py`, then verify the 2.1 tests pass
- [x] 2.3 Run `hatch run check` and verify it passes

## 3. `explain` facts guidance

- [x] 3.1 Add failing tests in `tests/acceptance/test_cli_explain_and_epilogs.py` for the `explain-command` scenarios (`Verify example`, `Read-side rule`, `Stale pointer` with a duration of days, `Brief example names facts`), each scoped to the `FACTS` section or the `brief` example line, and verify they fail
- [x] 3.2 Edit `EXPLAIN_TEXT` in `src/corvee/cli/commands/explain.py` to add the `fact verify` example, the read-side rule, the `fact list --stale 30d` example, and a `brief` example comment that names facts, then verify the 3.1 tests pass
- [x] 3.3 Run `hatch run check` and verify it passes

## 4. Integration

- [x] 4.1 Run `hatch run check` on the whole change and `openspec validate surface-facts-to-agents --strict`, and verify both pass

## Workflow follow-up

- Land each of groups 1 to 3 as its own commit.
- Archive the change after the project's review requirements are satisfied.
- Run `openspec validate --specs --strict` after archive and verify the main specs describe five `brief` sections and `facts.stale`.
