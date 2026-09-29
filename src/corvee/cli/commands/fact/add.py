#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.context import corvee_context
from corvee.cli.params import StdinOrValue, output_option
from corvee.constants import narrow_output_format
from corvee.db.facts import insert_fact
from corvee.errors import UsageError
from corvee.output import emit_facts

EPILOG = """\
\b
Examples:
Record an unverified claim, to check later:
  corvee fact add "requests is Apache-2.0 licensed"
Record it already verified, with reproducible proof:
  corvee fact add "requests is Apache-2.0 licensed" -o json --proof \\
    "pip download requests --no-deps -d /tmp && unzip -q /tmp/requests-*.whl -d /tmp/requests-whl \\
    && grep -i '^License:' /tmp/requests-whl/*/METADATA"
Read a long or multi-line claim from stdin instead of an argument:
  corvee fact add - -o json <<< "multi-line claim text from stdin"
File a fact that isn't specific to this project:
  corvee fact add "the CA cert bundle rotates every January" --global -o json
"""


@click.command(epilog=EPILOG)
@click.argument("claim", type=StdinOrValue())
@click.option("--proof", "-p", type=StdinOrValue(), default=None)
@click.option(
    "--global",
    "-g",
    "is_global",
    is_flag=True,
    help="File into the shared, machine-wide database instead of this project's.",
)
@output_option()
def add(claim: str, proof: str | None, is_global: bool, output_format: str) -> None:
    """Create a fact. Providing --proof verifies it immediately."""
    if not claim.strip():
        raise UsageError(
            "invalid_claim",
            "claim must not be empty or whitespace-only",
        )
    scope = "global" if is_global else "local"
    with corvee_context(scope=scope) as ctx:
        fact = insert_fact(
            ctx.conn,
            claim=claim,
            actor=ctx.actor,
            session_id=ctx.session_id,
            proof=proof,
            scope=scope,
        )
    emit_facts([fact.to_dict()], output=narrow_output_format(output_format))
