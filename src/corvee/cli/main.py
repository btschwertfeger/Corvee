#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sys
from typing import Any

import click

from corvee import __version__
from corvee.cli.commands.brief import brief
from corvee.cli.commands.completion import completion
from corvee.cli.commands.doctor import doctor
from corvee.cli.commands.explain import explain
from corvee.cli.commands.export import export
from corvee.cli.commands.fact import fact_group
from corvee.cli.commands.import_ import import_command
from corvee.cli.commands.init import init
from corvee.cli.commands.mcp import mcp_group
from corvee.cli.commands.task import task_group
from corvee.db.schema import CURRENT_SCHEMA_VERSION
from corvee.errors import CorveeError, UsageError
from corvee.output import emit_error


def _print_version(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return
    # --version prints both the package version and the schema version this
    # binary supports, so the exit-6 refusal can be diagnosed without
    # guessing which install is stale.
    click.echo(f"corvee, version {__version__} (schema {CURRENT_SCHEMA_VERSION})")
    ctx.exit()


class CorveeGroup(click.Group):
    """Routes every failure through the documented {"error": {...}} JSON-on-stderr
    shape and its exit code, including click's own usage errors — not just
    corvee's. Overriding `main()` (rather than wrapping only the console-script
    entry point) means `CliRunner`-based tests exercise this exact path too.
    """

    def main(self, *args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("standalone_mode", False)
        try:
            exit_code = super().main(*args, **kwargs)
        except CorveeError as error:
            emit_error(error)
            sys.exit(error.exit_code)
        except click.ClickException as error:
            emit_error(UsageError("usage_error", error.format_message()))
            sys.exit(error.exit_code)
        except click.Abort:
            sys.exit(1)
        except Exception as error:
            emit_error(CorveeError("internal_error", str(error)))
            sys.exit(1)
        else:
            sys.exit(exit_code if isinstance(exit_code, int) else 0)


GROUP_EPILOG = """\
\b
Examples:
Identify the caller without exporting environment variables first, so a
bare "corvee ..." prefix stays allowlist-friendly for a permission-gated
agent harness:
  corvee --actor agent:claude --session-id session-42 task list --json
"""


@click.group(cls=CorveeGroup, epilog=GROUP_EPILOG)
@click.option(
    "--version",
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=_print_version,
    help="Show the corvee and schema version and exit.",
)
@click.option(
    "--actor",
    help="Stable identity for this invocation (e.g. agent:claude). "
    "Overrides $CORVEE_ACTOR for every subcommand.",
)
@click.option(
    "--session-id",
    help="Per-session token stamped on events. "
    "Overrides $CORVEE_SESSION_ID for every subcommand.",
)
def cli(actor: str | None, session_id: str | None) -> None:
    """corvee: a single-machine, non-git-tracked, persistent,
    multi-agent-aware CLI task tracker and fact store."""


cli.add_command(init)
cli.add_command(brief)
cli.add_command(task_group)
cli.add_command(fact_group)
cli.add_command(export)
cli.add_command(import_command)
cli.add_command(doctor)
cli.add_command(explain)
cli.add_command(completion)
cli.add_command(mcp_group)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
