#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.completion import complete_fact_ids
from corvee.cli.context import corvee_context
from corvee.cli.params import StdinOrValue, output_option
from corvee.constants import narrow_output_format
from corvee.db.facts import revise_fact
from corvee.errors import require_non_empty
from corvee.models import parse_fact_ref
from corvee.output import emit_facts

EPILOG = """\
\b
Examples:
Correct a fact's claim text:
  corvee fact revise FACT-7 "Corrected claim text"
Fix a wrong claim; a verified fact resets to unverified:
  corvee fact revise 7 "package X is Apache-2.0, not MIT" -o json
Read a long or multi-line replacement claim from stdin:
  corvee fact revise 7 - -o json <<< "multi-line replacement claim text"
"""


@click.command(epilog=EPILOG)
@click.argument("fact_ref", shell_complete=complete_fact_ids)
@click.argument("new_claim", type=StdinOrValue())
@output_option()
def revise(fact_ref: str, new_claim: str, output_format: str) -> None:
    """Change a fact's claim text."""
    require_non_empty(new_claim, "invalid_claim", "new_claim must not be empty or whitespace-only")
    ref = parse_fact_ref(fact_ref)
    with corvee_context(scope=ref.scope) as ctx:
        fact = revise_fact(
            ctx.conn, ref.id, new_claim, ctx.actor, session_id=ctx.session_id, scope=ref.scope
        )
    emit_facts([fact.to_dict()], output=narrow_output_format(output_format))
