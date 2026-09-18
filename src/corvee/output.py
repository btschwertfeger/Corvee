#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
from collections.abc import Sequence
from typing import Any

import click

from corvee.constants import (
    FACT_LIST_FIELDS,
    FACT_LIST_TABLE_DEFAULT_FIELDS,
    LIST_FIELDS,
    LIST_TABLE_DEFAULT_FIELDS,
)
from corvee.errors import CorveeError


def filter_fields(task: dict[str, Any], fields: Sequence[str] | None) -> dict[str, Any]:
    """Project `task` down to `fields`, preserving the requested order.

    None means no projection — the full documented shape.
    """
    if fields is None:
        return task
    return {field: task[field] for field in fields}


def render_table(
    tasks: Sequence[dict[str, Any]],
    fields: Sequence[str] | None = None,
    *,
    default_fields: Sequence[str] = LIST_FIELDS,
) -> str:
    """Fixed-width table of `tasks`, showing `fields` or `default_fields`."""
    if not tasks:
        return ""
    columns = list(fields) if fields is not None else list(default_fields)
    rows = [
        [str(task.get(column, "")).replace("\r\n", " ").replace("\n", " ") for column in columns]
        for task in tasks
    ]
    widths = [max(len(column), *(len(row[i]) for row in rows)) for i, column in enumerate(columns)]
    header = "  ".join(column.upper().ljust(widths[i]) for i, column in enumerate(columns))
    lines = [header]
    for row in rows:
        lines.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
    return "\n".join(lines)


def render_detail_header(
    row: dict[str, Any],
    columns: Sequence[str],
    *,
    block_field: str,
) -> str:
    """Markdown-style `field: value` lines for one record — the single-record
    replacement for `render_table`'s fixed-width row, which overflows once a
    long free-text column (`description`/`proof`) is included.

    `block_field` is rendered as its own labeled block below the flat fields
    instead of inline, and only when it's actually one of `columns` — a
    caller that projected it out via `--fields` keeps it out here too.
    """
    flat_columns = [column for column in columns if column != block_field]
    lines = [f"{column}: {row.get(column, '')}" for column in flat_columns]
    if block_field in columns:
        value = row.get(block_field)
        lines.append("")
        lines.append(f"{block_field}:")
        lines.append(str(value) if value not in (None, "") else "(none)")
    return "\n".join(lines)


def _format_event_line(event: dict[str, Any]) -> str:
    """One human-readable line for a task_events/fact_events row.

    Each `kind` carries its payload in a different column (`body` for a
    comment, `old_value`/`new_value` for a field change or revision, `proof`
    for a verification, `note` for an unverify/retract) — this is the one
    place that knows how to read each kind back out.
    """
    kind = event["kind"]
    detail = ""
    if kind == "comment":
        detail = event.get("body") or ""
    elif kind == "field_change":
        detail = f"{event.get('field')}: {event.get('old_value')} -> {event.get('new_value')}"
    elif kind == "created":
        detail = event.get("new_value") or ""
    elif kind == "revised":
        detail = f"{event.get('old_value')!r} -> {event.get('new_value')!r}"
    elif kind == "verified":
        detail = f"proof: {event.get('proof')}"
    elif kind in ("unverified", "retracted"):
        detail = event.get("note") or ""
    prefix = f"  {event['created_at']}  {event['actor']}  {kind}"
    return f"{prefix}  {detail}" if detail else prefix


def render_detail_sections(row: dict[str, Any]) -> str:
    """Human-readable labels/links/subtasks/events sections for `task show` and
    `fact show`'s plain-text output.

    `render_table` only ever shows flat columns, so these nested keys (added
    on top of the base task/fact shape only by the `show` commands) would
    otherwise be visible in `--json` output only.
    """
    lines: list[str] = []
    if "labels" in row:
        lines.append(f"labels: {', '.join(row['labels']) or '(none)'}")
    if "links" in row:
        links = row["links"]
        if links:
            lines.append("links:")
            lines.extend(
                f"  {link['direction']} {link['relation']} {link['task_id']}" for link in links
            )
        else:
            lines.append("links: (none)")
    if "subtasks" in row:
        lines.append(f"subtasks: {', '.join(row['subtasks']) or '(none)'}")
    if "referenced" in row:
        lines.append(f"referenced: {', '.join(row['referenced']) or '(none)'}")
    if "events" in row:
        events = row["events"]
        if events:
            lines.append("events:")
            lines.extend(_format_event_line(event) for event in events)
        else:
            lines.append("events: (none)")
    return "\n".join(lines)


def _emit(
    rows: Sequence[dict[str, Any]],
    *,
    as_json: bool,
    fields: Sequence[str] | None,
    default_fields: Sequence[str],
) -> None:
    projected = [filter_fields(row, fields) for row in rows]
    if as_json:
        click.echo(json.dumps(projected))
        return
    table = render_table(projected, fields, default_fields=default_fields)
    if table:
        click.echo(table)


def emit_tasks(
    tasks: Sequence[dict[str, Any]],
    *,
    as_json: bool,
    fields: Sequence[str] | None = None,
) -> None:
    """Print `tasks` as a JSON array or a table — the one place that owns this shape."""
    _emit(tasks, as_json=as_json, fields=fields, default_fields=LIST_TABLE_DEFAULT_FIELDS)


def emit_facts(
    facts: Sequence[dict[str, Any]],
    *,
    as_json: bool,
    fields: Sequence[str] | None = None,
) -> None:
    """Print `facts` as a JSON array or a table — the fact-group equivalent of emit_tasks."""
    _emit(facts, as_json=as_json, fields=fields, default_fields=FACT_LIST_TABLE_DEFAULT_FIELDS)


def _emit_with_detail(
    rows: Sequence[dict[str, Any]],
    *,
    as_json: bool,
    fields: Sequence[str] | None,
    default_fields: Sequence[str],
    block_field: str,
) -> None:
    projected = [filter_fields(row, fields) for row in rows]
    if as_json:
        click.echo(json.dumps(projected))
        return
    columns = list(fields) if fields is not None else list(default_fields)
    for index, row in enumerate(projected):
        if index:
            click.echo()
        click.echo(render_detail_header(row, columns, block_field=block_field))
        detail = render_detail_sections(rows[index])
        if detail:
            click.echo()
            click.echo(detail)


def emit_task_detail(
    tasks: Sequence[dict[str, Any]],
    *,
    as_json: bool,
    fields: Sequence[str] | None = None,
) -> None:
    """`emit_tasks`, but plain-text output also includes labels/links/subtasks/events
    -- for `task show`, where those keys are always present on each row.
    """
    _emit_with_detail(
        tasks, as_json=as_json, fields=fields, default_fields=LIST_FIELDS, block_field="description"
    )


def emit_fact_detail(
    facts: Sequence[dict[str, Any]],
    *,
    as_json: bool,
    fields: Sequence[str] | None = None,
) -> None:
    """`emit_facts`, but plain-text output also includes the event history --
    for `fact show`, where the events key is always present on each row.
    """
    _emit_with_detail(
        facts, as_json=as_json, fields=fields, default_fields=FACT_LIST_FIELDS, block_field="proof"
    )


def emit_error(error: CorveeError) -> None:
    """Failure always writes a JSON object to stderr, regardless of --json."""
    click.echo(json.dumps(error.to_json()), err=True)
