#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.completion import complete_fact_ids
from corvee.cli.context import corvee_context
from corvee.db.facts import delete_fact
from corvee.models import parse_fact_ref
from corvee.output import emit_facts

EPILOG = """\
\b
Examples:
Retract a fact first, then permanently remove it:
  corvee fact retract FACT-7 && corvee fact delete FACT-7
Delete an already-retracted fact and get the result as JSON:
  corvee fact delete 7 --json
Deleting a fact that was never retracted fails, on purpose:
  corvee fact delete 7  # fails with fact_not_retracted unless already retracted
"""


@click.command(epilog=EPILOG)
@click.argument("fact_ref", shell_complete=complete_fact_ids)
@click.option("--json", "-j", "as_json", is_flag=True)
def delete(fact_ref: str, as_json: bool) -> None:
    """Permanently remove an already-retracted fact and its event history."""
    ref = parse_fact_ref(fact_ref)
    with corvee_context(scope=ref.scope) as ctx:
        fact = delete_fact(ctx.conn, ref.id, scope=ref.scope)
    emit_facts([fact.to_dict()], as_json=as_json)
