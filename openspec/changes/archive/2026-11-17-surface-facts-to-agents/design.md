# Design

## Context

`brief` builds each section in a function in `src/corvee/cli/commands/brief.py` (`mine_section`, `ready_section`, `stale_section`, `labels_section`). The CLI command and the MCP `brief` tool in `src/corvee/mcp/tools_read.py` both call those functions, so a section added there reaches both surfaces. The plain-text path renders every task section with the task column set. `doctor` takes its counts from `project_stats` in `src/corvee/db/stats.py`, and `explain` prints one static string, `EXPLAIN_TEXT`. See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- Add the `facts` section, the `facts.stale` count, and the `FACTS` guidance with the least new code, reusing `list_facts`, `fetch_merged`, `sort_facts`, and the `fact list` table rendering.

**Non-Goals:**
- A fact-specific stale window, or any change to how `fact list --stale` decides staleness.
- Any `--limit` or filter flag on `brief`.

## Decisions

**`facts_section` mirrors `ready_section`.** It takes the same `actor`, `project_db_path`, and `local_available` parameters, loads facts through `list_facts` and `fetch_merged`, sorts with `sort_facts`, and slices to 5, exactly as `ready_section` does for tasks. The MCP tool passes its already-resolved values as it does for the other sections. A new `FACTS_LIMIT = 5` constant sits beside `READY_LIMIT`. The spec fixes both caps independently, so each gets its own constant.

**`brief` reuses the `fact list` table rendering.** The 60-cell claim cut and the fact column sets exist only inside `emit_facts` in `src/corvee/output.py`, which prints instead of returning a string. The implementation extracts the table-building part into a function that `emit_facts` and `brief` both call. The alternative of copying the cut into `brief.py` would leave two places to keep in step with the `cli-conventions` rule.

**`facts.stale` reuses `list_facts`.** `project_stats` takes the length of `list_facts(conn, FactFilter(stale_before=...))`, so the count matches `fact list --stale` by construction, including the exclusion of `unverified` and `retracted` facts. `stale_before=None` yields 0, as for tasks. The task count uses raw SQL because no shared task predicate exists, and building fact rows to count them costs nothing at this scale.

**`facts` gets its own section.** `stale` lists tasks whose claim went quiet and that another agent may take over. Stale facts count in `doctor`, and `brief` lists the newest facts so an agent sees what exists.

**`explain` grows by a few lines in `FACTS`.** The additions are a `fact verify` example, the `fact search` read-side rule with its `verified` and `unverified` distinction, and a `fact list --stale 30d` example. The read-side rule deliberately repeats the fact discipline in the `agent-integration` pointer blocks, and the two wordings stay aligned. The `30d` duration keeps agents from re-verifying nearly every fact, which the default `4h` window would suggest.

## Risks / Trade-offs

[`-o json` rows carry the full fact, including `proof`, so five long proofs inflate `brief`] → The cap bounds it, and the spec's "same row shape as its source command" matches how `mine` and `ready` return full task rows.

[The `4h` default makes most verified facts count as stale in `doctor`] → `fact list --stale` already behaves this way. On `doctor`, one `--stale` value also sets `tasks.stale` and the shared-actor window, so widening it loosens all three. A separate fact window is a follow-up, and the non-goals exclude it here. `explain` points at `fact list --stale 30d`, which widens facts alone.

[Existing consumers of the `brief` JSON see a new `facts` key] → Adding a key leaves every existing key unchanged, and the MCP `brief` result is an untyped dict. Two existing tests assert the exact four-key result and change with it.
