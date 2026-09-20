#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from pathlib import Path

import pytest

from corvee.config import (
    CONFIG_DIRNAME,
    bootstrap_project,
    global_db_path,
    resolve_project,
)
from corvee.errors import ConfigError


class TestBootstrapProject:
    def test_creates_config_and_db_but_not_gitignore(self, tmp_path: Path) -> None:
        """A fresh directory gets config.toml and a DB file. No .gitignore exists
        yet, so it is left alone rather than created from scratch (GH#29).
        """
        result = bootstrap_project(tmp_path)

        assert result.config_created is True
        assert result.gitignore_status == "skipped"
        assert (tmp_path / CONFIG_DIRNAME / "config.toml").is_file()
        assert not (tmp_path / ".gitignore").exists()
        assert result.db_path.is_file()

    def test_db_path_argument_is_written_instead_of_the_default(self, tmp_path: Path) -> None:
        """A given db_path lands verbatim in config.toml and resolves the database there."""
        result = bootstrap_project(tmp_path, db_path="custom/nested.db")

        assert (
            tmp_path / CONFIG_DIRNAME / "config.toml"
        ).read_text() == 'db_path = "custom/nested.db"\n'
        assert result.db_path == (tmp_path / CONFIG_DIRNAME / "custom" / "nested.db").resolve()

    def test_db_path_argument_is_ignored_once_a_config_already_exists(self, tmp_path: Path) -> None:
        """db_path only applies while config.toml is being created, like every other init flag."""
        bootstrap_project(tmp_path)
        before = (tmp_path / CONFIG_DIRNAME / "config.toml").read_text()

        bootstrap_project(tmp_path, db_path="ignored.db")

        assert (tmp_path / CONFIG_DIRNAME / "config.toml").read_text() == before

    def test_is_idempotent_and_touches_nothing_on_second_run(self, tmp_path: Path) -> None:
        """Re-running bootstrap on an already-initialized directory changes nothing on disk."""
        first = bootstrap_project(tmp_path)
        config_mtime = first.config_path.stat().st_mtime_ns
        db_contents = first.db_path.read_bytes()

        second = bootstrap_project(tmp_path)

        assert second.config_created is False
        assert second.gitignore_status == "skipped"
        assert second.config_path.stat().st_mtime_ns == config_mtime
        assert second.db_path.read_bytes() == db_contents

    def test_adds_gitignore_entry_only_if_the_file_already_exists(self, tmp_path: Path) -> None:
        """An existing .gitignore keeps its content, gains only the .corvee/ entry, once."""
        (tmp_path / ".gitignore").write_text("node_modules/\n")
        result = bootstrap_project(tmp_path)
        assert result.gitignore_status == "appended"
        content = (tmp_path / ".gitignore").read_text()
        assert "node_modules/" in content
        assert ".corvee/" in content

        result_again = bootstrap_project(tmp_path)
        assert result_again.gitignore_status == "up_to_date"

    def test_never_creates_a_gitignore_from_scratch(self, tmp_path: Path) -> None:
        """No .gitignore in the directory means bootstrap leaves none behind."""
        result = bootstrap_project(tmp_path)
        assert result.gitignore_status == "skipped"
        assert not (tmp_path / ".gitignore").exists()

    def test_never_touches_an_existing_agents_md(self, tmp_path: Path) -> None:
        """corvee no longer writes to AGENTS.md at all; a project's file, if any,
        is left byte-for-byte untouched.
        """
        agents_path = tmp_path / "AGENTS.md"
        original = "# My project\n\nSome existing notes.\n"
        agents_path.write_text(original)

        bootstrap_project(tmp_path)

        assert agents_path.read_text() == original

    def test_never_creates_an_agents_md_from_scratch(self, tmp_path: Path) -> None:
        """No AGENTS.md in the directory means bootstrap leaves none behind (GH#29)."""
        bootstrap_project(tmp_path)
        assert not (tmp_path / "AGENTS.md").exists()

    def test_never_overwrites_an_existing_database(self, tmp_path: Path) -> None:
        """Re-running bootstrap never truncates a database that already holds data."""
        first = bootstrap_project(tmp_path)
        conn = sqlite3.connect(first.db_path)
        conn.execute(
            "INSERT INTO tasks (title, created_at, updated_at) VALUES ('x', 'a', 'a')",
        )
        conn.commit()
        conn.close()

        bootstrap_project(tmp_path)

        conn = sqlite3.connect(first.db_path)
        count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        conn.close()
        assert count == 1


class TestResolveProject:
    def test_walks_up_from_a_subdirectory(self, tmp_path: Path) -> None:
        """Resolution walks upward from a nested subdirectory to find the project root."""
        bootstrap_project(tmp_path)
        subdir = tmp_path / "a" / "b"
        subdir.mkdir(parents=True)

        project = resolve_project(subdir)

        assert project.config_path == tmp_path / CONFIG_DIRNAME / "config.toml"

    def test_root_is_the_directory_above_dot_corvee_not_dot_corvee_itself(
        self, tmp_path: Path
    ) -> None:
        """`.root` is the actual project root (what a user would call "the
        project directory"), not `.corvee` -- a caller asking `.config_path.parent`
        for this gets `.corvee` instead, one directory too deep.
        """
        bootstrap_project(tmp_path)

        project = resolve_project(tmp_path)

        assert project.root == tmp_path

    def test_raises_config_error_when_not_found(self, tmp_path: Path) -> None:
        """No .corvee/config.toml anywhere upward raises ConfigError (exit 6)."""
        with pytest.raises(ConfigError) as excinfo:
            resolve_project(tmp_path)
        assert excinfo.value.exit_code == 6

    def test_a_config_that_is_not_valid_toml_is_a_config_error(self, tmp_path: Path) -> None:
        """A config.toml TOML cannot parse exits 6, naming the file it could not read."""
        corvee_dir = tmp_path / CONFIG_DIRNAME
        corvee_dir.mkdir()
        (corvee_dir / "config.toml").write_text("db_path = \n")

        with pytest.raises(ConfigError) as excinfo:
            resolve_project(tmp_path)

        assert excinfo.value.exit_code == 6
        assert excinfo.value.code == "invalid_config"
        assert str(corvee_dir / "config.toml") in excinfo.value.message

    def test_a_config_that_is_not_utf8_is_a_config_error(self, tmp_path: Path) -> None:
        """A config.toml holding binary exits 6 like any other unreadable one."""
        corvee_dir = tmp_path / CONFIG_DIRNAME
        corvee_dir.mkdir()
        (corvee_dir / "config.toml").write_bytes(b'db_path = "x.db"\n\xff\xfe\n')

        with pytest.raises(ConfigError) as excinfo:
            resolve_project(tmp_path)

        assert excinfo.value.exit_code == 6
        assert excinfo.value.code == "invalid_config"

    def test_a_db_path_that_is_not_a_string_is_a_config_error(self, tmp_path: Path) -> None:
        """`db_path = 42` exits 6 with a message naming the type, rather than dying
        on the path join with a TypeError.
        """
        corvee_dir = tmp_path / CONFIG_DIRNAME
        corvee_dir.mkdir()
        (corvee_dir / "config.toml").write_text("db_path = 42\n")

        with pytest.raises(ConfigError) as excinfo:
            resolve_project(tmp_path)

        assert excinfo.value.exit_code == 6
        assert excinfo.value.code == "invalid_config"
        assert "db_path must be a string, got int" in excinfo.value.message

    def test_relative_db_path_resolves_against_config_dir_not_cwd(self, tmp_path: Path) -> None:
        """A relative db_path resolves against the config file's own directory, not cwd."""
        corvee_dir = tmp_path / CONFIG_DIRNAME
        corvee_dir.mkdir()
        (corvee_dir / "config.toml").write_text('db_path = "../shared/corvee.db"\n')

        project = resolve_project(tmp_path)

        assert project.db_path == (tmp_path / "shared" / "corvee.db").resolve()


class TestGlobalDbPath:
    def test_is_fixed_under_the_home_directory(self, tmp_path: Path) -> None:
        """The global database (§3.3) has one fixed path, no config file to look it up through."""
        # $HOME is already isolated to tmp_path/home by the autouse _fake_home fixture.
        assert global_db_path() == Path.home() / CONFIG_DIRNAME / "corvee.db"
        assert global_db_path() == tmp_path / "home" / CONFIG_DIRNAME / "corvee.db"

    def test_env_var_overrides_it(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """CORVEE_GLOBAL_DB redirects the global db, for test/tooling isolation only."""
        scratch = tmp_path / "scratch" / "corvee.db"
        monkeypatch.setenv("CORVEE_GLOBAL_DB", str(scratch))
        assert global_db_path() == scratch

    def test_unset_env_var_leaves_the_fixed_path(self, tmp_path: Path) -> None:
        """Without the override, the path is still the one fixed home-relative location."""
        assert global_db_path() == Path.home() / CONFIG_DIRNAME / "corvee.db"
