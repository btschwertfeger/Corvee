#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
from collections.abc import Callable

from click.testing import CliRunner

from corvee.cli.main import cli
from corvee.config import ProjectConfig, global_db_path


class TestTaskAddGlobal:
    def test_creates_a_task_with_the_global_id_prefix(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """`task add --global` files into the global database, TASK-GLOBAL-<n> id (§3.3)."""
        result = runner.invoke(
            cli, ["task", "add", "renew CA cert", "--description", "d", "--global", "--json"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)[0]
        assert payload["id"] == "TASK-GLOBAL-1"
        assert payload["scope"] == "global"

    def test_local_and_global_task_ids_start_independently_at_one(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """Each database's id sequence is its own — TASK-1 and TASK-GLOBAL-1 can coexist."""
        local_result = runner.invoke(cli, ["task", "add", "local", "--description", "d", "--json"])
        global_result = runner.invoke(
            cli, ["task", "add", "global", "--description", "d", "--global", "--json"]
        )
        assert json.loads(local_result.output)[0]["id"] == "TASK-1"
        assert json.loads(global_result.output)[0]["id"] == "TASK-GLOBAL-1"


class TestTaskGlobalLifecycle:
    def test_claim_show_update_comment_all_resolve_scope_from_the_id(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """A TASK-GLOBAL-<n> ref routes every id-based command to the global database."""
        add_result = runner.invoke(
            cli, ["task", "add", "renew CA cert", "--description", "d", "--global", "--json"]
        )
        task_id = json.loads(add_result.output)[0]["id"]

        claim_result = runner.invoke(cli, ["task", "claim", task_id, "--json"])
        assert claim_result.exit_code == 0
        assert json.loads(claim_result.output)[0]["claimed_by"] is not None

        update_result = runner.invoke(
            cli, ["task", "update", task_id, "--state", "in_progress", "--json"]
        )
        assert update_result.exit_code == 0
        assert json.loads(update_result.output)[0]["state"] == "in_progress"

        comment_result = runner.invoke(cli, ["task", "comment", task_id, "renewed", "--json"])
        assert comment_result.exit_code == 0

        show_result = runner.invoke(cli, ["task", "show", task_id, "--json"])
        assert show_result.exit_code == 0
        detail = json.loads(show_result.output)[0]
        assert detail["id"] == task_id
        assert detail["scope"] == "global"
        assert len(detail["events"]) >= 3

    def test_missing_global_task_is_a_clean_not_found(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """A TASK-GLOBAL-<n> id that doesn't exist exits 3, same as a missing local id."""
        result = runner.invoke(cli, ["task", "show", "TASK-GLOBAL-99", "--json"])
        assert result.exit_code == 3

    def test_show_on_missing_global_db_does_not_create_it(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """A read-only `task show TASK-GLOBAL-<n>` never materializes ~/.corvee/corvee.db (§3.3)."""
        assert not global_db_path().is_file()
        result = runner.invoke(cli, ["task", "show", "TASK-GLOBAL-5", "--json"])
        assert result.exit_code == 3
        assert not global_db_path().is_file()

    def test_fact_show_on_missing_global_db_does_not_create_it(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """Same guarantee for `fact show`."""
        assert not global_db_path().is_file()
        result = runner.invoke(cli, ["fact", "show", "FACT-GLOBAL-5", "--json"])
        assert result.exit_code == 3
        assert not global_db_path().is_file()


class TestTaskListMergesScope:
    def test_scope_all_is_the_default_and_merges_both(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """task list with no --scope shows local and global tasks together."""
        runner.invoke(cli, ["task", "add", "local one", "--description", "d", "--json"])
        runner.invoke(
            cli, ["task", "add", "global one", "--description", "d", "--global", "--json"]
        )

        result = runner.invoke(cli, ["task", "list", "--json"])
        assert result.exit_code == 0
        ids = {t["id"] for t in json.loads(result.output)}
        assert ids == {"TASK-1", "TASK-GLOBAL-1"}

    def test_scope_local_excludes_global(self, runner: CliRunner, project: ProjectConfig) -> None:
        """--scope local narrows the merge down to the project database only."""
        runner.invoke(cli, ["task", "add", "local one", "--description", "d", "--json"])
        runner.invoke(
            cli, ["task", "add", "global one", "--description", "d", "--global", "--json"]
        )

        result = runner.invoke(cli, ["task", "list", "--scope", "local", "--json"])
        ids = {t["id"] for t in json.loads(result.output)}
        assert ids == {"TASK-1"}

    def test_scope_global_on_a_project_that_never_used_global_is_empty(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """--scope global with no global rows ever filed returns [], not an error."""
        result = runner.invoke(cli, ["task", "list", "--scope", "global", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []


class TestTaskListRefFiltersRespectScope:
    def test_parent_filter_does_not_leak_into_the_other_scope(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """A --parent TASK-GLOBAL-<n> ref must never match a local task whose bare
        id happens to be the same number -- local and global ids are independent
        sequences (§3.3/§4.2), and cross-scope parent_of links are impossible.
        """
        # Local: id 1 is parent_of local id 2.
        runner.invoke(cli, ["task", "add", "local parent", "--description", "d", "--json"])
        runner.invoke(cli, ["task", "add", "local child", "--description", "d", "--json"])
        runner.invoke(cli, ["task", "link", "TASK-1", "TASK-2", "--relation", "parent_of"])

        # Global: id 1 is parent_of global id 2, an entirely unrelated pair.
        runner.invoke(
            cli, ["task", "add", "global parent", "--description", "d", "--global", "--json"]
        )
        runner.invoke(
            cli, ["task", "add", "global child", "--description", "d", "--global", "--json"]
        )
        runner.invoke(
            cli, ["task", "link", "TASK-GLOBAL-1", "TASK-GLOBAL-2", "--relation", "parent_of"]
        )

        result = runner.invoke(cli, ["task", "list", "--parent", "TASK-GLOBAL-1", "--json"])
        assert result.exit_code == 0
        ids = {t["id"] for t in json.loads(result.output)}
        assert ids == {"TASK-GLOBAL-2"}

    def test_parent_filter_local_ref_does_not_leak_into_global(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """The reverse direction: a local --parent ref must not match a global task."""
        runner.invoke(cli, ["task", "add", "local parent", "--description", "d", "--json"])
        runner.invoke(cli, ["task", "add", "local child", "--description", "d", "--json"])
        runner.invoke(cli, ["task", "link", "TASK-1", "TASK-2", "--relation", "parent_of"])

        runner.invoke(
            cli, ["task", "add", "global parent", "--description", "d", "--global", "--json"]
        )
        runner.invoke(
            cli, ["task", "add", "global child", "--description", "d", "--global", "--json"]
        )
        runner.invoke(
            cli, ["task", "link", "TASK-GLOBAL-1", "TASK-GLOBAL-2", "--relation", "parent_of"]
        )

        result = runner.invoke(cli, ["task", "list", "--parent", "TASK-1", "--json"])
        assert result.exit_code == 0
        ids = {t["id"] for t in json.loads(result.output)}
        assert ids == {"TASK-2"}


class TestFactGlobal:
    def test_add_global_and_merged_list(self, runner: CliRunner, project: ProjectConfig) -> None:
        """fact add --global files a FACT-GLOBAL-<n> fact that shows up in the merged list."""
        runner.invoke(cli, ["fact", "add", "local claim", "--json"])
        add_result = runner.invoke(cli, ["fact", "add", "global claim", "--global", "--json"])
        assert json.loads(add_result.output)[0]["id"] == "FACT-GLOBAL-1"

        list_result = runner.invoke(cli, ["fact", "list", "--json"])
        ids = {f["id"] for f in json.loads(list_result.output)}
        assert ids == {"FACT-1", "FACT-GLOBAL-1"}

    def test_verify_and_retract_resolve_scope_from_the_id(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """A FACT-GLOBAL-<n> ref routes verify/retract to the global database."""
        add_result = runner.invoke(cli, ["fact", "add", "global claim", "--global", "--json"])
        fact_id = json.loads(add_result.output)[0]["id"]

        verify_result = runner.invoke(cli, ["fact", "verify", fact_id, "--proof", "p", "--json"])
        assert verify_result.exit_code == 0
        assert json.loads(verify_result.output)[0]["status"] == "verified"

        retract_result = runner.invoke(cli, ["fact", "retract", fact_id, "--json"])
        assert retract_result.exit_code == 0
        assert json.loads(retract_result.output)[0]["status"] == "retracted"


class TestCrossScopeGuard:
    def test_link_across_scopes_is_a_guard_violation(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """Linking a local task to a global one is rejected, not silently applied (§3.3)."""
        local_id = json.loads(
            runner.invoke(cli, ["task", "add", "local", "--description", "d", "--json"]).output
        )[0]["id"]
        global_id = json.loads(
            runner.invoke(
                cli, ["task", "add", "global", "--description", "d", "--global", "--json"]
            ).output
        )[0]["id"]

        result = runner.invoke(
            cli, ["task", "link", local_id, global_id, "--relation", "blocks", "--json"]
        )
        assert result.exit_code == 5

    def test_add_with_parent_across_scopes_is_a_guard_violation(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """A new local task cannot --parent to a global one, or vice versa (§3.3)."""
        global_parent = json.loads(
            runner.invoke(
                cli, ["task", "add", "global parent", "--description", "d", "--global", "--json"]
            ).output
        )[0]["id"]

        result = runner.invoke(
            cli,
            [
                "task",
                "add",
                "local child",
                "--description",
                "d",
                "--parent",
                global_parent,
                "--json",
            ],
        )
        assert result.exit_code == 5

    def test_mixed_scope_ids_in_one_show_call_is_a_usage_error(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """`task show` with both a local and a global id in one call exits 2 (§3.3)."""
        local_id = json.loads(
            runner.invoke(cli, ["task", "add", "local", "--description", "d", "--json"]).output
        )[0]["id"]
        global_id = json.loads(
            runner.invoke(
                cli, ["task", "add", "global", "--description", "d", "--global", "--json"]
            ).output
        )[0]["id"]

        result = runner.invoke(cli, ["task", "show", local_id, global_id, "--json"])
        assert result.exit_code == 2


class TestDoctorGlobal:
    def test_global_is_null_when_never_used(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """doctor's global section is null on a project that has never used --global."""
        result = runner.invoke(cli, ["doctor", "--json"])
        payload = json.loads(result.output)
        assert payload["global"] is None

    def test_global_reports_counts_once_used(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """doctor's global section reports real counts once a --global task exists."""
        runner.invoke(cli, ["task", "add", "global one", "--description", "d", "--global"])
        result = runner.invoke(cli, ["doctor", "--json"])
        payload = json.loads(result.output)
        assert payload["global"] is not None
        assert payload["global"]["tasks"]["total"] == 1


class TestGlobalLinkScope:
    @staticmethod
    def _add_global(runner: CliRunner, title: str) -> str:
        return str(
            json.loads(
                runner.invoke(
                    cli, ["task", "add", title, "--description", "d", "--global", "--json"]
                ).output
            )[0]["id"]
        )

    def test_links_and_events_use_the_global_id_form(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """Linking two global tasks renders and records `TASK-GLOBAL-<n>`, both in
        `show`'s links and in the stored event values that make up the audit trail.
        """
        first = self._add_global(runner, "global one")
        second = self._add_global(runner, "global two")
        assert (first, second) == ("TASK-GLOBAL-1", "TASK-GLOBAL-2")

        link_result = runner.invoke(
            cli, ["task", "link", first, second, "--relation", "relates_to"]
        )
        assert link_result.exit_code == 0

        detail = json.loads(runner.invoke(cli, ["task", "show", first, "--json"]).output)[0]
        assert detail["links"] == [
            {"relation": "relates_to", "task_id": second, "direction": "outgoing"}
        ]
        link_events = [event for event in detail["events"] if event["field"] == "link:relates_to"]
        assert [event["new_value"] for event in link_events] == [second]

    def test_unlink_records_the_global_id_form(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """`unlink` on a global pair records the removal in the same id form."""
        first = self._add_global(runner, "global one")
        second = self._add_global(runner, "global two")
        runner.invoke(cli, ["task", "link", first, second, "--relation", "duplicates"])
        runner.invoke(cli, ["task", "unlink", first, second, "--relation", "duplicates"])

        detail = json.loads(runner.invoke(cli, ["task", "show", first, "--json"]).output)[0]
        assert detail["links"] == []
        unlink_events = [
            event
            for event in detail["events"]
            if event["field"] == "link:duplicates" and event["old_value"] is not None
        ]
        assert [event["old_value"] for event in unlink_events] == [second]

    def test_a_local_task_sharing_the_number_is_not_referenced(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A stored `TASK-GLOBAL-2` must not resolve against an unrelated local
        `TASK-2`: before the fix the event value was the bare `TASK-2`, so `show`
        reported the local task in `referenced` and pointed at the wrong record.
        """
        add_task("local one")
        add_task("local two")
        first = self._add_global(runner, "global one")
        second = self._add_global(runner, "global two")
        runner.invoke(cli, ["task", "link", first, second, "--relation", "relates_to"])

        detail = json.loads(runner.invoke(cli, ["task", "show", first, "--json"]).output)[0]
        assert second in detail["referenced"]
        assert "TASK-2" not in detail["referenced"]
