# Deep-read checklist (Step 3, full mode; once per risk path)

## Read
- The changed function(s) **in full** at head:
  - `git show <head_sha>:<path>` if the commit is in the local clone
  - otherwise `gh api repos/<repo>/contents/<path>?ref=<head_sha>` (GET)
- One level of callers and callees.
- Read independent files in the same turn.

A path counts as `inspected: true` **only** if you read all of it. A partial read is `false`, and the note says what is missing.

## Check
- input validation and error paths
- state transitions and atomicity
- idempotency, retries and concurrency
- contract and backward compatibility (signatures, return values, schema, API responses)
- security: authn/authz, injection, secrets, trusting client-supplied headers
- data integrity: writes, deletes, migrations and their reversibility

## Map tests to behaviors
For each critical behavior on the path:
- **Which test targets it?** Give its file:line, or "none".
- **Does it exercise the real path?** A test that seeds state by hand, or mocks out the thing under test, does not.
- **Does CI run it on head?** Use the gate semantics from the evidence checklist.

## Write findings
- **CODE_DEFECT, CONFIRMED.** Requires a `file:line` and a scenario: input or state → path → wrong result. You must have read the code that proves it.
- **HYPOTHESIS.** Plausible, but the scenario depends on something you couldn't observe (runtime config, ingress, deploy order). Write that dependency into `confirm_or_refute`.
- **Severity.** BLOCKER is only for a defect that must be fixed before merge, or a gate that really FAILed. Missing or pending evidence is at most MAJOR.
