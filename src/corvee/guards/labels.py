#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from corvee.constants import LABEL_PATTERN
from corvee.errors import UsageError


def normalize_label(raw: str) -> str:
    """Lowercase, trim, and validate a label name against LABEL_PATTERN.

    Raises UsageError with the pattern in the message when invalid.
    """
    name = raw.strip().lower()
    if not LABEL_PATTERN.fullmatch(name):
        raise UsageError(
            "invalid_label",
            f"invalid label {raw!r}: must match [a-z0-9][a-z0-9._/-]{{0,49}}",
            label=raw,
        )
    return name
