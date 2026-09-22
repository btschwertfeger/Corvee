#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.completion import complete_labels, complete_task_ids
from corvee.cli.scope import fetch_merged, paginate_after, resolve_cursor, sort_tasks
from corvee.constants import SCOPE_FILTERS, narrow_scope_filter
from corvee.db.tasks import ready_tasks
from corvee.guards.fields import validate_fields
from corvee.guards.labels import normalize_label
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
See what's unclaimed, unblocked, and could be started right now:
  corvee task ready --json
Narrow to one label, trimmed to a couple of fields:
  corvee task ready --label api --json --fields id,title
Cap the result to the five highest-priority candidates:
  corvee task ready --limit 5 --json
List only the ready tasks filed with --global:
  corvee task ready --scope global --json
Page through a long ready list, 20 rows at a time:
  corvee task ready --after TASK-88 --limit 20 --json
"""


@click.command(epilog=EPILOG)
@click.option("--label", "-l", "labels", multiple=True, shell_complete=complete_labels)
@click.option("--scope", "-s", "scope_filter", type=click.Choice(SCOPE_FILTERS), default="all")
@click.option(
    "--after",
    "-k",
    "after_ref",
    help="Cursor: only tasks after this id in the fixed order.",
    shell_complete=complete_task_ids,
)
@click.option("--limit", "-n", type=click.IntRange(min=1))
@click.option("--fields", "-f", "fields_csv")
@click.option("--json", "-j", "as_json", is_flag=True)
def ready(
    labels: tuple[str, ...],
    scope_filter: str,
    after_ref: str | None,
    limit: int | None,
    fields_csv: str | None,
    as_json: bool,
) -> None:
    """Unclaimed open tasks with no open blocks predecessor — what can start right now."""
    fields = validate_fields(fields_csv.split(",")) if fields_csv else None
    label_filters = tuple(normalize_label(name) for name in labels)
    # --limit applies after the merge, never per scope.
    tasks = sort_tasks(
        fetch_merged(
            narrow_scope_filter(scope_filter),
            lambda conn, s: ready_tasks(conn, labels=label_filters, scope=s),
        )
    )
    if after_ref is not None:
        tasks = paginate_after(tasks, resolve_cursor(after_ref))
    if limit is not None:
        tasks = tasks[:limit]
    emit_tasks([t.to_dict() for t in tasks], as_json=as_json, fields=fields)
