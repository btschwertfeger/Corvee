#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.completion import complete_fact_ids
from corvee.cli.context import corvee_context
from corvee.cli.params import StdinOrValue
from corvee.db.facts import revise_fact
from corvee.models import parse_fact_ref
from corvee.output import emit_facts

EPILOG = """\
\b
Examples:
Correct a fact's claim text:
  corvee fact revise FACT-7 "Corrected claim text"
Fix a wrong claim; a verified fact resets to unverified:
  corvee fact revise 7 "package X is Apache-2.0, not MIT" --json
Read a long or multi-line replacement claim from stdin:
  corvee fact revise 7 - --json <<< "multi-line replacement claim text"
"""


@click.command(epilog=EPILOG)
@click.argument("fact_ref", shell_complete=complete_fact_ids)
@click.argument("new_claim", type=StdinOrValue())
@click.option("--json", "-j", "as_json", is_flag=True)
def revise(fact_ref: str, new_claim: str, as_json: bool) -> None:
    """Change a fact's claim text."""
    ref = parse_fact_ref(fact_ref)
    with corvee_context(scope=ref.scope) as ctx:
        fact = revise_fact(
            ctx.conn, ref.id, new_claim, ctx.actor, session_id=ctx.session_id, scope=ref.scope
        )
    emit_facts([fact.to_dict()], as_json=as_json)
