#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#
import json
from collections.abc import Callable

import pytest
from click.testing import CliRunner

from corvee.cli.main import cli
from corvee.config import ProjectConfig


class TestClaims:
    def test_empty_project_returns_empty_array(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """No claims at all returns [], not an error."""
        result = runner.invoke(cli, ["task", "claims", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_groups_by_actor_across_different_claimants(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        monkeypatch: pytest.MonkeyPatch,
        add_task: Callable[[str], str],
    ) -> None:
        """Each actor holding a live claim gets one row with its count and scope."""
        first = add_task("first")
        second = add_task("second")
        runner.invoke(cli, ["task", "claim", first])
        monkeypatch.setenv("CORVEE_ACTOR", "agent:other")
        runner.invoke(cli, ["task", "claim", second])

        result = runner.invoke(cli, ["task", "claims", "--json"])
        payload = {row["actor"]: row for row in json.loads(result.output)}
        assert payload["agent:test"]["count"] == 1
        assert payload["agent:other"]["count"] == 1
        assert payload["agent:test"]["scope"] == "local"
