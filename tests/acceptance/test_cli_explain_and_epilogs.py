#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import click
import pytest
from click.testing import CliRunner

from corvee.cli.main import cli


class TestExplain:
    def test_exits_zero_and_is_non_empty(self, runner: CliRunner) -> None:
        """`corvee explain` exits 0 and prints a non-empty cheat sheet mentioning --actor."""
        result = runner.invoke(cli, ["explain"])
        assert result.exit_code == 0
        assert "corvee" in result.output
        assert "--actor" in result.output

    def test_does_not_accept_json(self, runner: CliRunner) -> None:
        """`explain` has no --json flag; its output is fixed plain text, not a query result."""
        result = runner.invoke(cli, ["explain", "--json"])
        assert result.exit_code == 2

    def test_splits_tasks_and_facts_into_separate_sections(self, runner: CliRunner) -> None:
        """The cheat sheet groups task-management and facts-management content
        under separate TASKS/FACTS headers instead of interleaving them, with
        task-only content (Claims) inside the TASKS section and fact-only
        content (fact add/search) inside the FACTS section.
        """
        result = runner.invoke(cli, ["explain"])
        tasks_index = result.output.index("TASKS")
        facts_index = result.output.index("FACTS")
        claims_index = result.output.index("Claims:")
        fact_add_index = result.output.index('corvee fact add "requests')
        assert tasks_index < claims_index < facts_index < fact_add_index

    def test_nudges_one_task_per_independent_item(self, runner: CliRunner) -> None:
        """The cheat sheet tells an agent to file one task per independently-
        resolvable item instead of bundling a batch into one umbrella task.
        """
        result = runner.invoke(cli, ["explain"])
        assert "One task per" in result.output
        assert "umbrella task" in result.output

    def test_nudges_non_default_type_priority_and_relations(self, runner: CliRunner) -> None:
        """The cheat sheet nudges away from always leaving --type/--priority at
        their defaults, and toward `task link --relation` for real dependencies.
        """
        result = runner.invoke(cli, ["explain"])
        assert "--type bug" in result.output
        assert "--priority high" in result.output
        assert "--relation blocks" in result.output


def _iter_leaf_commands(group: click.Group, prefix: str = "") -> "list[tuple[str, click.Command]]":
    """Every leaf (non-group) command, recursing into subcommand groups
    (`task`, `fact`) with its full dotted name for error messages.
    """
    leaves: list[tuple[str, click.Command]] = []
    for name, command in group.commands.items():
        full_name = f"{prefix}{name}"
        if isinstance(command, click.Group):
            leaves.extend(_iter_leaf_commands(command, prefix=f"{full_name} "))
        else:
            leaves.append((full_name, command))
    return leaves


class TestHelpEpilogs:
    def test_every_command_has_at_least_three_runnable_examples(self) -> None:
        """Every leaf command's epilog carries at least three lines starting with "corvee "."""
        for name, command in _iter_leaf_commands(cli):
            assert isinstance(command, click.Command)
            epilog = command.epilog or ""
            example_lines = [
                line for line in epilog.splitlines() if line.strip().startswith("corvee ")
            ]
            assert len(example_lines) >= 3, f"{name!r} has fewer than 3 example lines"

    def test_every_example_has_a_lead_in_sentence(self) -> None:
        """Each example line is preceded by a plain-language sentence, not another
        example line back to back — a reader should know what a command does
        before seeing it, not have to infer it from the flags alone.
        """
        for name, command in _iter_leaf_commands(cli):
            assert isinstance(command, click.Command)
            lines = (command.epilog or "").splitlines()
            for index, line in enumerate(lines):
                if not line.strip().startswith("corvee "):
                    continue
                previous = lines[index - 1].strip() if index > 0 else ""
                assert previous, f"{name!r}: example {line!r} has no lead-in sentence"
                assert not previous.startswith(
                    "corvee "
                ), f"{name!r}: example {line!r} is preceded by another example, not a sentence"
                assert previous not in {
                    "\\b",
                    "Examples:",
                }, f"{name!r}: example {line!r} has no real lead-in sentence"


class TestShortOptionAliases:
    def test_every_option_has_a_short_alias(self) -> None:
        """Every click.Option on every leaf command carries a one-character
        alias alongside its long form, so a command's full flag set is never
        exclusively long-form.
        """
        for name, command in _iter_leaf_commands(cli):
            assert isinstance(command, click.Command)
            for param in command.params:
                if not isinstance(param, click.Option) or param.name == "help":
                    continue
                short_opts = [opt for opt in param.opts if opt.startswith("-") and len(opt) == 2]
                assert short_opts, f"{name!r}: {param.opts!r} has no short alias"

    def test_no_two_options_share_a_short_alias_within_one_command(self) -> None:
        """Within a single command, every short alias is unique -- click itself
        would refuse to register the command otherwise, but this documents the
        invariant directly rather than relying on import-time failure alone.
        """
        for name, command in _iter_leaf_commands(cli):
            assert isinstance(command, click.Command)
            seen: dict[str, str] = {}
            for param in command.params:
                if not isinstance(param, click.Option):
                    continue
                for opt in param.opts:
                    if opt.startswith("-") and len(opt) == 2:
                        assert opt not in seen, (
                            f"{name!r}: {opt!r} used by both {seen.get(opt)!r} and "
                            f"{param.name!r}"
                        )
                        seen[opt] = param.name


class TestFactGroupHelp:
    def test_shows_the_fact_lifecycle(self) -> None:
        """The `fact` group's own help text explains the unverified/verified/
        retracted lifecycle, not just the one-line summaries of each
        subcommand that happen to mention those words in passing.
        """
        fact_group = cli.commands["fact"]
        assert isinstance(fact_group, click.Group)
        help_text = fact_group.help or ""
        for word in ("unverified", "verified", "retracted", "revise"):
            assert word in help_text, f"fact group help is missing {word!r}"


class TestLsAliasHidden:
    @pytest.mark.parametrize("group", ["task", "fact"])
    def test_ls_not_listed_in_help(self, runner: CliRunner, group: str) -> None:
        """`corvee task|fact --help` lists `list` but not its `ls` alias."""
        result = runner.invoke(cli, [group, "--help"])
        assert result.exit_code == 0
        assert "\n  list " in result.output
        assert "\n  ls " not in result.output

    @pytest.mark.parametrize("group", ["task", "fact"])
    def test_ls_still_invokable(self, runner: CliRunner, group: str) -> None:
        """`corvee task|fact ls --help` still works even though it's hidden from
        the parent group's listing.
        """
        result = runner.invoke(cli, [group, "ls", "--help"])
        assert result.exit_code == 0


class TestNoSpecReferences:
    def test_help_text_never_points_at_the_spec(self) -> None:
        """Help text is self-contained: no "§" section reference and no mention of
        the spec document, which a CLI user has no reason to have open.
        """
        for name, command in _iter_leaf_commands(cli):
            assert isinstance(command, click.Command)
            texts = [command.help or "", command.epilog or ""]
            texts.extend(getattr(param, "help", None) or "" for param in command.params)
            for text in texts:
                assert "§" not in text, f"{name!r} help text references a spec section: {text!r}"
                assert "spec.md" not in text, f"{name!r} help text mentions spec.md: {text!r}"
