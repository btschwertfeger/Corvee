#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import re
from pathlib import Path

WORKFLOW_PATH = Path(__file__).parents[2] / ".github" / "workflows" / "cicd.yaml"

# Actions that call the GitHub Pages API itself (not just upload a build
# artifact) and therefore require the `pages: write` permission to not
# silently no-op or fail (this is exactly how the docs/deploy-docs split
# regressed once already: the permission moved to deploy-docs but a step
# needing it was left behind in the permission-less docs job).
# actions/upload-pages-artifact is deliberately excluded: it only uploads a
# workflow artifact and needs no Pages-specific permission.
_PAGES_ACTIONS = ("actions/configure-pages", "actions/deploy-pages")
_JOB_HEADER_RE = re.compile(r"^  ([a-zA-Z0-9_-]+):\s*$")


def _split_into_jobs(text: str) -> dict[str, str]:
    """Split the `jobs:` section into per-job source text, keyed by job
    name. Deliberately not a general YAML parser (PyYAML isn't a project
    dependency, and adding one just for this test would be overkill) --
    this file's job blocks are all 2-space-indented top-level keys under
    `jobs:`, and that is the only shape this test needs to understand.
    """
    lines = text.splitlines()
    start = lines.index("jobs:") + 1
    jobs: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines[start:]:
        match = _JOB_HEADER_RE.match(line)
        if match:
            current = match.group(1)
            jobs[current] = []
        elif current is not None:
            jobs[current].append(line)
    return {name: "\n".join(body) for name, body in jobs.items()}


def _has_top_level_pages_write(text: str) -> bool:
    workflow_level = text.split("\njobs:", 1)[0]
    return "pages: write" in workflow_level


class TestPagesPermission:
    def test_every_step_using_a_pages_action_runs_in_a_job_with_pages_write(self) -> None:
        text = WORKFLOW_PATH.read_text()
        top_level_pages_write = _has_top_level_pages_write(text)
        for job_name, body in _split_into_jobs(text).items():
            for action in _PAGES_ACTIONS:
                if f"uses: {action}" not in body:
                    continue
                # A job-level `permissions:` block replaces the workflow-level
                # one entirely rather than merging with it (GitHub Actions'
                # own semantics) -- so a job that declares one must itself
                # carry pages: write; only a job with no block of its own
                # inherits the workflow-level default.
                has_job_permissions = "permissions:" in body
                job_pages_write = "pages: write" in body
                effective = job_pages_write if has_job_permissions else top_level_pages_write
                assert effective, (
                    f"job {job_name!r} runs {action!r} but its effective "
                    "permissions lack pages: write"
                )
