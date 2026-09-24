#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from corvee.cli.main import cli
from corvee.config import ProjectConfig


class TestTaskAddFromFile:
    def _write(self, tmp_path: Path, items: list[dict[str, object]]) -> Path:
        path = tmp_path / "batch.json"
        path.write_text(json.dumps(items))
        return path

    def test_creates_every_item_in_one_call(
        self, runner: CliRunner, project: ProjectConfig, tmp_path: Path
    ) -> None:
        """A JSON array of N items creates N tasks, returned in file order."""
        path = self._write(
            tmp_path,
            [
                {"title": "a", "description": "first"},
                {"title": "b", "description": "second"},
            ],
        )
        result = runner.invoke(cli, ["task", "add", "--from-file", str(path), "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert [t["title"] for t in payload] == ["a", "b"]
        assert [t["id"] for t in payload] == ["TASK-1", "TASK-2"]

    def test_applies_type_priority_and_label(
        self, runner: CliRunner, project: ProjectConfig, tmp_path: Path
    ) -> None:
        """type/priority/label fields on an item are honored, same as the single-task flags."""
        path = self._write(
            tmp_path,
            [
                {
                    "title": "a",
                    "description": "d",
                    "type": "bug",
                    "priority": "high",
                    "label": ["api", "urgent"],
                },
            ],
        )
        result = runner.invoke(cli, ["task", "add", "--from-file", str(path), "--json"])
        payload = json.loads(result.output)
        assert payload[0]["type"] == "bug"
        assert payload[0]["priority"] == "high"

        show = runner.invoke(cli, ["task", "show", payload[0]["id"], "--json"])
        assert sorted(json.loads(show.output)[0]["labels"]) == ["api", "urgent"]

    def test_defaults_apply_when_fields_are_omitted(
        self, runner: CliRunner, project: ProjectConfig, tmp_path: Path
    ) -> None:
        """An item with only title/description gets the same defaults a bare `task add` does."""
        path = self._write(tmp_path, [{"title": "a", "description": "d"}])
        result = runner.invoke(cli, ["task", "add", "--from-file", str(path), "--json"])
        payload = json.loads(result.output)
        assert payload[0]["type"] == "task"
        assert payload[0]["priority"] == "medium"

    def test_links_a_parent_within_the_batch_by_existing_id(
        self, runner: CliRunner, project: ProjectConfig, tmp_path: Path
    ) -> None:
        """parent references an id that already exists (not another item in the same file)."""
        parent_id = runner.invoke(cli, ["task", "add", "parent", "--description", "d", "--json"])
        parent_task_id = json.loads(parent_id.output)[0]["id"]
        path = self._write(
            tmp_path, [{"title": "child", "description": "d", "parent": parent_task_id}]
        )
        result = runner.invoke(cli, ["task", "add", "--from-file", str(path), "--json"])
        assert result.exit_code == 0
        show = runner.invoke(cli, ["task", "show", parent_task_id, "--json"])
        subtasks = json.loads(show.output)[0]["subtasks"]
        assert len(subtasks) == 1

    def test_one_bad_item_rolls_back_the_whole_batch(
        self, runner: CliRunner, project: ProjectConfig, tmp_path: Path
    ) -> None:
        """The first two items are valid; the third has an empty title. Nothing is created."""
        path = self._write(
            tmp_path,
            [
                {"title": "a", "description": "d"},
                {"title": "b", "description": "d"},
                {"title": "   ", "description": "d"},
            ],
        )
        result = runner.invoke(cli, ["task", "add", "--from-file", str(path), "--json"])
        assert result.exit_code == 2
        listing = runner.invoke(cli, ["task", "list", "--json"])
        assert json.loads(listing.output) == []

    def test_invalid_type_is_rejected_before_any_write(
        self, runner: CliRunner, project: ProjectConfig, tmp_path: Path
    ) -> None:
        """An unknown type value in any item fails the whole call, exit 2."""
        path = self._write(
            tmp_path,
            [
                {"title": "a", "description": "d"},
                {"title": "b", "description": "d", "type": "not-a-real-type"},
            ],
        )
        result = runner.invoke(cli, ["task", "add", "--from-file", str(path), "--json"])
        assert result.exit_code == 2
        listing = runner.invoke(cli, ["task", "list", "--json"])
        assert json.loads(listing.output) == []

    def test_empty_array_is_rejected(
        self, runner: CliRunner, project: ProjectConfig, tmp_path: Path
    ) -> None:
        """An empty JSON array has nothing to create and is a usage error, not a no-op."""
        path = self._write(tmp_path, [])
        result = runner.invoke(cli, ["task", "add", "--from-file", str(path), "--json"])
        assert result.exit_code == 2

    def test_non_array_json_is_rejected(
        self, runner: CliRunner, project: ProjectConfig, tmp_path: Path
    ) -> None:
        """A JSON object instead of an array is a usage error, not silently wrapped."""
        path = tmp_path / "batch.json"
        path.write_text(json.dumps({"title": "a", "description": "d"}))
        result = runner.invoke(cli, ["task", "add", "--from-file", str(path), "--json"])
        assert result.exit_code == 2

    def test_missing_title_in_an_item_is_rejected(
        self, runner: CliRunner, project: ProjectConfig, tmp_path: Path
    ) -> None:
        """An item with no title at all is a usage error, not an empty-string task."""
        path = self._write(tmp_path, [{"description": "d"}])
        result = runner.invoke(cli, ["task", "add", "--from-file", str(path), "--json"])
        assert result.exit_code == 2

    def test_cannot_combine_from_file_with_title_argument(
        self, runner: CliRunner, project: ProjectConfig, tmp_path: Path
    ) -> None:
        """--from-file and a TITLE argument together is ambiguous, rejected outright."""
        path = self._write(tmp_path, [{"title": "a", "description": "d"}])
        result = runner.invoke(
            cli, ["task", "add", "also a title", "--from-file", str(path), "--json"]
        )
        assert result.exit_code == 2

    def test_cannot_combine_from_file_with_description(
        self, runner: CliRunner, project: ProjectConfig, tmp_path: Path
    ) -> None:
        """--from-file and --description together is ambiguous, rejected outright."""
        path = self._write(tmp_path, [{"title": "a", "description": "d"}])
        result = runner.invoke(
            cli, ["task", "add", "--from-file", str(path), "--description", "d", "--json"]
        )
        assert result.exit_code == 2

    def test_missing_file_is_a_usage_error(self, runner: CliRunner, project: ProjectConfig) -> None:
        """A --from-file path that doesn't exist exits 2 via click's own Path(exists=True)."""
        result = runner.invoke(cli, ["task", "add", "--from-file", "/no/such/file.json", "--json"])
        assert result.exit_code == 2

    @pytest.mark.parametrize(
        "items",
        [
            pytest.param(["not a dict"], id="item_not_an_object"),
            pytest.param(
                [{"title": "a", "description": "   "}],
                id="blank_description",
            ),
            pytest.param(
                [{"title": "a", "description": "d", "priority": "not-a-real-priority"}],
                id="invalid_priority",
            ),
            pytest.param(
                [{"title": "a", "description": "d", "label": "api"}],
                id="label_not_a_list",
            ),
            pytest.param(
                [{"title": "a", "description": "d", "label": ["api", 1]}],
                id="label_item_not_a_string",
            ),
            pytest.param(
                [{"title": "a", "description": "d", "parent": 1}],
                id="parent_not_a_string",
            ),
        ],
    )
    def test_batch_item_validation_is_rejected(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        tmp_path: Path,
        items: list[object],
    ) -> None:
        """Each documented per-item validation rule fails the whole call, exit 2."""
        path = tmp_path / "batch.json"
        path.write_text(json.dumps(items))
        result = runner.invoke(cli, ["task", "add", "--from-file", str(path), "--json"])
        assert result.exit_code == 2
        listing = runner.invoke(cli, ["task", "list", "--json"])
        assert json.loads(listing.output) == []

    def test_invalid_json_is_a_usage_error(
        self, runner: CliRunner, project: ProjectConfig, tmp_path: Path
    ) -> None:
        """A file that exists but isn't valid JSON exits 2, not 1 internal_error."""
        path = tmp_path / "batch.json"
        path.write_text("not json at all")
        result = runner.invoke(cli, ["task", "add", "--from-file", str(path), "--json"])
        assert result.exit_code == 2

    def test_files_into_the_global_database(
        self, runner: CliRunner, project: ProjectConfig, tmp_path: Path
    ) -> None:
        """--global applies to the whole batch, same as it does to a single task add."""
        path = self._write(tmp_path, [{"title": "a", "description": "d"}])
        result = runner.invoke(cli, ["task", "add", "--from-file", str(path), "--global", "--json"])
        payload = json.loads(result.output)
        assert payload[0]["id"] == "TASK-GLOBAL-1"
