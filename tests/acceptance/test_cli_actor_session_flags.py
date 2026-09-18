#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
from collections.abc import Callable

import pytest
from click.testing import CliRunner

from corvee.cli.main import cli
from corvee.config import ProjectConfig


class TestGlobalActorSessionFlags:
    def test_actor_flag_stamps_events_without_any_env_var(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--actor identifies the caller even with $CORVEE_ACTOR unset entirely,
        the scenario a permission-gated harness needs: a bare "corvee ..."
        command line with no env var assignment prefixing it.
        """
        monkeypatch.delenv("CORVEE_ACTOR", raising=False)
        result = runner.invoke(
            cli,
            ["--actor", "agent:codex", "task", "add", "t", "--description", "d", "--json"],
        )
        task_id = json.loads(result.output)[0]["id"]
        claimed = runner.invoke(cli, ["--actor", "agent:codex", "task", "claim", task_id, "--json"])
        assert json.loads(claimed.output)[0]["claimed_by"] == "agent:codex"

    def test_session_id_flag_stamps_events_without_any_env_var(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        monkeypatch: pytest.MonkeyPatch,
        add_task: Callable[[str], str],
    ) -> None:
        """--session-id is recorded on task_events the same way $CORVEE_SESSION_ID is."""
        monkeypatch.delenv("CORVEE_SESSION_ID", raising=False)
        task_id = add_task("t")
        runner.invoke(cli, ["--session-id", "sess-1", "task", "comment", task_id, "a note"])
        show = runner.invoke(cli, ["task", "show", task_id, "--json"])
        events = json.loads(show.output)[0]["events"]
        assert events[-1]["session_id"] == "sess-1"

    def test_actor_flag_overrides_corvee_actor_env_var(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        add_task: Callable[[str], str],
    ) -> None:
        """--actor wins over $CORVEE_ACTOR when both are present."""
        task_id = add_task("t")
        result = runner.invoke(cli, ["--actor", "agent:flag", "task", "claim", task_id, "--json"])
        assert json.loads(result.output)[0]["claimed_by"] == "agent:flag"

    def test_task_mine_honors_the_actor_flag(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        monkeypatch: pytest.MonkeyPatch,
        add_task: Callable[[str], str],
    ) -> None:
        """A command that resolves the actor outside corvee_context (task mine)
        still picks up --actor, not just commands going through corvee_context.
        """
        monkeypatch.delenv("CORVEE_ACTOR", raising=False)
        task_id = add_task("t")
        runner.invoke(cli, ["--actor", "agent:codex", "task", "claim", task_id])
        result = runner.invoke(cli, ["--actor", "agent:codex", "task", "mine", "--json"])
        assert [t["id"] for t in json.loads(result.output)] == [task_id]

    def test_without_flag_or_env_var_falls_back_to_human_user(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        monkeypatch: pytest.MonkeyPatch,
        add_task: Callable[[str], str],
    ) -> None:
        """Neither flag nor $CORVEE_ACTOR set still resolves to human:$USER, unchanged."""
        monkeypatch.delenv("CORVEE_ACTOR", raising=False)
        monkeypatch.setenv("USER", "btschwertfeger")
        task_id = add_task("t")
        result = runner.invoke(cli, ["task", "claim", task_id, "--json"])
        assert json.loads(result.output)[0]["claimed_by"] == "human:btschwertfeger"
