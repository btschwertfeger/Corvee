#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from corvee.cli.main import cli

# GH#23: a purely-global call should work from any directory, with no
# `.corvee/config.toml` anywhere upward from cwd — the `--scope all`-default
# commands should behave like a missing local project is just an empty
# scope, the same way a missing global database already does.


@pytest.fixture(autouse=True)
def _no_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


class TestDefaultScopeAllOutsideAProject:
    @pytest.mark.parametrize(
        "args",
        [
            ["task", "list", "--json"],
            ["task", "ready", "--json"],
            ["task", "search", "x", "--json"],
            ["task", "mine", "--json"],
            ["task", "claims", "--json"],
            ["fact", "list", "--json"],
            ["fact", "search", "x", "--json"],
            ["brief", "--json"],
        ],
    )
    def test_succeeds_with_empty_result(self, runner: CliRunner, args: list[str]) -> None:
        """Every --scope-all-default command runs clean outside a project, empty result."""
        result = runner.invoke(cli, args)
        assert result.exit_code == 0, result.output

    def test_task_add_global_then_task_mine_finds_it(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A global task filed and worked entirely from outside any project (§3.3's
        "not project-specific" case) round-trips through the default --scope all.
        """
        monkeypatch.setenv("CORVEE_ACTOR", "agent:test")
        add_result = runner.invoke(
            cli, ["task", "add", "renew CA cert", "--description", "d", "--global", "--json"]
        )
        assert add_result.exit_code == 0
        task_id = json.loads(add_result.output)[0]["id"]

        claim_result = runner.invoke(cli, ["task", "claim", task_id, "--json"])
        assert claim_result.exit_code == 0

        mine_result = runner.invoke(cli, ["task", "mine", "--json"])
        assert mine_result.exit_code == 0
        assert [t["id"] for t in json.loads(mine_result.output)] == [task_id]

        ready_result = runner.invoke(cli, ["brief", "--json"])
        assert ready_result.exit_code == 0
        assert [t["id"] for t in json.loads(ready_result.output)["mine"]] == [task_id]


class TestExplicitScopeLocalOutsideAProject:
    @pytest.mark.parametrize(
        "args",
        [
            ["task", "list", "--scope", "local", "--json"],
            ["fact", "list", "--scope", "local", "--json"],
        ],
    )
    def test_still_fails_loudly(self, runner: CliRunner, args: list[str]) -> None:
        """--scope local, asked for explicitly, is a real usage error outside a project,
        not silently empty — unlike the --scope-all default above.
        """
        result = runner.invoke(cli, args)
        assert result.exit_code == 6
        payload = json.loads(result.output)
        assert payload["error"]["code"] == "no_project"
