# facts Specification

## Purpose

A fact is a standalone claim that is checked-true, not yet checked, or retracted. It is deliberately minimal, holding a claim, a status, and a revision history, and none of a task's labels, links, hierarchy, or claiming. Agents record a fact with proof so a later session can retrieve it instead of re-deriving it.

## Requirements

### Requirement: Fact status has no transition table
A fact's `status` SHALL be `unverified`, `verified`, or `retracted`. `verify`, `unverify`, `revise`, and `retract` SHALL each be valid from any status.

#### Scenario: Verify a retracted fact
- **WHEN** `corvee fact verify FACT-1 --proof "..."` runs on a `retracted` fact
- **THEN** the fact becomes `verified`

### Requirement: `fact add` creates an unverified fact
`corvee fact add <claim> [--proof <text>] [--global]` SHALL create a fact with status `unverified` and write a `created` event. With `--proof` it SHALL also verify the fact in the same call, writing `created` then `verified` events.

#### Scenario: Add with proof
- **WHEN** `corvee fact add "x is true" --proof "ran test y"` runs
- **THEN** the fact is `verified` and has a `created` and a `verified` event

#### Scenario: Add without proof
- **WHEN** `corvee fact add "x is true"` runs
- **THEN** the fact is `unverified` with one `created` event

### Requirement: `fact verify` records proof and refreshes on repeat
`corvee fact verify <id> --proof <text>` SHALL set `status` to `verified`, `verified_at` to now, `verified_by` to the actor, and `proof` to the text, and write a `verified` event. Verifying an already-verified fact SHALL succeed and refresh the proof and timestamp.

#### Scenario: Re-verify
- **WHEN** `corvee fact verify FACT-1 --proof "rechecked"` runs on a `verified` fact
- **THEN** `verified_at` advances and `proof` is `rechecked`

### Requirement: `fact unverify` withdraws verification
`corvee fact unverify <id> [--note <text>]` SHALL set `status` to `unverified`, clear `verified_at`, `verified_by`, and `proof`, and write an `unverified` event carrying `--note` when given.

#### Scenario: Unverify with a reason
- **WHEN** `corvee fact unverify FACT-1 --note "source changed"` runs
- **THEN** the fact is `unverified`, its proof is cleared, and the event's `note` is `source changed`

### Requirement: `fact revise` changes the claim
`corvee fact revise <id> <new-claim>` with text identical to the current claim SHALL be a no-op success with no event and no status change. Different text SHALL change `claim` and write a `revised` event holding the old and new text.

#### Scenario: Identical revision
- **WHEN** `corvee fact revise FACT-1 "same text"` runs and the claim is already `same text`
- **THEN** no event is written

### Requirement: Revising a verified or retracted fact resets it
Revising a `verified` or `retracted` fact to different text SHALL also reset it to `unverified` and write a second event of kind `unverified`. The old proof says nothing about new text, and revising a retracted fact signals it should re-enter the normal flow. Two events keep a scan for `verified` and `unverified` kinds correct without special-casing `revised`.

#### Scenario: Revise a verified fact
- **WHEN** `corvee fact revise FACT-1 "new text"` runs on a `verified` fact
- **THEN** the fact is `unverified` and has a `revised` event followed by an `unverified` event

### Requirement: `fact retract` withdraws a fact
`corvee fact retract <id> [--reason <text>]` SHALL set `status` to `retracted` and write a `retracted` event carrying `--reason` when given. A retracted fact SHALL drop out of the default `fact list` and remain recoverable through `verify`, `unverify`, and `revise`.

#### Scenario: Retract hides from default list
- **WHEN** `corvee fact retract FACT-1` runs, then `corvee fact list`
- **THEN** `FACT-1` is not listed, and `corvee fact list --all` lists it

### Requirement: `fact delete` removes a retracted fact for good
`corvee fact delete <id>` SHALL permanently remove a fact and its entire `fact_events` history, and SHALL work only on a `retracted` fact. On any other status it SHALL fail with a guard violation (exit 5, `fact_not_retracted`) naming `corvee fact retract`. It SHALL return the fact's last state before deletion.

Requiring retraction first means nothing is hard-removed without first passing through a visible, undoable state.

#### Scenario: Delete an unverified fact
- **WHEN** `corvee fact delete FACT-1` runs on an `unverified` fact
- **THEN** the exit code is 5 with error code `fact_not_retracted`

#### Scenario: Delete a retracted fact
- **WHEN** `corvee fact delete FACT-1` runs on a `retracted` fact
- **THEN** the fact and its events no longer exist and the output holds its last state

### Requirement: Verification columns reflect current state
`verified_at`, `verified_by`, and `proof` on `facts` SHALL denormalize the current verification, and SHALL all clear whenever status leaves `verified`, whether by `unverify`, a claim-changing `revise`, or `retract`. `--verified-by <actor>` on `fact list` and `fact search` SHALL filter on `verified_by`.

#### Scenario: Retract clears verification
- **WHEN** a `verified` fact is retracted
- **THEN** `verified_at`, `verified_by`, and `proof` are all null

### Requirement: Blank fact inputs are rejected
`fact add`'s claim, `fact revise`'s new claim, and `fact verify --proof` SHALL reject an empty or whitespace-only value with a usage error (exit 2).

#### Scenario: Whitespace claim
- **WHEN** `corvee fact add "   "` runs
- **THEN** the exit code is 2

### Requirement: `fact list` defaults to non-retracted facts
`corvee fact list` (alias `ls`) SHALL exclude `retracted` facts by default and include them with `--all`. `unverified` facts SHALL be included by default. It SHALL accept `--status`, `--since <duration>`, `--verified-by`, `--stale`, `--scope`, `--limit`, and `--fields`.

#### Scenario: Unverified is listed
- **WHEN** one `unverified` and one `retracted` fact exist and `corvee fact list` runs
- **THEN** only the `unverified` fact is listed

### Requirement: Facts sort newest first
`fact list` and `fact search` SHALL sort by `created_at` descending, breaking ties on `id` descending. `created_at` stays comparable across the merged local and global results, and `id` does not.

#### Scenario: Newest first
- **WHEN** two facts are created in sequence and `corvee fact list` runs
- **THEN** the later fact is listed first

### Requirement: `fact search` matches claims
`corvee fact search <text>` SHALL return facts whose `claim` contains `<text>`, case-insensitive, with `%` and `_` in the text matching literally. `--include-proof` SHALL also match `proof` text, `--all` SHALL include retracted facts, and `--verified-by` SHALL filter by verifier.

#### Scenario: Literal percent
- **WHEN** a fact claims `100% done` and `corvee fact search "100%"` runs
- **THEN** that fact is returned and a fact claiming `1000 done` is not

#### Scenario: Proof match
- **WHEN** a fact's proof is `PR #123` and `corvee fact search "#123" --include-proof` runs
- **THEN** that fact is returned

### Requirement: `fact list --stale` finds old verifications
`corvee fact list --stale [<duration>]` SHALL match facts where `verified_at` is not null and older than the cutoff, with the same default duration and parsing as `task list --stale`. Unverified and retracted facts SHALL never match.

#### Scenario: Old verification
- **WHEN** a fact was verified 40 days ago and `corvee fact list --stale 30d` runs
- **THEN** the fact is listed

### Requirement: `fact show` returns the full history
`corvee fact show <id> [<id> ...]` SHALL return claim, status, current proof, and the full revision timeline under `events`, with no trimming flags, plus a `referenced` key (see `record-references`).

#### Scenario: Revision timeline
- **WHEN** a fact was added, verified, and revised, and `corvee fact show FACT-1 -o json` runs
- **THEN** `events` lists the `created`, `verified`, `revised`, and `unverified` events

### Requirement: Fact field projection
`--fields` on `fact list` and `fact search` SHALL accept only `id`, `claim`, `status`, `verified_at`, `verified_by`, `proof`, `created_at`, `updated_at`, and `scope`, and SHALL reject any other name with a usage error (exit 2) listing the valid names.

#### Scenario: Unknown field
- **WHEN** `corvee fact list --fields id,bogus` runs
- **THEN** the exit code is 2 and the message lists the valid fields
