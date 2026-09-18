#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import re
from datetime import UTC, datetime, timedelta

from corvee.errors import UsageError

_DURATION_RE = re.compile(r"^(\d+)([smhdw])$")
_DURATION_UNITS: dict[str, str] = {
    "s": "seconds",
    "m": "minutes",
    "h": "hours",
    "d": "days",
    "w": "weeks",
}


def timestamp(dt: datetime | None = None) -> str:
    """Fixed-width UTC ISO-8601 timestamp with milliseconds, e.g. 2026-09-11T14:03:22.123Z.

    `datetime.isoformat()` emits microseconds and a `+00:00` offset, both of
    which break the fixed-width property that plain-text sorting relies on,
    so every timestamp in corvee goes through this helper instead.
    """
    moment = dt.astimezone(UTC) if dt is not None else datetime.now(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def parse_duration(text: str) -> timedelta:
    """Parse a duration like "4h" or "7d" into a timedelta.

    Accepts an integer followed by one of s(econds), m(inutes), h(ours),
    d(ays), w(eeks).
    """
    match = _DURATION_RE.fullmatch(text)
    if match is None:
        msg = f"invalid duration {text!r}: expected an integer followed by s, m, h, d, or w"
        raise UsageError("invalid_duration", msg)
    amount, unit = match.groups()
    return timedelta(**{_DURATION_UNITS[unit]: int(amount)})
