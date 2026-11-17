#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
import sqlite3
from collections.abc import Callable

from click.testing import CliRunner

from corvee.cli.main import cli
from corvee.config import ProjectConfig


class TestBrief:
    def test_empty_project_returns_empty_sections(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """A project with nothing claimed, ready, or stale returns empty arrays, not an error."""
        result = runner.invoke(cli, ["brief", "-o", "json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload == {"mine": [], "ready": [], "stale": [], "facts": [], "labels": []}

    def test_combines_mine_ready_and_stale(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        conn: sqlite3.Connection,
        add_task: Callable[[str], str],
    ) -> None:
        """One call surfaces the same rows `task mine`/`task ready`/`task list --stale` would."""
        mine_id = add_task("in progress")
        runner.invoke(cli, ["task", "claim", mine_id])
        runner.invoke(cli, ["task", "update", mine_id, "--state", "in_progress"])

        ready_id = add_task("ready to start")

        stale_id = add_task("stale claim")
        runner.invoke(cli, ["task", "claim", stale_id])
        stale_num = stale_id.removeprefix("TASK-")
        conn.execute(
            "UPDATE tasks SET claimed_at = '2000-01-01T00:00:00.000Z' WHERE id = ?", (stale_num,)
        )
        conn.commit()

        result = runner.invoke(cli, ["brief", "-o", "json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert {t["id"] for t in payload["mine"]} == {stale_id, mine_id}
        assert [t["id"] for t in payload["ready"]] == [ready_id]
        assert [t["id"] for t in payload["stale"]] == [stale_id]

    def test_ready_is_capped_at_five_regardless_of_backlog_size(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """The ready section stays capped even when far more tasks are startable."""
        for i in range(8):
            add_task(f"task {i}")

        result = runner.invoke(cli, ["brief", "-o", "json"])
        payload = json.loads(result.output)
        assert len(payload["ready"]) == 5

    def test_plain_text_omits_empty_sections(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A section with no rows doesn't print a header over an empty table."""
        add_task("ready to start")
        result = runner.invoke(cli, ["brief"])
        assert result.exit_code == 0
        assert "ready:" in result.output
        assert "mine:" not in result.output
        assert "stale:" not in result.output

    def test_plain_text_table_uses_the_narrow_default_fields(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """The description column is dropped by default, like every other list-shaped
        command's table -- a long free-text value would otherwise blow up the
        fixed-width row.
        """
        runner.invoke(
            cli,
            [
                "task",
                "add",
                "ready to start",
                "--description",
                "a long free-text description",
                "-o",
                "json",
            ],
        )
        result = runner.invoke(cli, ["brief"])
        assert "DESCRIPTION" not in result.output
        assert "a long free-text description" not in result.output

    def test_scope_global_merges_the_global_database(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """--scope behaves like task list's: all merges local and global."""
        runner.invoke(
            cli, ["task", "add", "global task", "--description", "d", "--global", "-o", "json"]
        )
        result = runner.invoke(cli, ["brief", "-o", "json"])
        payload = json.loads(result.output)
        assert [t["id"] for t in payload["ready"]] == ["TASK-GLOBAL-1"]

    def test_labels_shows_existing_vocabulary_with_task_counts(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`labels` surfaces the project's label vocabulary, same shape as `task labels`."""
        task_id = add_task("tagged")
        runner.invoke(cli, ["task", "label", task_id, "--add", "api"])

        result = runner.invoke(cli, ["brief", "-o", "json"])
        payload = json.loads(result.output)
        assert payload["labels"] == [{"name": "api", "task_count": 1}]

    def test_labels_are_not_merged_across_scope(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A global task's labels stay out of `labels`, regardless of --scope
        (`local-global-scope` spec).
        """
        global_result = runner.invoke(
            cli, ["task", "add", "global task", "--description", "d", "--global", "-o", "json"]
        )
        global_id = json.loads(global_result.output)[0]["id"]
        runner.invoke(cli, ["task", "label", global_id, "--add", "global-only"])

        result = runner.invoke(cli, ["brief", "--scope", "all", "-o", "json"])
        payload = json.loads(result.output)
        assert payload["labels"] == []

    def test_plain_text_labels_section(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """Plain-text output includes a labels: section when labels exist."""
        task_id = add_task("tagged")
        runner.invoke(cli, ["task", "label", task_id, "--add", "api"])

        result = runner.invoke(cli, ["brief"])
        assert "labels:" in result.output
        assert "api" in result.output


class TestBriefFacts:
    def test_facts_are_the_newest_five_newest_first(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """The facts section is capped at five and ordered like `fact list`."""
        ids = [add_fact(f"fact {i}") for i in range(8)]

        result = runner.invoke(cli, ["brief", "-o", "json"])
        payload = json.loads(result.output)
        assert [f["id"] for f in payload["facts"]] == list(reversed(ids))[:5]

    def test_retracted_facts_are_excluded(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """A retracted fact drops out, the same default `fact list` has."""
        kept_id = add_fact("kept")
        retracted_id = add_fact("withdrawn")
        runner.invoke(cli, ["fact", "retract", retracted_id])

        result = runner.invoke(cli, ["brief", "-o", "json"])
        payload = json.loads(result.output)
        assert [f["id"] for f in payload["facts"]] == [kept_id]

    def test_unverified_and_verified_facts_both_appear(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """The `status` field tells unchecked facts from verified ones."""
        unverified_id = add_fact("unchecked")
        runner.invoke(cli, ["fact", "add", "checked", "--proof", "ran it", "-o", "json"])

        result = runner.invoke(cli, ["brief", "-o", "json"])
        payload = json.loads(result.output)
        statuses = {f["id"]: f["status"] for f in payload["facts"]}
        assert statuses[unverified_id] == "unverified"
        assert set(statuses.values()) == {"unverified", "verified"}

    def test_facts_merge_local_and_global_newest_first(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        conn: sqlite3.Connection,
        add_fact: Callable[[str], str],
    ) -> None:
        """--scope all (the default) merges both databases by created_at descending."""
        local_id = add_fact("local fact")
        conn.execute("UPDATE facts SET created_at = '2000-01-01T00:00:00.000Z'")
        conn.commit()
        runner.invoke(cli, ["fact", "add", "global fact", "--global", "-o", "json"])

        result = runner.invoke(cli, ["brief", "-o", "json"])
        payload = json.loads(result.output)
        assert [f["id"] for f in payload["facts"]] == ["FACT-GLOBAL-1", local_id]

    def test_scope_global_excludes_local_facts(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """--scope global shows only the shared database's facts."""
        add_fact("local fact")
        runner.invoke(cli, ["fact", "add", "global fact", "--global", "-o", "json"])

        result = runner.invoke(cli, ["brief", "--scope", "global", "-o", "json"])
        payload = json.loads(result.output)
        assert [f["id"] for f in payload["facts"]] == ["FACT-GLOBAL-1"]

    def test_plain_text_has_no_headers_on_a_clean_backlog(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """With nothing to show, no section header prints, `facts:` included."""
        result = runner.invoke(cli, ["brief"])
        assert result.exit_code == 0
        for header in ("mine:", "ready:", "stale:", "facts:", "labels:"):
            assert header not in result.output

    def test_plain_text_facts_section_sits_between_stale_and_labels(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """The facts: section renders after the task sections and before labels:."""
        task_id = add_task("tagged")
        runner.invoke(cli, ["task", "label", task_id, "--add", "api"])
        runner.invoke(cli, ["fact", "add", "a claim", "-o", "json"])

        output = runner.invoke(cli, ["brief"]).output
        assert output.index("ready:") < output.index("facts:") < output.index("labels:")

    def test_plain_text_facts_table_uses_the_narrow_fact_columns(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """The default facts table shows ID, CLAIM and STATUS, not the task columns."""
        add_fact("a claim")

        facts_block = runner.invoke(cli, ["brief"]).output.split("facts:\n", 1)[1]
        header = facts_block.splitlines()[0].split()
        assert header == ["ID", "CLAIM", "STATUS"]

    def test_plain_text_cuts_a_long_claim_at_sixty_cells(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """A 100-character claim is cut to 60 cells ending in `...`, like `fact list`."""
        add_fact("x" * 100)

        output = runner.invoke(cli, ["brief"]).output
        assert "x" * 57 + "..." in output
        assert "x" * 58 not in output

    def test_wide_shows_the_fact_wide_columns_and_the_full_claim(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """-o wide matches `fact list -o wide`: more columns, whole claim."""
        add_fact("x" * 100)

        output = runner.invoke(cli, ["brief", "-o", "wide"]).output
        wide_header = runner.invoke(cli, ["fact", "list", "-o", "wide"]).output.splitlines()[0]
        assert wide_header in output
        assert "x" * 100 in output
