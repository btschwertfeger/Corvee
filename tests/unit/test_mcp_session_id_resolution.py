#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import uuid

import pytest

from corvee.mcp.server import resolve_server_session_id


class TestResolveServerSessionId:
    def test_explicit_value_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CORVEE_SESSION_ID", "env-session")
        assert resolve_server_session_id("explicit-session") == "explicit-session"

    def test_falls_back_to_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CORVEE_SESSION_ID", "env-session")
        assert resolve_server_session_id(None) == "env-session"

    def test_falls_back_to_a_generated_uuid_when_nothing_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No --session-id, no $CORVEE_SESSION_ID: the server still needs a
        stable per-process id (spec §10.1's one-process-per-conversation
        model), so it mints one itself rather than leaving every write
        without any session id at all.
        """
        monkeypatch.delenv("CORVEE_SESSION_ID", raising=False)
        generated = resolve_server_session_id(None)
        assert uuid.UUID(generated)

    def test_generated_ids_are_not_repeated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CORVEE_SESSION_ID", raising=False)
        assert resolve_server_session_id(None) != resolve_server_session_id(None)
