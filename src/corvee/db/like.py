#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#


def escape_like(text: str) -> str:
    """Escape %, _ and the escape character itself for a `LIKE ... ESCAPE '\\'` clause,
    so a search query containing them matches literally rather than as wildcards.
    """
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
