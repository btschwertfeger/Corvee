#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from collections.abc import Iterable

from corvee.constants import TERMINAL_STATES, Scope, State
from corvee.errors import GuardViolationError
from corvee.models import task_ref


def assert_no_open_children(
    children: Iterable[tuple[int, State]], *, scope: Scope = "local"
) -> None:
    """Raise GuardViolationError if any child is not done/cancelled.

    `children` is (task_id, state) pairs for a task's direct `parent_of`
    children. Used to guard both `done` and `cancelled` (without --cascade)
    transitions on a parent.
    """
    blocking_ids = [
        task_ref(task_id, scope) for task_id, state in children if state not in TERMINAL_STATES
    ]
    if blocking_ids:
        raise GuardViolationError(
            "open_children",
            f"cannot close this task while children are still open: {blocking_ids}",
            blocking_ids=blocking_ids,
        )
