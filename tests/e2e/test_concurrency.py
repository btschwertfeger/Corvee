#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
import os
import subprocess
import sys
from pathlib import Path

from corvee.config import bootstrap_project
from corvee.db.connection import open_connection

_RUN_CLI = "from corvee.cli.main import main; main()"


def _run(args: list[str], cwd: Path, actor: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CORVEE_ACTOR": actor}
    return subprocess.run(
        [sys.executable, "-c", _RUN_CLI, *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestConcurrentClaims:
    def test_two_processes_claiming_the_same_task_produce_exactly_one_winner(
        self, tmp_path: Path
    ) -> None:
        """Of 8 real processes racing to claim one task, exactly one wins; every
        loser exits 4 (claim_conflict), except a loser whose wait outlasts
        busy_timeout, which exits 1 instead -- a real outcome of this race on
        a loaded runner, not a bug in the race itself.
        """
        bootstrap_project(tmp_path)
        add_result = _run(
            ["task", "add", "contended task", "--description", "d", "--json"],
            tmp_path,
            "agent:setup",
        )
        task_id = json.loads(add_result.stdout)[0]["id"]

        n = 8
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", _RUN_CLI, "task", "claim", task_id, "--json"],
                cwd=tmp_path,
                env={**os.environ, "CORVEE_ACTOR": f"agent:{i}"},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for i in range(n)
        ]
        results = [(proc.wait(timeout=30), proc) for proc in processes]

        exit_codes = [code for code, _ in results]
        assert exit_codes.count(0) == 1
        assert all(code in (1, 4) for code in exit_codes if code != 0)

        conn = open_connection(tmp_path / ".corvee" / "corvee.db")
        row = conn.execute("SELECT claimed_by FROM tasks").fetchone()
        conn.close()
        assert row["claimed_by"] is not None

        claim_events = [c for c in range(n) if exit_codes[c] == 0]
        assert len(claim_events) == 1


class TestConcurrentMigration:
    def test_two_processes_migrating_a_fresh_database_apply_each_migration_once(
        self,
        tmp_path: Path,
    ) -> None:
        """6 real processes racing to migrate a fresh database apply the migration exactly once."""
        corvee_dir = tmp_path / ".corvee"
        corvee_dir.mkdir()
        (corvee_dir / "config.toml").write_text('db_path = "corvee.db"\n')
        # No `init` here — the db file doesn't exist yet, so every concurrent
        # command below must bootstrap/migrate it from scratch.

        n = 6
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", _RUN_CLI, "task", "list", "--json"],
                cwd=tmp_path,
                env={**os.environ, "CORVEE_ACTOR": f"agent:{i}"},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for i in range(n)
        ]
        results = [(proc.wait(timeout=30), proc) for proc in processes]
        exit_codes = [code for code, _ in results]
        assert exit_codes == [0] * n

        conn = open_connection(corvee_dir / "corvee.db")
        versions = [
            row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        ]
        conn.close()
        assert versions == sorted(set(versions))
