#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import getpass
import os

import click


def _flag_value(name: str) -> str | None:
    """The global --actor/--session-id value from the running CLI invocation,
    if any. None outside a click context (e.g. calling these functions
    directly in a test) or when the flag was not passed.
    """
    ctx = click.get_current_context(silent=True)
    if ctx is None:
        return None
    return ctx.find_root().params.get(name)


def resolve_actor(override: str | None = None) -> str:
    """--actor if given (explicitly, or via the running CLI's --actor flag),
    else CORVEE_ACTOR if set, else human:$USER.
    """
    actor = override or _flag_value("actor") or os.environ.get("CORVEE_ACTOR")
    if actor:
        return actor
    user = os.environ.get("USER") or getpass.getuser()
    return f"human:{user}"


def resolve_session_id(override: str | None = None) -> str | None:
    """--session-id if given (explicitly, or via the running CLI's
    --session-id flag), else CORVEE_SESSION_ID if set and non-empty, else
    None.
    """
    return override or _flag_value("session_id") or os.environ.get("CORVEE_SESSION_ID") or None
