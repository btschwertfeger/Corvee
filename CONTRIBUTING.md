# Contributing

Requires Python 3.11+ and [Hatch](https://hatch.pypa.io/) (`uv` is used
underneath as the installer).

```bash
hatch run test                  # run the test suite (parallel via pytest-xdist)
hatch run cov                   # run the test suite with coverage
hatch run lint                  # ruff check, via prek
hatch run format                # black, via prek
hatch run typecheck             # ty, via prek
hatch run check                 # every prek hook + test
hatch run mutate                # mutation testing against db/ and guards/,
                                 # opt-in, not part of check/CI
hatch run +py=3.12 test:test    # run the suite against one Python version
                                 # from the test matrix (3.11-3.14)
hatch run docs-serve            # serve the documentation locally
hatch build                     # build sdist + wheel
```

`hatch run check` (or `prek run --all-files` directly) is the quality gate
for any change. Run it before considering a change done.

See [AGENTS.md](AGENTS.md) for the architecture, testing conventions, and
the `corvee` task-tracking workflow this project uses on itself.

## Before you open a PR

Open an issue first and wait for a maintainer to approve it before starting
a pull request. This applies to features and non-trivial fixes. A typo or
other trivial fix can go straight to a PR. Approval keeps effort from being
spent on work that doesn't fit the project's direction. PRs opened without an
approved issue may be closed and asked to go through this process first.
