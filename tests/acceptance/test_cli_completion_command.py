#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from click.testing import CliRunner

from corvee.cli.main import cli


class TestCompletionCommand:
    def test_bash_prints_an_activation_script(self, runner: CliRunner) -> None:
        """`corvee completion bash` succeeds and prints a script mentioning corvee."""
        result = runner.invoke(cli, ["completion", "bash"])
        assert result.exit_code == 0
        assert "_CORVEE_COMPLETE" in result.output
        assert "corvee" in result.output

    def test_zsh_and_fish_are_also_supported(self, runner: CliRunner) -> None:
        """The other two shells click supports out of the box also work."""
        for shell in ("zsh", "fish"):
            result = runner.invoke(cli, ["completion", shell])
            assert result.exit_code == 0
            assert result.output.strip()

    def test_rejects_an_unsupported_shell(self, runner: CliRunner) -> None:
        """A shell outside bash/zsh/fish exits 2, same as any other bad --choice value."""
        result = runner.invoke(cli, ["completion", "powershell"])
        assert result.exit_code == 2
