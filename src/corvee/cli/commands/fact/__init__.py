#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.commands.fact.add import add
from corvee.cli.commands.fact.delete import delete
from corvee.cli.commands.fact.list_ import list_command
from corvee.cli.commands.fact.retract import retract
from corvee.cli.commands.fact.revise import revise
from corvee.cli.commands.fact.search import search
from corvee.cli.commands.fact.show import show
from corvee.cli.commands.fact.unverify import unverify
from corvee.cli.commands.fact.verify import verify
from corvee.cli.params import AliasGroup


@click.group(name="fact", cls=AliasGroup, hidden_aliases={"ls"})
def fact_group() -> None:
    """Standalone, checked-true claims, kept separate from tasks.

    \b
    Lifecycle: a fact starts unverified. `verify` marks it verified with
    proof and a timestamp; `unverify` moves it back. `revise` changes the
    claim text and, if it was verified, resets it to unverified, since the
    old proof said nothing about the new text. `retract` withdraws a fact
    that should not have existed, dropping it out of the default `list`;
    `verify`, `unverify`, and `revise` all still work on a retracted fact
    and bring it back into the normal flow.
    """


fact_group.add_command(add)
fact_group.add_command(list_command)
fact_group.add_command(list_command, name="ls")
fact_group.add_command(search)
fact_group.add_command(show)
fact_group.add_command(verify)
fact_group.add_command(unverify)
fact_group.add_command(revise)
fact_group.add_command(retract)
fact_group.add_command(delete)
