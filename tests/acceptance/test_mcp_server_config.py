#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from pathlib import Path

import pytest

from corvee.config import ProjectConfig, bootstrap_project
from corvee.errors import ConfigError
from corvee.mcp.server import resolve_server_project


class TestResolveServerProjectExplicit:
    def test_explicit_project_root_resolves_that_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An explicit project_root resolves that project regardless of cwd."""
        real_project = tmp_path / "real-project"
        real_project.mkdir()
        init_result = bootstrap_project(real_project)

        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)

        project = resolve_server_project(real_project)
        assert project is not None
        assert project.db_path == init_result.db_path

    def test_explicit_project_root_that_does_not_resolve_raises(self, tmp_path: Path) -> None:
        """A wrong explicit project_root is a real usage error -- it raises
        rather than silently falling back to global-only mode, so the server
        refuses to start instead of serving from the wrong place.
        """
        with pytest.raises(ConfigError):
            resolve_server_project(tmp_path / "nope")


class TestResolveServerProjectAutoDetect:
    def test_no_project_root_auto_detects_from_cwd(
        self, project: ProjectConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Omitting project_root resolves the project at cwd, exactly like
        every CLI command's own default -- no flag needed when the host sets
        the spawned process's working directory to the project.
        """
        resolved = resolve_server_project(None)
        assert resolved is not None
        assert resolved.db_path == project.db_path

    def test_no_project_root_and_no_project_at_cwd_falls_back_to_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Omitting project_root with nothing found at cwd falls back to
        None (global-only mode) rather than raising -- the server still
        starts, the same graceful degrade `scopes_for` already applies at
        the CLI layer for a merged read with no local project.
        """
        monkeypatch.chdir(tmp_path)
        assert resolve_server_project(None) is None
