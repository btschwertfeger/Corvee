#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from contextlib import ExitStack

import click

from corvee.cli.completion import complete_fact_ids
from corvee.cli.context import corvee_context
from corvee.constants import Scope
from corvee.db.events import get_fact_events
from corvee.db.facts import require_facts
from corvee.models import parse_fact_refs
from corvee.output import emit_fact_detail
from corvee.references import find_referenced

EPILOG = """\
\b
Examples:
See full detail for one fact:
  corvee fact show FACT-7
Show several facts at once, as JSON:
  corvee fact show 7 8 9 --json
Pull out just the revision/verification history:
  corvee fact show FACT-7 --json | jq '.[0].events'
"""


@click.command(epilog=EPILOG)
@click.argument("ids", nargs=-1, required=True, shell_complete=complete_fact_ids)
@click.option("--json", "-j", "as_json", is_flag=True)
def show(ids: tuple[str, ...], as_json: bool) -> None:
    """Full detail for one or more facts: claim, status, current proof, timeline."""
    fact_ids, scope = parse_fact_refs(ids)
    other_scope: Scope = "global" if scope == "local" else "local"
    results = []
    with ExitStack() as stack:
        ctx = stack.enter_context(corvee_context(write=False, scope=scope))
        other_conn_holder: list[sqlite3.Connection] = []

        def other_conn() -> sqlite3.Connection:
            if not other_conn_holder:
                other_ctx = stack.enter_context(corvee_context(write=False, scope=other_scope))
                other_conn_holder.append(other_ctx.conn)
            return other_conn_holder[0]

        facts = require_facts(ctx.conn, fact_ids, scope=scope)
        for fact in facts:
            detail = fact.to_dict()
            events = get_fact_events(ctx.conn, fact.id)
            detail["events"] = events
            detail["referenced"] = find_referenced(
                [
                    fact.claim,
                    fact.proof,
                    *(event.get("old_value") for event in events),
                    *(event.get("new_value") for event in events),
                    *(event.get("proof") for event in events),
                    *(event.get("note") for event in events),
                ],
                own_kind="fact",
                own_id=fact.id,
                own_scope=scope,
                same_scope_conn=ctx.conn,
                other_scope_conn=other_conn,
            )
            results.append(detail)
    emit_fact_detail(results, as_json=as_json)
