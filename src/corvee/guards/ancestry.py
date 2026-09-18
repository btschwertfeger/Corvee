#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from collections.abc import Callable, Iterable

Adjacency = Callable[[int], Iterable[int] | None]


def is_reachable(adjacency: Adjacency, start: int, target: int) -> bool:
    """Whether `target` is reachable from `start` by following `adjacency` edges.

    Iterative DFS with a `visited` set, so a cycle already present in the
    graph terminates the walk instead of hanging it.
    """
    visited: set[int] = set()
    stack = [start]
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node in visited:
            continue
        visited.add(node)
        stack.extend(adjacency(node) or ())
    return False


def creates_cycle(adjacency: Adjacency, new_source: int, new_target: int) -> bool:
    """Whether adding edge `new_source -> new_target` would close a cycle.

    True iff `new_target` can already reach `new_source` via existing edges —
    adding the new edge would then complete a loop back to its own source.
    Reused for both `parent_of` and `blocks` link insertion.
    """
    return is_reachable(adjacency, new_target, new_source)
