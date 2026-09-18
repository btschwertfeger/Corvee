#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

"""`ServerConfig`, split out of `server.py` so `scope.py`/`tools_*.py` can
import it without an edge back into `server.py` -- this module has no
dependents of its own, so there is nothing left to cycle with.
"""

from dataclasses import dataclass

from corvee.config import ProjectConfig


@dataclass(frozen=True)
class ServerConfig:
    """Resolved once at server launch, on the main thread, and threaded
    explicitly into every tool call from then on -- never re-derived from
    click's (thread-local) context or the process's cwd once a tool call's
    DB work moves to the dedicated worker thread (spec §10.1).

    `project` is `None` in global-only mode: no `--project-root` was given,
    so local scope is unavailable for the server's whole lifetime.

    `session_id` is the server's own default, used by any write tool call
    that omits its own per-call `session_id` argument (§10.1) -- never
    silently unset, unlike the CLI's own `session_id: str | None = None`.
    """

    actor: str
    project: ProjectConfig | None
    session_id: str
