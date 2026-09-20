#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from corvee.db.connection import open_connection
from corvee.errors import ConfigError

# What `init` did to `.gitignore`, the one file it appends to but never
# creates from scratch: "appended" (the `.corvee/` entry was missing and got
# added to an existing file), "up_to_date" (already present, nothing
# written), or "skipped" (no `.gitignore` in this directory at all, so
# nothing was written and nothing was created).
TouchStatus = Literal["appended", "up_to_date", "skipped"]

CONFIG_DIRNAME = ".corvee"
CONFIG_FILENAME = "config.toml"
DEFAULT_DB_FILENAME = "corvee.db"

# Internal escape hatch, not part of the documented CLI/config surface: lets
# tests and agent tooling redirect the global database to a scratch file
# instead of the real ~/.corvee/corvee.db. Ordinary use never sets this —
# there is still only ever one fixed global db location for a real user.
GLOBAL_DB_OVERRIDE_ENV = "CORVEE_GLOBAL_DB"

# `init` never writes either of these into a file itself — it only prints
# them, so a human can paste whichever fits into place on their own terms.
# Two separate texts because the two destinations mean different things by
# "this": AGENTS_BLOCK_LOCAL's "this project"/"this codebase" is true for a
# project's own AGENTS.md, but false for a global, cross-project config like
# ~/.claude/CLAUDE.md, which applies to every project on the machine —
# including ones that never ran `corvee init` at all.
AGENTS_BLOCK_LOCAL = (
    "## Task tracking and facts (corvee)\n"
    "\n"
    "This project tracks tasks and checked-true facts with `corvee`, a local,\n"
    "multi-agent-aware CLI task tracker and fact store. Identify yourself with\n"
    "`corvee --actor agent:claude --session-id <token> <command>` (or the\n"
    "CORVEE_ACTOR/CORVEE_SESSION_ID environment variables, which the flags\n"
    "override) so every call stays a plain `corvee ...` command instead of an\n"
    "env-var-prefixed one a permission allowlist can't match. Run\n"
    "`corvee explain` for a full usage guide before doing anything else with it.\n"
    "\n"
    "Before asserting something uncertain about this codebase (a version number,\n"
    "a tool's exact behavior, a decision from an earlier session), check `corvee\n"
    "fact search` for an existing `verified` fact rather than guessing. Only mark\n"
    "a fact `verified` when `--proof` names something reproducible: a command's\n"
    "output, a specific test run, a file and line. A fact you cannot back with\n"
    "that stays `unverified`.\n"
)
AGENTS_BLOCK_GLOBAL = (
    "## Task tracking and facts (corvee)\n"
    "\n"
    "Projects that have run `corvee init` track tasks and checked-true facts\n"
    "with `corvee`, a local, multi-agent-aware CLI task tracker and fact\n"
    "store. Check for `.corvee/config.toml`, or run `corvee doctor`, before\n"
    "assuming the current project uses it — not every project will. Where it\n"
    "applies, identify yourself with `corvee --actor agent:claude --session-id\n"
    "<token> <command>` (or the CORVEE_ACTOR/CORVEE_SESSION_ID environment\n"
    "variables, which the flags override) so every call stays a plain\n"
    "`corvee ...` command instead of an env-var-prefixed one a permission\n"
    "allowlist can't match. Run `corvee explain` for a full usage guide before\n"
    "doing anything else with it.\n"
    "\n"
    "Before asserting something uncertain (a version number, a tool's exact\n"
    "behavior, a decision from an earlier session) in a project that uses it,\n"
    "check `corvee fact search` for an existing `verified` fact rather than\n"
    "guessing. Only mark a fact `verified` when `--proof` names something\n"
    "reproducible: a command's output, a specific test run, a file and line.\n"
    "A fact you cannot back with that stays `unverified`.\n"
)


@dataclass(frozen=True)
class ProjectConfig:
    config_path: Path
    db_path: Path

    @property
    def root(self) -> Path:
        """The project root: the directory containing `.corvee/`, i.e. what
        a user would call "the project directory". `config_path.parent` is
        `.corvee` itself, one directory too deep -- a mistake made at
        every call site that needed "the project root" until this
        property existed (TASK-27).
        """
        return self.config_path.parent.parent


@dataclass(frozen=True)
class InitResult:
    config_path: Path
    db_path: Path
    config_created: bool
    gitignore_status: TouchStatus


def _find_config_upward(start: Path) -> Path | None:
    """Walk up from `start` to the nearest .corvee/config.toml, like git's .git search."""
    current = start.resolve()
    while True:
        candidate = current / CONFIG_DIRNAME / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        if current.parent == current:
            return None
        current = current.parent


def global_db_path() -> Path:
    """The one fixed location of the global database.

    No `config.toml`, no override for ordinary use — there is only ever one,
    shared across every project on the machine. `$CORVEE_GLOBAL_DB`, if set,
    redirects it to a scratch file instead; that escape hatch exists only so
    tests and agent tooling can exercise --global scope without touching a
    real user's database, never for normal use.
    """
    override = os.environ.get(GLOBAL_DB_OVERRIDE_ENV)
    if override:
        return Path(override)
    return Path.home() / CONFIG_DIRNAME / DEFAULT_DB_FILENAME


def project_exists(start: Path | None = None) -> bool:
    """Cheap existence check for the local project, mirroring `global_db_path().is_file()`.

    Lets a caller that only wants local data *if it happens to be there*
    (§3.3's `--scope all`/`global` merge, `doctor`) skip it silently instead
    of provoking `resolve_project`'s loud `ConfigError`.
    """
    return _find_config_upward(start or Path.cwd()) is not None


def resolve_project(start: Path | None = None) -> ProjectConfig:
    config_path = _find_config_upward(start or Path.cwd())
    if config_path is None:
        raise ConfigError(
            "no_project",
            "no .corvee/config.toml found in this directory or any parent; run `corvee init`",
        )
    try:
        with config_path.open("rb") as f:
            data = tomllib.load(f)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as error:
        raise ConfigError(
            "invalid_config",
            f"cannot read {config_path}: {error}",
            path=str(config_path),
        ) from error
    db_path_value = data.get("db_path", DEFAULT_DB_FILENAME)
    if not isinstance(db_path_value, str):
        raise ConfigError(
            "invalid_config",
            f"cannot read {config_path}: db_path must be a string, "
            f"got {type(db_path_value).__name__}",
            path=str(config_path),
        )
    # A relative db_path resolves against config.toml's own directory, never cwd.
    db_path = (config_path.parent / db_path_value).resolve()
    return ProjectConfig(config_path=config_path, db_path=db_path)


def _ensure_gitignore_entry(directory: Path) -> TouchStatus:
    """Append the `.corvee/` entry to an existing `.gitignore`, never create one from
    scratch. `.gitignore`'s absence usually means the project doesn't want an
    automated tool writing one, or isn't a git repo at all — low-consequence to skip,
    since `.corvee/` never containing anything git would refuse to ignore anyway.
    """
    gitignore_path = directory / ".gitignore"
    if not gitignore_path.is_file():
        return "skipped"
    entry = f"{CONFIG_DIRNAME}/"
    content = gitignore_path.read_text()
    if entry in content.splitlines():
        return "up_to_date"
    if content and not content.endswith("\n"):
        content += "\n"
    content += f"{entry}\n"
    gitignore_path.write_text(content)
    return "appended"


def bootstrap_project(directory: Path, *, db_path: str | None = None) -> InitResult:
    """Idempotently set up a project in `directory` (never over anything that exists).

    Never truncates an existing config or database — a second `init` in the
    same directory is a safe, speculative no-op for anything already present.
    `db_path`, if given, is only used the first time a config is created; it
    is ignored (with the existing config left untouched) on a re-run. Never
    touches AGENTS.md; the caller is responsible for showing
    `AGENTS_BLOCK_LOCAL`/`AGENTS_BLOCK_GLOBAL` to the user instead.
    """
    corvee_dir = directory / CONFIG_DIRNAME
    config_path = corvee_dir / CONFIG_FILENAME

    config_created = not config_path.exists()
    if config_created:
        corvee_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text(f'db_path = "{db_path or DEFAULT_DB_FILENAME}"\n')

    gitignore_status = _ensure_gitignore_entry(directory)

    project = resolve_project(directory)
    project.db_path.parent.mkdir(parents=True, exist_ok=True)
    open_connection(project.db_path).close()

    return InitResult(
        config_path=config_path,
        db_path=project.db_path,
        config_created=config_created,
        gitignore_status=gitignore_status,
    )
