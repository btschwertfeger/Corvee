#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.completion import complete_fact_ids
from corvee.cli.context import corvee_context
from corvee.cli.params import StdinOrValue
from corvee.db.facts import verify_fact
from corvee.models import parse_fact_ref
from corvee.output import emit_facts

EPILOG = """\
\b
Examples:
Verify a claim with a reproducible command as proof:
  corvee fact verify FACT-7 --proof \\
    "pip download requests --no-deps -d /tmp && unzip -q /tmp/requests-*.whl -d /tmp/requests-whl \\
    && grep -i '^License:' /tmp/requests-whl/*/METADATA"
Verify against a computed result, and get the result as JSON:
  corvee fact verify 7 --proof "grep -c '^def ' src/widgets.py  # -> 42" --json
Read long or multi-line proof from stdin instead of an argument:
  corvee fact verify 7 --proof - --json <<< "multi-line proof text"
"""


@click.command(epilog=EPILOG)
@click.argument("fact_ref", shell_complete=complete_fact_ids)
@click.option("--proof", "-p", type=StdinOrValue(), required=True)
@click.option("--json", "-j", "as_json", is_flag=True)
def verify(fact_ref: str, proof: str, as_json: bool) -> None:
    """Mark a fact verified, recording proof and a timestamp."""
    ref = parse_fact_ref(fact_ref)
    with corvee_context(scope=ref.scope) as ctx:
        fact = verify_fact(
            ctx.conn, ref.id, proof, ctx.actor, session_id=ctx.session_id, scope=ref.scope
        )
    emit_facts([fact.to_dict()], as_json=as_json)
