#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click

from corvee.cli.commands.mcp.serve import serve


@click.group(name="mcp")
def mcp_group() -> None:
    """Run corvee as an MCP server, for hosts that speak MCP natively but have
    no shell/exec tool (Claude Desktop, several IDE-integrated assistants).

    A second, additive interface alongside the CLI, not a replacement for
    it -- a harness that already shells out to `corvee ...` keeps doing so.
    """


mcp_group.add_command(serve)
