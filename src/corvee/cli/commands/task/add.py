#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
import sqlite3
from pathlib import Path
from typing import Any

import click

from corvee.cli.completion import complete_labels, complete_task_ids
from corvee.cli.context import corvee_context
from corvee.cli.params import StdinOrValue
from corvee.constants import (
    DEFAULT_PRIORITY,
    DEFAULT_TASK_TYPE,
    PRIORITIES,
    TASK_TYPES,
    Scope,
    narrow_priority,
    narrow_task_type,
)
from corvee.db.labels import add_label
from corvee.db.links import link_tasks
from corvee.db.tasks import TaskRow, insert_task, require_task
from corvee.errors import UsageError
from corvee.guards.labels import normalize_label
from corvee.guards.scope import assert_same_scope
from corvee.models import parse_task_ref
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
File a task with a title and a description of how to reproduce it:
  corvee task add "Fix the flaky auth test" --description "repro: run make test twice in a row"
Set its type and priority, and get the result as JSON:
  corvee task add "Investigate slow query" --description "p99 up 3x since Tuesday's deploy" \\
    --type bug --priority high --json
Read a long or multi-line title from stdin instead of an argument:
  corvee task add - --description "multi-line body read separately" <<< "Title from stdin"
Attach a label at creation time:
  corvee task add "Write the migration" --description "adds facts table" --label api --json
File it as a subtask of an existing task:
  corvee task add "Add index" --description "on tasks.claimed_by" --parent TASK-1 --json
File a task that isn't specific to this project:
  corvee task add "Renew the CA cert" --description "expires yearly, not project-specific" --global
File a whole batch from a JSON array in one all-or-nothing transaction:
  corvee task add --from-file backlog.json --json
"""

FROM_FILE_HELP = """\
Read a JSON array of task objects from PATH instead of the TITLE argument
and --description/--type/--priority/--label/--parent options, and create
all of them in one transaction: if any item is invalid, none are created.
Each object supports the same fields as the single-task options: "title"
and "description" (both required, non-empty), "type", "priority", "label"
(a list of strings), and "parent" (an existing task ref, same scope as
this batch). --global still applies to the whole file, the same way it
applies to a single `task add`.
"""


def _task_from_batch_item(path: Path, index: int, item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise UsageError("invalid_batch_file", f"{path}: item {index} is not a JSON object")
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        raise UsageError(
            "invalid_batch_file", f"{path}: item {index} needs a non-empty string title"
        )
    description = item.get("description")
    if not isinstance(description, str) or not description.strip():
        raise UsageError(
            "invalid_batch_file", f"{path}: item {index} needs a non-empty string description"
        )
    type_ = item.get("type", DEFAULT_TASK_TYPE)
    if type_ not in TASK_TYPES:
        raise UsageError(
            "invalid_batch_file", f"{path}: item {index} has an invalid type {type_!r}"
        )
    priority = item.get("priority", DEFAULT_PRIORITY)
    if priority not in PRIORITIES:
        raise UsageError(
            "invalid_batch_file", f"{path}: item {index} has an invalid priority {priority!r}"
        )
    labels = item.get("label", [])
    if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
        raise UsageError(
            "invalid_batch_file", f"{path}: item {index}'s label must be a list of strings"
        )
    parent = item.get("parent")
    if parent is not None and not isinstance(parent, str):
        raise UsageError("invalid_batch_file", f"{path}: item {index}'s parent must be a string")
    return {
        "title": title,
        "description": description,
        "type": type_,
        "priority": priority,
        "labels": labels,
        "parent": parent,
    }


def _load_batch(path: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise UsageError("invalid_batch_file", f"could not read/parse {path}: {exc}") from exc
    if not isinstance(raw, list) or not raw:
        raise UsageError("invalid_batch_file", f"{path} must contain a non-empty JSON array")
    return [_task_from_batch_item(path, index, item) for index, item in enumerate(raw)]


def _insert_one(
    conn: sqlite3.Connection,
    *,
    scope: Scope,
    actor: str,
    session_id: str | None,
    item: dict[str, Any],
) -> TaskRow:
    if not item["title"].strip():
        raise UsageError("invalid_title", "title must not be empty or whitespace-only")
    if not item["description"].strip():
        raise UsageError(
            "invalid_description", "--description must not be empty or whitespace-only"
        )
    task = insert_task(
        conn,
        title=item["title"],
        description=item["description"],
        type_=narrow_task_type(item["type"]),
        priority=narrow_priority(item["priority"]),
        actor=actor,
        session_id=session_id,
    )
    for name in item["labels"]:
        add_label(conn, task.id, normalize_label(name), actor, session_id)
    if item["parent"] is not None:
        parent = parse_task_ref(item["parent"])
        assert_same_scope(parent.scope, scope)
        link_tasks(conn, parent.id, task.id, "parent_of", actor, session_id, scope=scope)
    return require_task(conn, task.id, scope=scope)


@click.command(epilog=EPILOG)
@click.argument("title", type=StdinOrValue(), required=False)
@click.option("--description", "-d", type=StdinOrValue())
@click.option("--type", "-t", "type_", type=click.Choice(TASK_TYPES), default=DEFAULT_TASK_TYPE)
@click.option("--priority", "-p", type=click.Choice(PRIORITIES), default=DEFAULT_PRIORITY)
@click.option(
    "--label",
    "-l",
    "labels",
    multiple=True,
    help="Repeatable.",
    shell_complete=complete_labels,
)
@click.option(
    "--parent",
    "-P",
    "parent_ref",
    help="Link the new task as a child of this task.",
    shell_complete=complete_task_ids,
)
@click.option(
    "--from-file",
    "-f",
    "from_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help=FROM_FILE_HELP,
)
@click.option(
    "--global",
    "-g",
    "is_global",
    is_flag=True,
    help="File into the shared, machine-wide database instead of this project's.",
)
@click.option("--json", "-j", "as_json", is_flag=True)
def add(
    title: str | None,
    description: str | None,
    type_: str,
    priority: str,
    labels: tuple[str, ...],
    parent_ref: str | None,
    from_file: Path | None,
    is_global: bool,
    as_json: bool,
) -> None:
    """Create a task, or a whole batch from --from-file in one transaction."""
    if from_file is not None:
        if title is not None or description is not None:
            raise UsageError(
                "usage_error", "--from-file cannot be combined with TITLE or --description"
            )
        items = _load_batch(from_file)
    else:
        items = [
            {
                "title": title or "",
                "description": description or "",
                "type": type_,
                "priority": priority,
                "labels": list(labels),
                "parent": parent_ref,
            }
        ]

    scope: Scope = "global" if is_global else "local"
    with corvee_context(scope=scope) as ctx:
        # add never claims the task(s) it creates — filing work and starting
        # it are separate acts. All items in one transaction: a bad item
        # anywhere in a --from-file batch rolls back every task in it.
        tasks = [
            _insert_one(
                ctx.conn, scope=scope, actor=ctx.actor, session_id=ctx.session_id, item=item
            )
            for item in items
        ]
    emit_tasks([task.to_dict() for task in tasks], as_json=as_json)
