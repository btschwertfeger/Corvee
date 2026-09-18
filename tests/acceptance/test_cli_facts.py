#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
import sqlite3
from collections.abc import Callable

import pytest
from click.testing import CliRunner

from corvee.cli.main import cli
from corvee.config import ProjectConfig


class TestFactAdd:
    def test_creates_unverified_fact(self, runner: CliRunner, project: ProjectConfig) -> None:
        """`fact add` with no --proof creates an unverified fact with the FACT-1 id."""
        result = runner.invoke(cli, ["fact", "add", "package X is MIT-licensed", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["id"] == "FACT-1"
        assert payload[0]["claim"] == "package X is MIT-licensed"
        assert payload[0]["status"] == "unverified"

    def test_with_proof_verifies_immediately(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """`fact add --proof` creates the fact already verified, with that proof recorded."""
        result = runner.invoke(cli, ["fact", "add", "claim", "--proof", "see LICENSE", "--json"])
        payload = json.loads(result.output)
        assert payload[0]["status"] == "verified"
        assert payload[0]["proof"] == "see LICENSE"

    def test_reads_claim_from_stdin(self, runner: CliRunner, project: ProjectConfig) -> None:
        """A "-" claim argument reads the claim text from stdin instead of argv."""
        result = runner.invoke(cli, ["fact", "add", "-", "--json"], input="From stdin")
        payload = json.loads(result.output)
        assert payload[0]["claim"] == "From stdin"

    def test_rejects_whitespace_only_claim(self, runner: CliRunner, project: ProjectConfig) -> None:
        """A fact's claim is its entire content; whitespace-only is as meaningless as empty."""
        result = runner.invoke(cli, ["fact", "add", "   ", "--json"])
        assert result.exit_code == 2

    def test_rejects_empty_claim(self, runner: CliRunner, project: ProjectConfig) -> None:
        """An empty claim exits 2 the same as a whitespace-only one."""
        result = runner.invoke(cli, ["fact", "add", "", "--json"])
        assert result.exit_code == 2


class TestFactRevise:
    def test_identical_text_is_a_no_op(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """Revising a fact to its own current claim text writes no new event."""
        fact_id = add_fact("claim text")
        result = runner.invoke(cli, ["fact", "revise", fact_id, "claim text", "--json"])
        assert result.exit_code == 0
        show_result = runner.invoke(cli, ["fact", "show", fact_id, "--json"])
        assert len(json.loads(show_result.output)[0]["events"]) == 1

    def test_different_text_updates_claim(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """Revising a fact to genuinely different text updates its claim."""
        fact_id = add_fact("old claim")
        result = runner.invoke(cli, ["fact", "revise", fact_id, "new claim", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["claim"] == "new claim"


class TestFactVerify:
    def test_sets_status_verified(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """`fact verify --proof` marks the fact verified and stamps the current actor."""
        fact_id = add_fact("claim")
        result = runner.invoke(
            cli, ["fact", "verify", fact_id, "--proof", "see file.py:12", "--json"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["status"] == "verified"
        assert payload[0]["verified_by"] == "agent:test"

    def test_requires_proof(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """`fact verify` without --proof exits 2; proof is mandatory for a verification."""
        fact_id = add_fact("claim")
        result = runner.invoke(cli, ["fact", "verify", fact_id, "--json"])
        assert result.exit_code == 2


class TestFactUnverify:
    def test_clears_verified_state(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """`fact unverify` resets status to unverified and clears the recorded proof."""
        fact_id = add_fact("claim")
        runner.invoke(cli, ["fact", "verify", fact_id, "--proof", "proof"])
        result = runner.invoke(cli, ["fact", "unverify", fact_id, "--json"])
        payload = json.loads(result.output)
        assert payload[0]["status"] == "unverified"
        assert payload[0]["proof"] is None


class TestFactRetract:
    def test_excludes_from_default_list(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """A retracted fact drops out of the default `fact list` but stays visible with --all."""
        fact_id = add_fact("claim")
        runner.invoke(cli, ["fact", "retract", fact_id, "--reason", "added by mistake"])

        result = runner.invoke(cli, ["fact", "list", "--json"])
        assert json.loads(result.output) == []

        all_result = runner.invoke(cli, ["fact", "list", "--all", "--json"])
        assert len(json.loads(all_result.output)) == 1

    def test_retracted_fact_can_be_reverified(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """Retract is not a dead end: verify still works on a retracted fact and moves it back."""
        fact_id = add_fact("claim")
        runner.invoke(cli, ["fact", "retract", fact_id])
        result = runner.invoke(cli, ["fact", "verify", fact_id, "--proof", "proof", "--json"])
        assert json.loads(result.output)[0]["status"] == "verified"

    def test_retracted_fact_can_be_revised_back_into_the_default_list(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """
        Revising a retracted fact also moves it back, showing up in the default
        `fact list` again.
        """
        fact_id = add_fact("claim")
        runner.invoke(cli, ["fact", "retract", fact_id])
        runner.invoke(cli, ["fact", "revise", fact_id, "revised claim"])

        result = runner.invoke(cli, ["fact", "list", "--json"])
        payload = json.loads(result.output)
        assert [f["id"] for f in payload] == [fact_id]
        assert payload[0]["status"] == "unverified"


class TestFactDelete:
    def test_rejects_a_fact_that_is_not_retracted(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """`fact delete` on a non-retracted fact exits 5 with fact_not_retracted."""
        fact_id = add_fact("claim")
        result = runner.invoke(cli, ["fact", "delete", fact_id, "--json"])
        assert result.exit_code == 5
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "fact_not_retracted"

    def test_removes_a_retracted_fact_permanently(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """`fact delete` on a retracted fact removes it; a later `fact show` exits 3."""
        fact_id = add_fact("claim")
        runner.invoke(cli, ["fact", "retract", fact_id])
        result = runner.invoke(cli, ["fact", "delete", fact_id, "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output)[0]["id"] == fact_id

        show_result = runner.invoke(cli, ["fact", "show", fact_id, "--json"])
        assert show_result.exit_code == 3


class TestFactList:
    def test_default_includes_unverified(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """Unlike tasks, an unverified fact stays in the default `fact list` output."""
        add_fact("claim")
        result = runner.invoke(cli, ["fact", "list", "--json"])
        assert len(json.loads(result.output)) == 1

    def test_filters_by_status(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """--status narrows the listing to facts holding exactly that status."""
        verified_id = add_fact("verified claim")
        runner.invoke(cli, ["fact", "verify", verified_id, "--proof", "proof"])
        add_fact("unverified claim")

        result = runner.invoke(cli, ["fact", "list", "--status", "verified", "--json"])
        payload = json.loads(result.output)
        assert [f["id"] for f in payload] == [verified_id]

    def test_fields_projection(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """--fields projects fact objects down to exactly the requested keys."""
        add_fact("claim one")
        result = runner.invoke(cli, ["fact", "list", "--json", "--fields", "id,claim"])
        payload = json.loads(result.output)
        assert payload == [{"id": "FACT-1", "claim": "claim one"}]

    def test_rejects_unknown_field(self, runner: CliRunner, project: ProjectConfig) -> None:
        """An unrecognized --fields column on `fact list` exits 2 as unknown_field."""
        result = runner.invoke(cli, ["fact", "list", "--json", "--fields", "bogus"])
        assert result.exit_code == 2
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "unknown_field"

    def test_since_filters_out_facts_updated_before_the_cutoff(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        conn: sqlite3.Connection,
        add_fact: Callable[[str], str],
    ) -> None:
        """--since drops facts whose updated_at predates the duration cutoff."""
        old_id = add_fact("old claim")
        recent_id = add_fact("recent claim")
        conn.execute(
            "UPDATE facts SET updated_at = '2020-01-01T00:00:00.000Z' WHERE id = ?",
            (int(old_id.removeprefix("FACT-")),),
        )
        conn.commit()

        result = runner.invoke(cli, ["fact", "list", "--since", "7d", "--json"])
        assert [f["id"] for f in json.loads(result.output)] == [recent_id]

    def test_verified_by_filters_to_one_actor(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        monkeypatch: pytest.MonkeyPatch,
        add_fact: Callable[[str], str],
    ) -> None:
        """--verified-by narrows the listing to facts that actor verified."""
        mine_id = add_fact("mine")
        runner.invoke(cli, ["fact", "verify", mine_id, "--proof", "proof"])
        theirs_id = add_fact("theirs")
        monkeypatch.setenv("CORVEE_ACTOR", "agent:other")
        runner.invoke(cli, ["fact", "verify", theirs_id, "--proof", "proof"])

        result = runner.invoke(cli, ["fact", "list", "--verified-by", "agent:test", "--json"])
        assert [f["id"] for f in json.loads(result.output)] == [mine_id]

    def test_stale_filters_to_verified_facts_past_the_cutoff(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        conn: sqlite3.Connection,
        add_fact: Callable[[str], str],
    ) -> None:
        """--stale keeps verified facts whose verified_at predates the duration cutoff."""
        stale_id = add_fact("stale")
        runner.invoke(cli, ["fact", "verify", stale_id, "--proof", "proof"])
        fresh_id = add_fact("fresh")
        runner.invoke(cli, ["fact", "verify", fresh_id, "--proof", "proof"])
        conn.execute(
            "UPDATE facts SET verified_at = '2020-01-01T00:00:00.000Z' WHERE id = ?",
            (int(stale_id.removeprefix("FACT-")),),
        )
        conn.commit()

        result = runner.invoke(cli, ["fact", "list", "--stale", "7d", "--json"])
        assert [f["id"] for f in json.loads(result.output)] == [stale_id]

    def test_ls_is_an_alias_for_list(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """`fact ls` behaves exactly like `fact list`, flags included."""
        add_fact("claim one")
        result = runner.invoke(cli, ["fact", "ls", "--json", "--fields", "id,claim"])
        assert result.exit_code == 0
        assert json.loads(result.output) == [{"id": "FACT-1", "claim": "claim one"}]


class TestFactSearch:
    def test_finds_claim_substring(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """`fact search` matches a case-insensitive substring of the claim text."""
        add_fact("package X is MIT-licensed")
        add_fact("unrelated claim")
        result = runner.invoke(cli, ["fact", "search", "MIT", "--json"])
        assert len(json.loads(result.output)) == 1

    def test_verified_by_filters_to_one_actor(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        monkeypatch: pytest.MonkeyPatch,
        add_fact: Callable[[str], str],
    ) -> None:
        """--verified-by narrows a search to facts that actor verified."""
        mine_id = add_fact("license mine")
        runner.invoke(cli, ["fact", "verify", mine_id, "--proof", "proof"])
        theirs_id = add_fact("license theirs")
        monkeypatch.setenv("CORVEE_ACTOR", "agent:other")
        runner.invoke(cli, ["fact", "verify", theirs_id, "--proof", "proof"])

        result = runner.invoke(
            cli, ["fact", "search", "license", "--verified-by", "agent:test", "--json"]
        )
        assert [f["id"] for f in json.loads(result.output)] == [mine_id]

    def test_include_proof_matches_proof_text(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """--include-proof extends the match to proof text."""
        fact_id = add_fact("claim")
        runner.invoke(cli, ["fact", "verify", fact_id, "--proof", "see PR #123"])

        assert json.loads(runner.invoke(cli, ["fact", "search", "PR #123", "--json"]).output) == []

        result = runner.invoke(cli, ["fact", "search", "PR #123", "--include-proof", "--json"])
        assert [f["id"] for f in json.loads(result.output)] == [fact_id]


class TestFactShow:
    def test_returns_full_detail_shape(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """`fact show` includes the full revision timeline under "events"."""
        fact_id = add_fact("claim")
        result = runner.invoke(cli, ["fact", "show", fact_id, "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert len(payload[0]["events"]) == 1
        assert payload[0]["events"][0]["kind"] == "created"

    def test_missing_fact_exits_three(self, runner: CliRunner, project: ProjectConfig) -> None:
        """Showing a nonexistent fact id exits 3 with the fact_not_found error code."""
        result = runner.invoke(cli, ["fact", "show", "999", "--json"])
        assert result.exit_code == 3
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "fact_not_found"

    def test_preserves_given_id_order(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """Multiple ids to `fact show` come back in the order they were given."""
        add_fact("a")
        add_fact("b")
        result = runner.invoke(cli, ["fact", "show", "2", "1", "--json"])
        payload = json.loads(result.output)
        assert [f["id"] for f in payload] == ["FACT-2", "FACT-1"]

    def test_plain_output_includes_revision_history(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        add_fact: Callable[[str], str],
    ) -> None:
        """Without --json, `fact show` still surfaces the revision/verification
        history -- specifically an unverify note, which lives only in
        fact_events, not on the denormalized fact row.
        """
        fact_id = add_fact("claim")
        runner.invoke(cli, ["fact", "verify", fact_id, "--proof", "grep -c foo bar.py"])
        runner.invoke(cli, ["fact", "unverify", fact_id, "--note", "proof link is now dead"])
        result = runner.invoke(cli, ["fact", "show", fact_id])
        assert result.exit_code == 0
        assert "proof link is now dead" in result.output


class TestCrossNamespaceIds:
    def test_fact_command_rejects_a_task_id(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """A `fact` command given a TASK-<n> value is rejected rather than silently misread."""
        runner.invoke(cli, ["task", "add", "a task", "--description", "d", "--json"])
        result = runner.invoke(cli, ["fact", "show", "TASK-1", "--json"])
        assert result.exit_code == 2
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "wrong_id_namespace"

    def test_task_command_rejects_a_fact_id(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """A `task` command given a FACT-<n> value is rejected rather than silently misread."""
        add_fact("a fact")
        result = runner.invoke(cli, ["task", "show", "FACT-1", "--json"])
        assert result.exit_code == 2
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "wrong_id_namespace"
