#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from corvee.constants import TRANSITIONS, State
from corvee.errors import GuardViolationError


def validate_transition(current: State, target: State) -> None:
    """Raise GuardViolationError unless `current -> target` is permitted.

    Setting a task to the state it already holds is always a no-op success.
    """
    if current == target:
        return
    allowed = sorted(TRANSITIONS[current])
    if target not in TRANSITIONS[current]:
        raise GuardViolationError(
            "invalid_transition",
            f"cannot transition from {current!r} to {target!r}; "
            f"from {current!r} may move to: {', '.join(allowed) or 'nothing (terminal)'}",
            current_state=current,
            target_state=target,
            allowed_states=allowed,
        )
