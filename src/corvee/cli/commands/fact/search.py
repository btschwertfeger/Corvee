#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.params import output_option
from corvee.cli.scope import fetch_merged, sort_facts
from corvee.constants import (
    FACT_LIST_FIELDS,
    SCOPE_FILTERS,
    narrow_output_format,
    narrow_scope_filter,
)
from corvee.db.facts import search_facts
from corvee.guards.fields import validate_fields
from corvee.output import emit_facts

EPILOG = """\
\b
Examples:
Check whether a fact for this already exists:
  corvee fact search "license" -o json
Include retracted facts in the search:
  corvee fact search "page number" --all -o json
Cap the result and trim it to a couple of fields:
  corvee fact search "MIT" --limit 5 --fields id,claim -o json
Check what a specific actor has verified matching this text:
  corvee fact search "license" --verified-by agent:claude -o json
Also match text buried in the proof, not just the claim:
  corvee fact search "PR #123" --include-proof -o json
"""


@click.command(epilog=EPILOG)
@click.argument("text")
@click.option("--all", "-a", "include_all", is_flag=True)
@click.option(
    "--include-proof",
    "-i",
    is_flag=True,
    help="Also match proof text, not just the claim.",
)
@click.option("--verified-by", "-v", "verified_by")
@click.option("--scope", "-s", "scope_filter", type=click.Choice(SCOPE_FILTERS), default="all")
@click.option("--limit", "-n", type=click.IntRange(min=1))
@click.option("--fields", "-f", "fields_csv")
@output_option(wide=True)
def search(
    text: str,
    include_all: bool,
    include_proof: bool,
    verified_by: str | None,
    scope_filter: str,
    limit: int | None,
    fields_csv: str | None,
    output_format: str,
) -> None:
    """Facts whose claim contains <text>, case-insensitive."""
    fields = (
        validate_fields(fields_csv.split(","), allowed=FACT_LIST_FIELDS) if fields_csv else None
    )
    # --limit applies after the merge, never per scope.
    facts = sort_facts(
        fetch_merged(
            narrow_scope_filter(scope_filter),
            lambda conn, s: search_facts(
                conn,
                text,
                include_all=include_all,
                include_proof=include_proof,
                verified_by=verified_by,
                scope=s,
            ),
        )
    )
    if limit is not None:
        facts = facts[:limit]
    emit_facts(
        [f.to_dict() for f in facts], output=narrow_output_format(output_format), fields=fields
    )
