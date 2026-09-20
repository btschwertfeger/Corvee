#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from pathlib import Path

import pytest

from corvee.db.connection import unusable_database_error

DB_PATH = Path("/project/.corvee/corvee.db")


def _error(code: int | None) -> sqlite3.Error:
    """A sqlite3.Error carrying `code`, the way one raised by sqlite does.

    `sqlite_errorcode` is set by sqlite itself, never by the caller, so the
    translation's own input is built here: mapping a code to a reason is the
    whole subject of the function, and no real database can produce every code
    on demand.
    """
    error = sqlite3.OperationalError("boom")
    if code is not None:
        error.sqlite_errorcode = code
    return error


class TestUnusableDatabaseError:
    @pytest.mark.parametrize(
        "code",
        [
            sqlite3.SQLITE_CANTOPEN,
            sqlite3.SQLITE_NOTADB,
            sqlite3.SQLITE_READONLY,
            sqlite3.SQLITE_PERM,
            sqlite3.SQLITE_CORRUPT,
        ],
    )
    def test_a_file_that_cannot_be_used_becomes_exit_six(self, code: int) -> None:
        """Every code in the set turns into the ConfigError that names the file."""
        error = unusable_database_error(_error(code), DB_PATH)

        assert error is not None
        assert error.exit_code == 6
        assert error.code == "unusable_database"
        assert error.extra["path"] == str(DB_PATH)

    def test_an_extended_code_matches_through_its_primary_code(self) -> None:
        """SQLITE_READONLY_DBMOVED is an extended READONLY, matched by the low byte.

        A plain membership test on the extended code would quietly demote every
        such variant back to an internal error.
        """
        assert sqlite3.SQLITE_READONLY_DBMOVED & 0xFF == sqlite3.SQLITE_READONLY

        error = unusable_database_error(_error(sqlite3.SQLITE_READONLY_DBMOVED), DB_PATH)

        assert error is not None
        assert error.exit_code == 6

    @pytest.mark.parametrize(
        "code",
        [
            sqlite3.SQLITE_BUSY,
            sqlite3.SQLITE_BUSY_SNAPSHOT,
            sqlite3.SQLITE_ERROR,
            sqlite3.SQLITE_IOERR,
        ],
    )
    def test_every_other_failure_keeps_its_own_shape(self, code: int) -> None:
        """A lock timeout, a failing statement or a device error is not a config problem.

        Reporting those as exit 6 would send the caller off to inspect a file
        that is perfectly fine.
        """
        assert unusable_database_error(_error(code), DB_PATH) is None

    def test_an_error_without_a_code_is_left_alone(self) -> None:
        """Only sqlite sets `sqlite_errorcode`; an error lacking one has nothing to judge."""
        assert unusable_database_error(_error(None), DB_PATH) is None
