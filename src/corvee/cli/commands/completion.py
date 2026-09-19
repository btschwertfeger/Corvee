#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click
import click.shell_completion

_COMPLETE_VAR = "_CORVEE_COMPLETE"
_SHELLS = ("bash", "zsh", "fish")

EPILOG = """\
\b
Examples:
Print the bash activation script, to inspect before trusting it:
  corvee completion bash
Print the zsh script instead:
  corvee completion zsh
Print the fish script instead:
  corvee completion fish

Enable it by `eval`ing the output, e.g. once per shell session:
  eval "$(corvee completion bash)"
Or permanently, by adding the same line to your shell's rc file:
  echo 'eval "$(corvee completion bash)"' >> ~/.bashrc
"""


@click.command(epilog=EPILOG)
@click.argument("shell", type=click.Choice(_SHELLS))
def completion(shell: str) -> None:
    """Print a shell completion script; `eval` its output to enable it.

    Covers subcommand and flag names, click.Choice values (--state,
    --priority, ...), and TASK-<n>/FACT-<n> arguments completed against
    real ids in the current project.
    """
    root_cli = click.get_current_context().find_root().command

    comp_cls = click.shell_completion.get_completion_class(shell)
    if comp_cls is None:
        # Unreachable: click.Choice(_SHELLS) already restricts to known shells.
        raise AssertionError(f"no completion support for shell {shell!r}")
    click.echo(comp_cls(root_cli, {}, "corvee", _COMPLETE_VAR).source())
