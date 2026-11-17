# Spec Delta

## MODIFIED Requirements

### Requirement: Core commands with one example each
The block SHALL list the commands needed most of the time with one example each, covering `brief`, `task mine`, `task ready`, `task search`, `task list`, `task add`, `task claim`, `task start`, `task update`, `task comment`, `task show`, `task link`, `task claims`, and `task assign`. `brief` and `task mine` SHALL come first and `task search` SHALL precede `task add`, since resuming beats starting something new and checking for an existing task stops duplicate filing.

#### Scenario: Order
- **WHEN** `corvee explain` runs
- **THEN** the `brief` example appears before the `task add` example, and `task search` appears before `task add`

#### Scenario: Brief example names facts
- **WHEN** `corvee explain` runs
- **THEN** the comment on the `brief` example names facts

### Requirement: Facts and scope
The block SHALL show a `fact add` and `fact verify` example and say facts are not linked to tasks by the schema. It SHALL say `--global` on `task add` and `fact add` files into the shared database and is needed only on `add`.

#### Scenario: Global note
- **WHEN** `corvee explain` runs
- **THEN** the text states that `--global` is needed only on `add`

#### Scenario: Verify example
- **WHEN** `corvee explain` runs
- **THEN** the `FACTS` section contains a `corvee fact verify` example

## ADDED Requirements

### Requirement: Facts are consulted before asserting
The `FACTS` section SHALL tell the reader to run `fact search` before asserting or re-deriving something uncertain, to rely only on a `verified` fact, and to treat an `unverified` one as unchecked. It SHALL say `brief` lists the newest facts and `fact search` finds the rest.

The rule repeats the fact discipline in the `init` pointer blocks (`agent-integration`) on purpose, so an agent that never received the pasted block still sees it. The two wordings stay aligned.

#### Scenario: Read-side rule
- **WHEN** `corvee explain` runs
- **THEN** the `FACTS` section tells the reader to check `fact search` before asserting something uncertain and names `brief` as listing the newest facts

### Requirement: Stale facts are re-verified
The `FACTS` section SHALL say `fact list --stale <duration>` shows verified facts whose verification is older than the duration, SHALL show it with a long duration such as `30d`, and SHALL say `fact verify` with fresh proof re-checks one.

The default `4h` window is shorter than most facts live, so the example gives a longer one.

#### Scenario: Stale pointer
- **WHEN** `corvee explain` runs
- **THEN** the `FACTS` section shows `fact list --stale` with a duration of days and mentions re-verifying with `fact verify`
