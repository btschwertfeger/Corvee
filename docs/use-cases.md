# Use cases

corvee holds two independent stores. Tasks are units of work with a state,
a priority, and an event history. Facts are claims you checked once and may
need to check again. Each fact carries the proof that established it.
Neither store is tied to software.

Any directory you return to can be a corvee project, and the same
claim/unclaim protocol that keeps two coding agents off the same task works
between two people, or a person and an agent.

## Software work

The software case is one repository's backlog, shared by every session and
every worker in it. The [Quickstart](quickstart.md) covers this loop in
full.

```bash
cd ~/src/my-project
corvee init
corvee task add "Fix the flaky auth test" --type bug --description "repro: make test twice"
corvee task start TASK-1
corvee task comment TASK-1 "root cause: the retry loop has no backoff"
corvee task update TASK-1 --state done
```

Each agent session identifies itself, so two sessions never hold the same
task at once:

```bash
corvee --actor agent:claude --session-id session-42 task mine --json
corvee --actor agent:claude --session-id session-42 task start TASK-14 --json
```

## Research

A reading queue is a task list, and open questions are tasks. What you
established from a source becomes a fact, and the source is its proof.

```bash
corvee task add "Read the 2024 survey on X" --description "for the related-work section" --priority high
corvee task add "Find the error bound for method Y" --description "needed for section 3.2"
corvee fact add "The survey reports a 12% error rate at n=1000" \
  --proof "Table 4, p. 11, https://example.org/survey.pdf"
```

A later session runs `corvee fact search "error rate"` and gets the claim,
its proof, and the date, instead of re-reading the paper or trusting a
summary of it.

## Writing and editing

Chapters, revisions, and reviews map onto tasks and subtasks. Editorial
decisions are facts, with the style guide or source you checked as proof.

```bash
corvee task add "Revise chapter 4" --description "tighten the argument, drop the digression" --priority high
corvee task add "Verify every citation resolves" --description "every URL and DOI, against the publisher's page" --parent TASK-1
corvee task label TASK-1 --add editorial
corvee fact add "House style uses the Oxford comma" --proof "style guide, section 2.1"
```

## Operations and home labs

A recurring chore or a machine-wide fact belongs in the shared database,
so every checkout sees it:

```bash
corvee task add "Renew the CA cert" --description "expires yearly" --global
corvee fact add "The CA bundle rotates every January" --global \
  --proof "openssl x509 -in ca.pem -noout -enddate"
```

`corvee task list` merges both databases by default, so the global chore
shows up wherever you are.

## Personal tracking

With no `--actor` flag the identity defaults to `human:$USER`, and the
default table output reads fine in a terminal. Nothing here requires an
agent. Shell completion covers subcommands, flags, and real
`TASK-<n>`/`FACT-<n>` ids:

```bash
eval "$(corvee completion bash)"   # or zsh / fish
corvee task add "Renew passport" --description "appointment needed before it lapses" --priority high
corvee task list --fields id,title,state
```

A job search, a move, or any long-running project with a state and a
history fits the same shape.

## Sharing one backlog

Claims work between any two actors. A person runs `corvee task claims` to
see what an agent currently holds, and `corvee task assign` to route work
without claiming it on someone else's behalf:

```bash
corvee --actor human:alice task claims --json
corvee --actor human:alice task assign TASK-14 --to agent:claude
```

## Scope limits

Use corvee for work that spans sessions, has a state worth querying, and
lives on one machine. It is not a hosted issue tracker, so cross-machine
sharing, a web UI, notifications, and scheduling all fall outside it. See
[What it is not](index.md#what-it-is-not) for the full list.
