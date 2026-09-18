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

# (args to invoke, up to but not including the duration flag/value)
_DURATION_INVOCATIONS = [
    (["task", "list", "--stale"], "5x"),
    (["task", "list", "--since"], "5x"),
    (["fact", "list", "--stale"], "5x"),
    (["fact", "list", "--since"], "5x"),
    (["doctor", "--stale"], "5x"),
]


class TestDurationValidation:
    @pytest.mark.parametrize("args, bad_value", _DURATION_INVOCATIONS)
    def test_malformed_duration_is_a_usage_error(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        args: list[str],
        bad_value: str,
    ) -> None:
        """A mistyped duration (e.g. "5x") exits 2, not 1 internal_error."""
        result = runner.invoke(cli, [*args, bad_value, "--json"])
        assert result.exit_code == 2
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] != "internal_error"

    def test_task_show_malformed_since_is_a_usage_error(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`task show --since` goes through the same parse_duration call site."""
        task_id = add_task("task")
        result = runner.invoke(cli, ["task", "show", task_id, "--since", "5x", "--json"])
        assert result.exit_code == 2
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] != "internal_error"
