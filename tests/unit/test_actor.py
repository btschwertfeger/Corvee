#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import pytest

from corvee.actor import resolve_actor, resolve_session_id


class TestResolveActor:
    def test_uses_corvee_actor_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CORVEE_ACTOR, when set, is returned verbatim as the stable actor identity."""
        monkeypatch.setenv("CORVEE_ACTOR", "agent:claude")
        assert resolve_actor() == "agent:claude"

    def test_falls_back_to_human_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With CORVEE_ACTOR unset, the actor defaults to human:$USER."""
        monkeypatch.delenv("CORVEE_ACTOR", raising=False)
        monkeypatch.setenv("USER", "btschwertfeger")
        assert resolve_actor() == "human:btschwertfeger"

    def test_override_wins_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A passed-in override (the --actor flag) wins over CORVEE_ACTOR."""
        monkeypatch.setenv("CORVEE_ACTOR", "agent:claude")
        assert resolve_actor("agent:codex") == "agent:codex"

    def test_empty_override_falls_through_to_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty --actor value (unset flag) does not shadow CORVEE_ACTOR."""
        monkeypatch.setenv("CORVEE_ACTOR", "agent:claude")
        assert resolve_actor(None) == "agent:claude"


class TestResolveSessionId:
    def test_defaults_to_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CORVEE_SESSION_ID is optional; unset resolves to None, not an empty string."""
        monkeypatch.delenv("CORVEE_SESSION_ID", raising=False)
        assert resolve_session_id() is None

    def test_returns_set_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CORVEE_SESSION_ID, when set, is returned verbatim as the per-session token."""
        monkeypatch.setenv("CORVEE_SESSION_ID", "claude-session-7")
        assert resolve_session_id() == "claude-session-7"

    def test_override_wins_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A passed-in override (the --session-id flag) wins over CORVEE_SESSION_ID."""
        monkeypatch.setenv("CORVEE_SESSION_ID", "claude-session-7")
        assert resolve_session_id("codex-session-1") == "codex-session-1"

    def test_empty_override_falls_through_to_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty --session-id value (unset flag) does not shadow CORVEE_SESSION_ID."""
        monkeypatch.setenv("CORVEE_SESSION_ID", "claude-session-7")
        assert resolve_session_id(None) == "claude-session-7"
