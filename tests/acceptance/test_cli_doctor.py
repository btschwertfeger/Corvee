#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from corvee.cli.main import cli
from corvee.config import ProjectConfig, bootstrap_project
from corvee.db.schema import CURRENT_SCHEMA_VERSION


def _insert_blocks_cycle(runner: CliRunner, conn: sqlite3.Connection) -> tuple[str, str]:
    """Hand-edit an a-blocks-b-blocks-a cycle, impossible via normal `task link`.

    Returns the two full ids in insertion order, which is also cycle-detection
    order (`edges` is built by row-insertion order, so `a`'s cycle is found
    walking `a -> b -> a`).
    """
    a_result = runner.invoke(cli, ["task", "add", "a", "--description", "d", "--json"])
    b_result = runner.invoke(cli, ["task", "add", "b", "--description", "d", "--json"])
    a_id = json.loads(a_result.output)[0]["id"]
    b_id = json.loads(b_result.output)[0]["id"]
    a = a_id.removeprefix("TASK-")
    b = b_id.removeprefix("TASK-")
    conn.execute(
        "INSERT INTO task_links (source_id, target_id, relation) VALUES (?, ?, 'blocks')",
        (a, b),
    )
    conn.execute(
        "INSERT INTO task_links (source_id, target_id, relation) VALUES (?, ?, 'blocks')",
        (b, a),
    )
    conn.commit()
    return a_id, b_id


class TestDoctor:
    def test_reports_schema_version_and_db_path(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """`corvee doctor --json` yields one object with schema_version and local.db_path."""
        result = runner.invoke(cli, ["doctor", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["schema_version"] == CURRENT_SCHEMA_VERSION
        assert payload["local"]["db_path"] == str(project.db_path)

    def test_reports_task_and_fact_counts(self, runner: CliRunner, project: ProjectConfig) -> None:
        """doctor reflects tasks/facts created since init, regardless of state/status."""
        runner.invoke(cli, ["task", "add", "a task", "--description", "d", "--json"])
        runner.invoke(cli, ["fact", "add", "a fact", "--json"])
        result = runner.invoke(cli, ["doctor", "--json"])
        payload = json.loads(result.output)
        assert payload["local"]["tasks"]["total"] == 1
        assert payload["local"]["facts"]["total"] == 1

    def test_stale_flag_controls_the_cutoff(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """--stale (default 4h) is a tunable duration, mirroring task list --stale."""
        result = runner.invoke(cli, ["doctor", "--stale", "0s", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "stale" in payload["local"]["tasks"]

    def test_yields_one_object_not_an_array(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """Unlike every task/fact command, doctor's --json output is a single object."""
        result = runner.invoke(cli, ["doctor", "--json"])
        payload = json.loads(result.output)
        assert isinstance(payload, dict)

    def test_table_output_is_non_empty(self, runner: CliRunner, project: ProjectConfig) -> None:
        """Without --json, doctor prints readable key: value lines, not a JSON blob."""
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert result.output.strip() != ""

    def test_healthy_project_reports_no_findings(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """A project with no cycles and no dangling rows reports an empty findings list."""
        runner.invoke(cli, ["task", "add", "a task", "--description", "d", "--json"])
        result = runner.invoke(cli, ["doctor", "--json"])
        payload = json.loads(result.output)
        assert payload["local"]["findings"] == []

    def test_reports_a_hand_edited_cycle(
        self, runner: CliRunner, project: ProjectConfig, conn: sqlite3.Connection
    ) -> None:
        """A blocks cycle in the database, impossible via normal `task link`, still surfaces."""
        a_id, b_id = _insert_blocks_cycle(runner, conn)

        result = runner.invoke(cli, ["doctor", "--json"])
        payload = json.loads(result.output)
        assert payload["local"]["findings"] == [
            {"kind": "cycle", "relation": "blocks", "task_ids": [a_id, b_id, a_id]}
        ]

    def test_table_output_renders_a_cycle_finding(
        self, runner: CliRunner, project: ProjectConfig, conn: sqlite3.Connection
    ) -> None:
        """Non-JSON output spells out the cycle's actual task ids, not just its label."""
        a_id, b_id = _insert_blocks_cycle(runner, conn)

        result = runner.invoke(cli, ["doctor"])
        assert f"blocks cycle: {a_id} -> {b_id} -> {a_id}" in result.output

    def test_table_output_renders_a_dangling_foreign_key_finding(
        self, runner: CliRunner, project: ProjectConfig, conn: sqlite3.Connection
    ) -> None:
        """Non-JSON output spells out a dangling foreign key finding.

        Only reachable with foreign_keys off, like a database edited by
        something other than corvee itself.
        """
        task_id = json.loads(
            runner.invoke(cli, ["task", "add", "a", "--description", "d", "--json"]).output
        )[0]["id"].removeprefix("TASK-")
        conn.execute("INSERT INTO labels (name) VALUES ('api')")
        conn.execute(
            "INSERT INTO task_labels (task_id, label_id) "
            "VALUES (?, (SELECT id FROM labels WHERE name = 'api'))",
            (task_id,),
        )
        rowid = conn.execute("SELECT rowid FROM task_labels").fetchone()[0]
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()

        result = runner.invoke(cli, ["doctor"])
        assert f"dangling foreign key: task_labels.rowid={rowid} -> tasks" in result.output

    def test_table_output_renders_the_global_section(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """Non-JSON output includes the global stats block once --global is used."""
        runner.invoke(cli, ["task", "add", "global one", "--description", "d", "--global"])
        result = runner.invoke(cli, ["doctor"])
        assert "global.db_path:" in result.output
        assert "global.tasks.total: 1" in result.output

    def test_table_output_renders_the_local_section(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """Non-JSON output prefixes the local stats block the same way global's is."""
        runner.invoke(cli, ["task", "add", "a task", "--description", "d", "--json"])
        result = runner.invoke(cli, ["doctor"])
        assert "local.db_path:" in result.output
        assert "local.tasks.total: 1" in result.output

    def test_runs_from_a_directory_with_no_project(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Outside any project, doctor reports local: null instead of exit 6 (GH#23)."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(cli, ["doctor", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["local"] is None
        assert payload["global"] is None

    def test_table_output_reports_no_local_project(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-JSON output names the missing local project rather than erroring."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "local: not initialized in this directory" in result.output

    def test_reports_global_stats_with_no_local_project(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A --global task filed elsewhere still shows up run from an uninitialized directory."""
        other_project = tmp_path / "elsewhere"
        other_project.mkdir()
        monkeypatch.chdir(other_project)
        bootstrap_project(other_project)
        runner.invoke(cli, ["task", "add", "global one", "--description", "d", "--global"])

        no_project_dir = tmp_path / "scratch"
        no_project_dir.mkdir()
        monkeypatch.chdir(no_project_dir)
        result = runner.invoke(cli, ["doctor", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["local"] is None
        assert payload["global"]["tasks"]["total"] == 1

    def test_flags_two_sessions_sharing_one_actor_on_a_claimed_task(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """Two CORVEE_SESSION_IDs claiming under the same actor surface as a
        shared_actor_sessions finding (GH#24) -- the collision an unset
        CORVEE_ACTOR causes between two concurrent sessions.
        """
        add_result = runner.invoke(cli, ["task", "add", "a", "--description", "d", "--json"])
        task_id = json.loads(add_result.output)[0]["id"]

        runner.invoke(cli, ["--session-id", "session-a", "task", "claim", task_id])
        runner.invoke(cli, ["--session-id", "session-b", "task", "claim", task_id])

        result = runner.invoke(cli, ["doctor", "--json"])
        payload = json.loads(result.output)
        assert payload["local"]["findings"] == [
            {
                "kind": "shared_actor_sessions",
                "task_id": task_id,
                "actor": "agent:test",
                "session_ids": ["session-a", "session-b"],
            }
        ]
