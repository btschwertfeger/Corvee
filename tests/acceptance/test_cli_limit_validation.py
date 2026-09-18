#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from collections.abc import Callable

import pytest
from click.testing import CliRunner

from corvee.cli.main import cli
from corvee.config import ProjectConfig

# (command, extra args required before --limit can be reached)
_LIMIT_COMMANDS = [
    ("task", ["list"]),
    ("task", ["ready"]),
    ("task", ["search", "x"]),
    ("task", ["mine"]),
    ("fact", ["list"]),
    ("fact", ["search", "x"]),
]


class TestLimitValidation:
    @pytest.mark.parametrize("group, args", _LIMIT_COMMANDS)
    def test_negative_limit_is_a_usage_error(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        group: str,
        args: list[str],
        add_task: Callable[[str], str],
    ) -> None:
        """A negative --limit exits 2 instead of silently slicing from the end."""
        add_task("a")
        result = runner.invoke(cli, [group, *args, "--limit", "-1"])
        assert result.exit_code == 2

    @pytest.mark.parametrize("group, args", _LIMIT_COMMANDS)
    def test_zero_limit_is_a_usage_error(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        group: str,
        args: list[str],
        add_task: Callable[[str], str],
    ) -> None:
        """A --limit of 0 exits 2 rather than silently returning an empty result."""
        add_task("a")
        result = runner.invoke(cli, [group, *args, "--limit", "0"])
        assert result.exit_code == 2

    @pytest.mark.parametrize("group, args", _LIMIT_COMMANDS)
    def test_positive_limit_still_works(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        group: str,
        args: list[str],
        add_task: Callable[[str], str],
    ) -> None:
        """A valid positive --limit is unaffected by the added bound."""
        add_task("a")
        result = runner.invoke(cli, [group, *args, "--limit", "1", "--json"])
        assert result.exit_code == 0
