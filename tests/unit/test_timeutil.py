#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import re
from datetime import UTC, datetime, timedelta

import pytest

from corvee.errors import UsageError
from corvee.timeutil import parse_duration, timestamp

TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


class TestTimestamp:
    def test_is_fixed_width_utc_iso8601_with_milliseconds(self) -> None:
        """A generated timestamp matches the fixed-width UTC ISO-8601-with-milliseconds format."""
        assert TIMESTAMP_RE.match(timestamp())

    def test_fixed_width_sorts_the_same_as_chronological_order(self) -> None:
        """Fixed-width formatting means plain text sort order matches chronological order."""
        earlier = datetime(2026, 1, 1, 0, 0, 0, 0, tzinfo=UTC)
        later = earlier + timedelta(milliseconds=1)
        earlier_str = timestamp(earlier)
        later_str = timestamp(later)
        assert len(earlier_str) == len(later_str)
        assert sorted([later_str, earlier_str]) == [earlier_str, later_str]

    def test_of_given_datetime_round_trips(self) -> None:
        """A specific datetime formats to the exact expected timestamp string."""
        dt = datetime(2026, 9, 11, 14, 3, 22, 123_000, tzinfo=UTC)
        assert timestamp(dt) == "2026-09-11T14:03:22.123Z"


class TestParseDuration:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("4h", timedelta(hours=4)),
            ("7d", timedelta(days=7)),
            ("30m", timedelta(minutes=30)),
            ("2w", timedelta(weeks=2)),
            ("90s", timedelta(seconds=90)),
        ],
    )
    def test_accepts_documented_units(self, text: str, expected: timedelta) -> None:
        """Every documented unit suffix (s/m/h/d/w) parses to the correct timedelta."""
        assert parse_duration(text) == expected

    @pytest.mark.parametrize("text", ["", "4", "h4", "4x", "-4h", "4.5h"])
    def test_rejects_invalid_input(self, text: str) -> None:
        """Malformed duration input (no unit, bad unit, negative, fractional) raises a
        UsageError, so a mistyped duration maps to exit 2, not exit 1 internal_error.
        """
        with pytest.raises(UsageError, match="duration"):
            parse_duration(text)

    def test_rejects_a_digit_run_too_large_for_timedelta(self) -> None:
        """A syntactically valid but absurdly large digit run (TASK-30) raises
        UsageError (exit 2) instead of the bare OverflowError timedelta() itself
        raises when the value can't convert to a C int.
        """
        with pytest.raises(UsageError, match="duration"):
            parse_duration("99999999999999999999d")
