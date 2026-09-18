#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click
import click.shell_completion

from corvee.cli.context import corvee_context
from corvee.cli.scope import fetch_merged, sort_facts, sort_tasks
from corvee.db.facts import FactFilter, list_facts
from corvee.db.labels import list_labels_with_counts
from corvee.db.tasks import TaskFilter, list_tasks
from corvee.errors import CorveeError


def complete_task_ids(
    ctx: click.Context, param: click.Parameter, incomplete: str
) -> list[click.shell_completion.CompletionItem]:
    """Shell-complete a TASK-<n>/TASK-GLOBAL-<n> argument against real ids,
    merged across local and global (§3.3) the same way `--scope all` does.

    Silent on any corvee-raised failure -- outside a project, or against a
    database on a newer schema than this binary, tab completion just offers
    nothing rather than erroring into the middle of the user's shell prompt.
    """
    del ctx, param
    try:
        tasks = fetch_merged(
            "all", lambda conn, scope: list_tasks(conn, TaskFilter(include_all=True), scope=scope)
        )
    except CorveeError:
        return []
    return [
        click.shell_completion.CompletionItem(task_id, help=task.title[:60])
        for task in sort_tasks(tasks)
        if (task_id := task.to_dict()["id"]).startswith(incomplete)
    ]


def complete_fact_ids(
    ctx: click.Context, param: click.Parameter, incomplete: str
) -> list[click.shell_completion.CompletionItem]:
    """The fact-group equivalent of `complete_task_ids`."""
    del ctx, param
    try:
        facts = fetch_merged(
            "all", lambda conn, scope: list_facts(conn, FactFilter(include_all=True), scope=scope)
        )
    except CorveeError:
        return []
    return [
        click.shell_completion.CompletionItem(fact_id, help=fact.claim[:60])
        for fact in sort_facts(facts)
        if (fact_id := fact.to_dict()["id"]).startswith(incomplete)
    ]


def complete_labels(
    ctx: click.Context, param: click.Parameter, incomplete: str
) -> list[click.shell_completion.CompletionItem]:
    """Shell-complete a label name against the local project's real labels.

    Labels aren't merged across scope (§3.3, like `task labels` itself), so
    this only ever looks at the local project, not `--scope all`.
    """
    del ctx, param
    try:
        with corvee_context(write=False) as project_ctx:
            labels = list_labels_with_counts(project_ctx.conn)
    except CorveeError:
        return []
    return [
        click.shell_completion.CompletionItem(name)
        for name, _ in labels
        if name.startswith(incomplete)
    ]
