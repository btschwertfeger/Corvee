#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import tomllib

import pytest

from corvee.config import _toml_basic_string


class TestTomlBasicString:
    @pytest.mark.parametrize(
        "value",
        [
            "plain.db",
            'quote"inside.db',
            "back\\slash.db",
            "new\nline.db",
            "tab\there.db",
            "del\x7fhere.db",
            "ünïcode.db",
        ],
    )
    def test_every_value_is_written_as_valid_toml_and_reads_back_verbatim(self, value: str) -> None:
        """Escaping is asserted on the serialization, not through a file on disk.

        A value like `quote"inside.db` cannot be a filename on every platform
        the CI matrix runs on, so the round-trip stops at the config text.
        """
        written = f"db_path = {_toml_basic_string(value)}\n"

        assert tomllib.loads(written)["db_path"] == value
