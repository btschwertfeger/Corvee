#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.commands.task.add import add
from corvee.cli.commands.task.assign import assign
from corvee.cli.commands.task.claim import claim
from corvee.cli.commands.task.claims import claims
from corvee.cli.commands.task.comment import comment
from corvee.cli.commands.task.label import label
from corvee.cli.commands.task.labels import labels_command
from corvee.cli.commands.task.link import link
from corvee.cli.commands.task.list_ import list_command
from corvee.cli.commands.task.mine import mine
from corvee.cli.commands.task.purge import purge
from corvee.cli.commands.task.ready import ready
from corvee.cli.commands.task.search import search
from corvee.cli.commands.task.show import show
from corvee.cli.commands.task.start import start
from corvee.cli.commands.task.tree import tree
from corvee.cli.commands.task.unassign import unassign
from corvee.cli.commands.task.unclaim import unclaim
from corvee.cli.commands.task.unlink import unlink
from corvee.cli.commands.task.update import update
from corvee.cli.params import AliasGroup


@click.group(name="task", cls=AliasGroup, hidden_aliases={"ls"})
def task_group() -> None:
    """Work items: create, query, mutate, claim, label, link."""


task_group.add_command(add)
task_group.add_command(assign)
task_group.add_command(unassign)
task_group.add_command(list_command)
task_group.add_command(list_command, name="ls")
task_group.add_command(ready)
task_group.add_command(search)
task_group.add_command(mine)
task_group.add_command(show)
task_group.add_command(update)
task_group.add_command(claim)
task_group.add_command(claims)
task_group.add_command(unclaim)
task_group.add_command(start)
task_group.add_command(label)
task_group.add_command(labels_command)
task_group.add_command(comment)
task_group.add_command(link)
task_group.add_command(unlink)
task_group.add_command(tree)
task_group.add_command(purge)
