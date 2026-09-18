#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from collections.abc import Iterable

from corvee.constants import LIST_FIELDS
from corvee.errors import UsageError


def validate_fields(
    requested: Iterable[str], *, allowed: Iterable[str] = LIST_FIELDS
) -> tuple[str, ...]:
    """Validate --fields values against `allowed` (the task allow-list by default).

    Returns the requested fields as a tuple, preserving order, or raises
    UsageError naming the first unknown field and the valid list.
    """
    fields = tuple(requested)
    allowed_list = list(allowed)
    for field in fields:
        if field not in allowed_list:
            raise UsageError(
                "unknown_field",
                f"unknown field {field!r}; valid fields: {', '.join(allowed_list)}",
                field=field,
                valid_fields=allowed_list,
            )
    return fields
