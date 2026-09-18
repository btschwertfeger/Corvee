#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.completion import complete_fact_ids
from corvee.cli.context import corvee_context
from corvee.cli.params import StdinOrValue
from corvee.db.facts import unverify_fact
from corvee.models import parse_fact_ref
from corvee.output import emit_facts

EPILOG = """\
\b
Examples:
Move a verified fact back to unverified:
  corvee fact unverify FACT-7
Record why, and get the result as JSON:
  corvee fact unverify 7 --note "proof link is now dead" --json
Read a long note from stdin instead of an argument:
  corvee fact unverify 7 --note - --json <<< "reason read from stdin"
"""


@click.command(epilog=EPILOG)
@click.argument("fact_ref", shell_complete=complete_fact_ids)
@click.option("--note", "-m", type=StdinOrValue(), default=None)
@click.option("--json", "-j", "as_json", is_flag=True)
def unverify(fact_ref: str, note: str | None, as_json: bool) -> None:
    """Mark a fact unverified again."""
    ref = parse_fact_ref(fact_ref)
    with corvee_context(scope=ref.scope) as ctx:
        fact = unverify_fact(
            ctx.conn, ref.id, ctx.actor, note=note, session_id=ctx.session_id, scope=ref.scope
        )
    emit_facts([fact.to_dict()], as_json=as_json)
