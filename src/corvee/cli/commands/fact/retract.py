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
from corvee.db.facts import retract_fact
from corvee.models import parse_fact_ref
from corvee.output import emit_facts

EPILOG = """\
\b
Examples:
Withdraw a fact that should never have been added:
  corvee fact retract FACT-7
Record why, and get the result as JSON:
  corvee fact retract 7 --reason "added by mistake, claim never held" -o json
Read a long reason from stdin instead of an argument:
  corvee fact retract 7 --reason - -o json <<< "reason read from stdin"
"""


@click.command(epilog=EPILOG)
@click.argument("fact_ref", shell_complete=complete_fact_ids)
@click.option("--reason", "-r", type=StdinOrValue(), default=None)
@output_option()
def retract(fact_ref: str, reason: str | None, output_format: str) -> None:
    """Withdraw a fact; excluded from the default `fact list`."""
    ref = parse_fact_ref(fact_ref)
    with corvee_context(scope=ref.scope) as ctx:
        fact = retract_fact(
            ctx.conn, ref.id, ctx.actor, reason=reason, session_id=ctx.session_id, scope=ref.scope
        )
    emit_facts([fact.to_dict()], output=narrow_output_format(output_format))
