#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json

import pytest

from corvee.errors import NotFoundError
from corvee.output import (
    _display_width,
    emit_error,
    emit_fact_detail,
    emit_facts,
    emit_task_detail,
    emit_tasks,
    filter_fields,
    render_detail_header,
    render_table,
)

FACT = {
    "id": "FACT-1",
    "claim": "package X is MIT-licensed",
    "status": "verified",
    "verified_at": "2026-01-01T00:00:00.000Z",
    "verified_by": "agent:test",
    "proof": "see LICENSE",
    "created_at": "2026-01-01T00:00:00.000Z",
    "updated_at": "2026-01-01T00:00:00.000Z",
}

TASK = {
    "id": "TASK-1",
    "title": "do the thing",
    "description": "",
    "type": "task",
    "priority": "high",
    "state": "open",
    "claimed_by": None,
    "claimed_at": None,
    "created_at": "2026-01-01T00:00:00.000Z",
    "updated_at": "2026-01-01T00:00:00.000Z",
}


class TestFilterFields:
    def test_returns_full_dict_when_no_fields_given(self) -> None:
        """fields=None means no projection — the full documented shape passes through unchanged."""
        assert filter_fields(TASK, None) == TASK

    def test_projects_requested_keys_in_order(self) -> None:
        """Projection keeps only the requested keys, in the order they were requested."""
        assert list(filter_fields(TASK, ["title", "id"]).keys()) == ["title", "id"]


class TestRenderTable:
    def test_empty_list_is_empty_string(self) -> None:
        """An empty row list renders no table at all, not a header-only table."""
        assert render_table([]) == ""

    def test_includes_header_and_row(self) -> None:
        """The rendered table has an uppercased header row and the field values below it."""
        table = render_table([TASK], fields=["id", "title"])
        lines = table.splitlines()
        assert lines[0].split() == ["ID", "TITLE"]
        assert "TASK-1" in lines[1]
        assert "do the thing" in lines[1]

    def test_null_column_renders_blank_not_the_string_none(self) -> None:
        """A None value (e.g. an unclaimed task's claimed_by) renders as an empty
        cell, not the string "None".
        """
        table = render_table([TASK], fields=["id", "claimed_by"])
        lines = table.splitlines()
        assert "None" not in lines[1]

    def test_embedded_newlines_do_not_break_row_alignment(self) -> None:
        """A multi-line field value (an expected shape for agent-written free
        text, §5.2) collapses onto one physical line instead of splitting the
        row and pushing later columns out from under their header.
        """
        multiline_task = {**TASK, "title": "Line one\nLine two\nLine three"}
        table = render_table([multiline_task], fields=["id", "title", "priority"])
        lines = table.splitlines()
        assert len(lines) == 2
        assert "\n" not in lines[1]
        assert "Line one" in lines[1]
        assert "Line two" in lines[1]
        assert "high" in lines[1]

    def test_wide_characters_keep_later_columns_aligned(self) -> None:
        """A CJK title takes two terminal cells per character, so the column after
        it starts at the same cell as for an ASCII title of the same width.
        """
        wide = {**TASK, "title": "四字熟語"}
        narrow = {**TASK, "title": "12345678"}
        lines = render_table([wide, narrow], fields=["id", "title", "priority"]).splitlines()
        assert lines[1].rstrip() == "TASK-1  四字熟語  high"
        assert lines[2].rstrip() == "TASK-1  12345678  high"


class TestDisplayWidth:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("do the thing", 12),
            ("", 0),
            ("四字熟語", 8),
            ("\uff21\uff22", 4),  # fullwidth latin, east_asian_width "F"
            ("e\u0301", 1),
        ],
    )
    def test_counts_terminal_cells_not_code_points(self, text: str, expected: int) -> None:
        """Wide and fullwidth characters take two cells, a combining mark none."""
        assert _display_width(text) == expected


class TestRenderDetailHeader:
    def test_flat_fields_then_block_field(self) -> None:
        """Flat columns render as one `field: value` line each, followed by a
        blank line and the block field under its own label -- lowercase, like
        every other field, not a second, capitalized vocabulary.
        """
        row = {**TASK, "description": "repro: run make test twice in a row"}
        header = render_detail_header(
            row, ["id", "title", "description"], block_field="description"
        )
        assert header.splitlines() == [
            "id: TASK-1",
            "title: do the thing",
            "",
            "description:",
            "repro: run make test twice in a row",
        ]

    def test_omits_block_when_not_in_columns(self) -> None:
        """A caller that projected the block field out via --fields keeps it out here too."""
        header = render_detail_header(TASK, ["id", "title"], block_field="description")
        assert header == "id: TASK-1\ntitle: do the thing"

    def test_null_flat_field_shows_none_placeholder(self) -> None:
        """A None flat-field value (e.g. an unclaimed task's claimed_by) shows
        (none), not the string "None", directly above the block field.
        """
        header = render_detail_header(TASK, ["id", "claimed_by"], block_field="description")
        assert header.splitlines() == ["id: TASK-1", "claimed_by: (none)"]

    def test_block_field_shows_none_placeholder_when_missing(self) -> None:
        """An unset block value (e.g. an unverified fact's proof) shows (none), not "None"."""
        row = {**FACT, "proof": None}
        header = render_detail_header(row, ["id", "claim", "proof"], block_field="proof")
        assert header.splitlines()[-2:] == ["proof:", "(none)"]


class TestEmitTaskDetail:
    def _row(self, **overrides: object) -> dict[str, object]:
        return {**TASK, "labels": [], "links": [], "subtasks": [], "events": [], **overrides}

    def test_plain_output_uses_markdown_header_not_table(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The header block is `field: value` lines, not a fixed-width table --
        no uppercased column-header row.
        """
        row = self._row(description="a long free-text description explaining repro steps")
        emit_task_detail([row], as_json=False)
        out = capsys.readouterr().out
        assert "id: TASK-1" in out
        assert "description:" in out
        assert "a long free-text description explaining repro steps" in out
        assert "DESCRIPTION" not in out
        # The id appears exactly once -- no separate "== id ==" divider repeating it.
        assert out.count("TASK-1") == 1

    def test_multiple_rows_each_get_their_own_header_in_order(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Each id given to `show` gets its own header block, in the order given."""
        rows = [self._row(id="TASK-2"), self._row(id="TASK-1")]
        emit_task_detail(rows, as_json=False)
        out = capsys.readouterr().out
        assert out.index("id: TASK-2") < out.index("id: TASK-1")

    def test_json_output_unaffected(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--json still returns the full row shape, ignoring the plain-text layout change."""
        row = self._row()
        emit_task_detail([row], as_json=True)
        payload = json.loads(capsys.readouterr().out)
        assert payload == [row]

    def test_plain_output_lists_links_by_direction_and_relation(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A task with links renders one `direction relation task_id` line per link."""
        row = self._row(
            links=[{"direction": "outgoing", "relation": "blocks", "task_id": "TASK-2"}]
        )
        emit_task_detail([row], as_json=False)
        out = capsys.readouterr().out
        assert "links:" in out
        assert "outgoing blocks TASK-2" in out


class TestEmitFactDetail:
    def test_plain_output_uses_markdown_header_not_table(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        row = {**FACT, "events": []}
        emit_fact_detail([row], as_json=False)
        out = capsys.readouterr().out
        assert "id: FACT-1" in out
        assert "claim: package X is MIT-licensed" in out
        assert "proof:" in out
        assert "see LICENSE" in out
        assert "CLAIM" not in out

    def test_plain_output_renders_revised_and_unverified_event_lines(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A "revised" event shows the old and new claim; an "unverified" event
        shows its note -- the two event kinds specific to facts, not tasks.
        """
        row = {
            **FACT,
            "events": [
                {
                    "kind": "revised",
                    "old_value": "package X is MIT-licensed",
                    "new_value": "package X is Apache-2.0-licensed",
                    "actor": "agent:test",
                    "created_at": "2026-01-01T00:00:00.000Z",
                },
                {
                    "kind": "unverified",
                    "note": "license file changed upstream",
                    "actor": "agent:test",
                    "created_at": "2026-01-02T00:00:00.000Z",
                },
            ],
        }
        emit_fact_detail([row], as_json=False)
        out = capsys.readouterr().out
        assert "'package X is MIT-licensed' -> 'package X is Apache-2.0-licensed'" in out
        assert "license file changed upstream" in out


class TestEmitTasks:
    def test_json_prints_array(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--json output is a JSON array containing exactly the given task objects."""
        emit_tasks([TASK], as_json=True)
        payload = json.loads(capsys.readouterr().out)
        assert payload == [TASK]

    def test_json_empty_list_prints_empty_array(self, capsys: pytest.CaptureFixture[str]) -> None:
        """An empty task list still prints a valid empty JSON array, not nothing."""
        emit_tasks([], as_json=True)
        assert json.loads(capsys.readouterr().out) == []

    def test_table_respects_fields(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Table output shows only the requested columns, omitting the rest."""
        emit_tasks([TASK], as_json=False, fields=["id", "title"])
        out = capsys.readouterr().out
        assert "TITLE" in out
        assert "DESCRIPTION" not in out

    def test_table_default_omits_description(self, capsys: pytest.CaptureFixture[str]) -> None:
        """With no --fields, the table drops the long free-text description column
        by default -- it's what blows up a fixed-width row past terminal width.
        """
        emit_tasks([TASK], as_json=False)
        out = capsys.readouterr().out
        assert "TITLE" in out
        assert "DESCRIPTION" not in out

    def test_table_fields_can_still_request_description(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--fields can still ask for description explicitly; only the default omits it."""
        emit_tasks([TASK], as_json=False, fields=["id", "description"])
        out = capsys.readouterr().out
        assert "DESCRIPTION" in out

    def test_json_default_still_includes_description(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--json is unaffected by the table's narrower default -- it always returns
        the full row shape.
        """
        emit_tasks([TASK], as_json=True)
        payload = json.loads(capsys.readouterr().out)
        assert "description" in payload[0]


class TestEmitFacts:
    def test_json_prints_array(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--json output is a JSON array containing exactly the given fact objects."""
        emit_facts([FACT], as_json=True)
        payload = json.loads(capsys.readouterr().out)
        assert payload == [FACT]

    def test_table_defaults_to_fact_columns(self, capsys: pytest.CaptureFixture[str]) -> None:
        """With no --fields, the table falls back to the fact column set, not the task one."""
        emit_facts([FACT], as_json=False)
        out = capsys.readouterr().out
        assert "CLAIM" in out
        assert "STATUS" in out

    def test_table_respects_fields(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Table output for facts shows only the requested columns, omitting the rest."""
        emit_facts([FACT], as_json=False, fields=["id", "claim"])
        out = capsys.readouterr().out
        assert "CLAIM" in out
        assert "STATUS" not in out

    def test_table_default_omits_proof(self, capsys: pytest.CaptureFixture[str]) -> None:
        """With no --fields, the table drops the long free-text proof column by
        default -- the fact-group equivalent of description on tasks.
        """
        emit_facts([FACT], as_json=False)
        out = capsys.readouterr().out
        assert "CLAIM" in out
        assert "PROOF" not in out

    def test_table_fields_can_still_request_proof(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--fields can still ask for proof explicitly; only the default omits it."""
        emit_facts([FACT], as_json=False, fields=["id", "proof"])
        out = capsys.readouterr().out
        assert "PROOF" in out


class TestEmitError:
    def test_writes_json_object_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A CorveeError writes a JSON {"error": {...}} object to stderr, nothing to stdout."""
        error = NotFoundError("task_not_found", "no such task", task_id="TASK-99")
        emit_error(error)
        captured = capsys.readouterr()
        assert captured.out == ""
        payload = json.loads(captured.err)
        assert payload == {
            "error": {
                "code": "task_not_found",
                "message": "no such task",
                "task_id": "TASK-99",
            },
        }
