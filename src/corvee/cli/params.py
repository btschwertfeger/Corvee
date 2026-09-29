#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sys
from collections.abc import Callable, Collection
from typing import Any

import click
from click.decorators import FC

from corvee.constants import OUTPUT_FORMATS

_STDIN_CONSUMED_KEY = "corvee_stdin_consumed"


def output_option(*, wide: bool = False) -> Callable[[FC], FC]:
    """`-o/--output`, defaulting to `table`.

    `wide=True` (the row-listing commands: `task list`/`ready`/`search`/
    `mine`, `fact list`/`search`, `brief`) also accepts `wide`, which widens
    the table's default column set (`constants.py`'s `*_TABLE_WIDE_FIELDS`)
    without becoming a full `--fields` projection. Every other command
    keeps `wide` out of its choice set entirely rather than accepting it as
    a silent no-op, since its table already shows everything relevant to
    one mutated row or a fixed-shape aggregate.
    """
    choices = OUTPUT_FORMATS if wide else ("table", "json")
    return click.option(
        "--output",
        "-o",
        "output_format",
        type=click.Choice(choices),
        default="table",
        show_default=True,
    )


class AliasGroup(click.Group):
    """A `click.Group` where some registered command names are invocable but
    excluded from the `--help` "Commands:" listing — for aliases like `ls` that
    would otherwise show up as a separate entry with the same help text as the
    command they alias.
    """

    def __init__(self, *args: Any, hidden_aliases: Collection[str] = (), **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.hidden_aliases = set(hidden_aliases)

    def list_commands(self, ctx: click.Context) -> list[str]:
        return [name for name in super().list_commands(ctx) if name not in self.hidden_aliases]


class StdinOrValue(click.ParamType[str]):
    """A text param that reads from stdin when given `-`.

    At most one `-` per invocation, since stdin can only be read once; a
    second one is a usage error (exit 2).
    """

    name = "text"

    def convert(
        self,
        value: Any,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> str:
        if value != "-":
            return str(value)
        if ctx is not None and ctx.meta.get(_STDIN_CONSUMED_KEY):
            self.fail("at most one option may read from stdin (`-`) per invocation", param, ctx)
        if ctx is not None:
            ctx.meta[_STDIN_CONSUMED_KEY] = True
        return sys.stdin.read()
