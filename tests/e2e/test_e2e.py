#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

"""End-to-end tests against the real installed binary and a real database
in a temp directory — no CliRunner, no in-process shortcuts. Each call is a
genuine subprocess, either `python -m corvee` or the installed `corvee`
console script, which is what an actual agent or human invokes.
"""

import json
import os
import subprocess
import sys
import sysconfig
from pathlib import Path


def _corvee(
    args: list[str], cwd: Path, actor: str = "agent:e2e"
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CORVEE_ACTOR": actor, "CORVEE_SESSION_ID": "e2e-session"}
    return subprocess.run(
        [sys.executable, "-m", "corvee", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestFullWorkflow:
    def test_init_add_claim_work_done_show(self, tmp_path: Path) -> None:
        """A full init -> add -> claim -> work -> done -> show workflow succeeds end to end."""
        init_result = _corvee(["init"], tmp_path)
        assert init_result.returncode == 0
        assert (tmp_path / ".corvee" / "config.toml").is_file()
        assert (tmp_path / ".corvee" / "corvee.db").is_file()

        add_result = _corvee(
            ["task", "add", "Fix the flaky auth test", "--description", "d", "--json"], tmp_path
        )
        assert add_result.returncode == 0
        task_id = json.loads(add_result.stdout)[0]["id"]
        assert task_id == "TASK-1"

        claim_result = _corvee(["task", "claim", task_id, "--json"], tmp_path)
        assert claim_result.returncode == 0
        assert json.loads(claim_result.stdout)[0]["claimed_by"] == "agent:e2e"

        in_progress = _corvee(
            ["task", "update", task_id, "--state", "in_progress", "--json"], tmp_path
        )
        assert json.loads(in_progress.stdout)[0]["state"] == "in_progress"

        comment_result = _corvee(
            ["task", "comment", task_id, "found the root cause", "--json"], tmp_path
        )
        assert comment_result.returncode == 0

        done_result = _corvee(["task", "update", task_id, "--state", "done", "--json"], tmp_path)
        done_payload = json.loads(done_result.stdout)[0]
        assert done_payload["state"] == "done"
        assert done_payload["claimed_by"] is None

        show_result = _corvee(["task", "show", task_id, "--json"], tmp_path)
        show_payload = json.loads(show_result.stdout)[0]
        kinds = [event["kind"] for event in show_payload["events"]]
        assert "comment" in kinds
        assert "field_change" in kinds

    def test_second_actor_conflicts_with_an_active_claim(self, tmp_path: Path) -> None:
        """A second real process cannot update a task the first process still holds."""
        _corvee(["init"], tmp_path)
        add_result = _corvee(
            ["task", "add", "shared task", "--description", "d", "--json"],
            tmp_path,
            actor="agent:a",
        )
        task_id = json.loads(add_result.stdout)[0]["id"]
        _corvee(["task", "claim", task_id], tmp_path, actor="agent:a")

        conflict = _corvee(
            ["task", "update", task_id, "--title", "stolen", "--json"], tmp_path, actor="agent:b"
        )
        assert conflict.returncode == 4
        payload = json.loads(conflict.stderr)
        assert payload["error"]["code"] == "claim_conflict"

    def test_export_then_import_into_a_fresh_project(self, tmp_path: Path) -> None:
        """A real export/import round trip via two separate processes restores every task."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _corvee(["init"], source_dir)
        _corvee(["task", "add", "task one", "--description", "d", "--json"], source_dir)
        _corvee(["task", "add", "task two", "--description", "d", "--json"], source_dir)
        backup_file = tmp_path / "backup.json"
        export_result = _corvee(["export", "--output", str(backup_file)], source_dir)
        assert export_result.returncode == 0
        assert backup_file.is_file()

        target_dir = tmp_path / "target"
        target_dir.mkdir()
        _corvee(["init"], target_dir)
        import_result = _corvee(["import", str(backup_file), "--json"], target_dir)
        assert import_result.returncode == 0
        imported = json.loads(import_result.stdout)
        assert {t["title"] for t in imported} == {"task one", "task two"}

    def test_labels_and_parent_child_hierarchy(self, tmp_path: Path) -> None:
        """Labeling and parent_of linking work end to end, and closing an open parent is blocked."""
        _corvee(["init"], tmp_path)
        parent = json.loads(
            _corvee(["task", "add", "epic", "--description", "d", "--json"], tmp_path).stdout
        )[0]["id"]
        child = json.loads(
            _corvee(["task", "add", "subtask", "--description", "d", "--json"], tmp_path).stdout
        )[0]["id"]

        _corvee(["task", "label", parent, "--add", "backend", "--add", "urgent"], tmp_path)
        link_result = _corvee(
            ["task", "link", parent, child, "--relation", "parent_of", "--json"], tmp_path
        )
        assert link_result.returncode == 0

        show_result = _corvee(["task", "show", parent, "--json"], tmp_path)
        payload = json.loads(show_result.stdout)[0]
        assert sorted(payload["labels"]) == ["backend", "urgent"]
        assert payload["subtasks"] == [child]

        # Can't close the parent while the child is still open.
        blocked_close = _corvee(["task", "update", parent, "--state", "done", "--json"], tmp_path)
        assert blocked_close.returncode == 5

    def test_explain_and_help_work_without_a_project(self, tmp_path: Path) -> None:
        """`explain` and `--help` work in a directory with no .corvee/config.toml at all."""
        explain_result = _corvee(["explain"], tmp_path)
        assert explain_result.returncode == 0
        assert "--actor" in explain_result.stdout

        help_result = _corvee(["--help"], tmp_path)
        assert help_result.returncode == 0

    def test_installed_console_script_runs_end_to_end(self, tmp_path: Path) -> None:
        """The `corvee` console script declared in [project.scripts] works, not just
        `python -m corvee`."""
        script = Path(sysconfig.get_path("scripts")) / (
            "corvee.exe" if sys.platform == "win32" else "corvee"
        )
        assert script.is_file(), f"installed console script not found at {script}"

        env = {**os.environ, "CORVEE_ACTOR": "agent:e2e", "CORVEE_SESSION_ID": "e2e-session"}
        init_result = subprocess.run(
            [str(script), "init"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30
        )
        assert init_result.returncode == 0

        add_result = subprocess.run(
            [
                str(script),
                "task",
                "add",
                "exercise the console script",
                "--description",
                "d",
                "--json",
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert add_result.returncode == 0
        assert json.loads(add_result.stdout)[0]["id"] == "TASK-1"
