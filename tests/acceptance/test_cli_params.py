#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click
from click.testing import CliRunner

from corvee.cli.params import StdinOrValue


def _dummy_command() -> click.Command:
    @click.command()
    @click.option("--a", type=StdinOrValue())
    @click.option("--b", type=StdinOrValue())
    def dummy(a: str | None, b: str | None) -> None:
        click.echo(f"a={a!r} b={b!r}")

    return dummy


class TestStdinOrValue:
    def test_plain_value_passes_through(self, runner: CliRunner) -> None:
        """A normal string value passes through untouched."""
        result = runner.invoke(_dummy_command(), ["--a", "hello"])
        assert result.exit_code == 0
        assert "a='hello'" in result.output

    def test_dash_reads_from_stdin(self, runner: CliRunner) -> None:
        """A "-" value is replaced with the full contents of stdin."""
        result = runner.invoke(_dummy_command(), ["--a", "-"], input="from stdin")
        assert result.exit_code == 0
        assert "a='from stdin'" in result.output

    def test_second_dash_in_same_invocation_is_a_usage_error(self, runner: CliRunner) -> None:
        """At most one option may read from stdin per invocation; a second "-" exits 2."""
        result = runner.invoke(_dummy_command(), ["--a", "-", "--b", "-"], input="x")
        assert result.exit_code == 2
