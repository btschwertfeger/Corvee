#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3

from corvee.db.labels import add_label, list_labels_with_counts, list_task_labels, remove_label
from corvee.db.tasks import insert_task


class TestAddLabel:
    def test_attaches_it(self, conn: sqlite3.Connection) -> None:
        """Adding a label attaches it to the task."""
        task = insert_task(conn, title="t")
        add_label(conn, task.id, "api", "agent:a", None)
        assert list_task_labels(conn, task.id) == ["api"]

    def test_twice_is_a_no_op(self, conn: sqlite3.Connection) -> None:
        """Adding a label the task already has is a success, not a duplicate row."""
        task = insert_task(conn, title="t")
        add_label(conn, task.id, "api", "agent:a", None)
        add_label(conn, task.id, "api", "agent:a", None)
        assert list_task_labels(conn, task.id) == ["api"]


class TestRemoveLabel:
    def test_detaches_it(self, conn: sqlite3.Connection) -> None:
        """Removing an attached label detaches it from the task."""
        task = insert_task(conn, title="t")
        add_label(conn, task.id, "api", "agent:a", None)
        remove_label(conn, task.id, "api", "agent:a", None)
        assert list_task_labels(conn, task.id) == []

    def test_not_present_is_a_no_op(self, conn: sqlite3.Connection) -> None:
        """Removing a label the task never had succeeds without error."""
        task = insert_task(conn, title="t")
        remove_label(conn, task.id, "nonexistent", "agent:a", None)
        assert list_task_labels(conn, task.id) == []


class TestListLabelsWithCounts:
    def test_counts_tasks_per_label(self, conn: sqlite3.Connection) -> None:
        """Every label in the project is listed once with the count of tasks carrying it."""
        a = insert_task(conn, title="a")
        b = insert_task(conn, title="b")
        add_label(conn, a.id, "api", "agent:a", None)
        add_label(conn, b.id, "api", "agent:a", None)
        add_label(conn, a.id, "urgent", "agent:a", None)

        counts = dict(list_labels_with_counts(conn))
        assert counts == {"api": 2, "urgent": 1}
