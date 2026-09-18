#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
import sqlite3
from typing import Any

import click

from corvee.cli.completion import complete_task_ids
from corvee.cli.context import corvee_context
from corvee.constants import Scope
from corvee.db.links import get_children
from corvee.db.tasks import require_task
from corvee.models import parse_task_ref, task_ref

EPILOG = """\
\b
Examples:
See everything under an epic, several levels deep:
  corvee task tree TASK-1
Get the same tree as nested JSON:
  corvee task tree TASK-1 --json
Pull out every id in the subtree with jq:
  corvee task tree TASK-1 --json | jq -r '.. | .id? // empty'
"""


def _build_tree(conn: sqlite3.Connection, root_id: int, scope: Scope) -> dict[str, Any]:
    """Nested {id, state, title, children} for the `parent_of` subtree at `root_id`.

    Iterative in both passes — walking the graph and rendering the result —
    a hand-edited cycle stops at the first already-visited id (the visited
    set is seeded with `root_id`) instead of hanging, and a plain long chain
    can't blow a recursion limit either, the same reasoning
    `guards/ancestry.py:is_reachable` and the fixed `cascade_cancel_descendants`
    already apply to graph walks over this data.
    """
    visited = {root_id}
    children_of: dict[int, list[int]] = {}
    discovery_order = [root_id]
    stack = [root_id]
    while stack:
        current = stack.pop()
        kids = [child for child in get_children(conn, current) if child not in visited]
        visited.update(kids)
        children_of[current] = kids
        discovery_order.extend(kids)
        stack.extend(kids)

    nodes: dict[int, dict[str, Any]] = {}
    for task_id in reversed(discovery_order):
        task = require_task(conn, task_id, scope=scope)
        nodes[task_id] = {
            "id": task_ref(task_id, scope),
            "state": task.state,
            "title": task.title,
            "children": [nodes[child_id] for child_id in children_of[task_id]],
        }
    return nodes[root_id]


def _render_lines(root: dict[str, Any]) -> list[str]:
    lines = []
    stack: list[tuple[dict[str, Any], int]] = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        lines.append(f"{'  ' * depth}{node['id']} [{node['state']}] {node['title']}")
        for child in reversed(node["children"]):
            stack.append((child, depth + 1))
    return lines


@click.command(name="tree", epilog=EPILOG)
@click.argument("ref", shell_complete=complete_task_ids)
@click.option("--json", "-j", "as_json", is_flag=True)
def tree(ref: str, as_json: bool) -> None:
    """The full parent_of subtree rooted at <id>, as a tree instead of a flat list."""
    parsed = parse_task_ref(ref)
    with corvee_context(write=False, scope=parsed.scope) as ctx:
        result = _build_tree(ctx.conn, parsed.id, parsed.scope)
    if as_json:
        click.echo(json.dumps(result))
    else:
        click.echo("\n".join(_render_lines(result)))
