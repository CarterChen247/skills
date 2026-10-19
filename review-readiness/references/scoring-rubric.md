# Scoring Rubric

The four dimensions are scored **independently**. Never compute an overall score or average. Scores are decision aids, not calibrated probabilities. Every sub-score must cite observable evidence: a quote, a `file:line`, a check name, or an explicit absence.

## Evidence sources (tag every fact)

| Tag | Meaning | Counts as proof that tests ran? |
|---|---|---|
| `EXECUTED` | Run in this session by the reviewer or AI, with output observed | Yes |
| `CI_GITHUB` | Check-run status retrieved from GitHub (`gh pr checks`) | Yes, only for what that check covers |
| `TEST_SOURCE` | Test code exists (in the diff or repo), but it was not observed running | No |
| `AUTHOR_REPORTED` | Claimed in the PR body or comments with no linked artifact | No; partial credit only as a *claim* |
| `MISSING` | Not available | No |

A CI check that passed proves only what that job executes. If you can't tell whether CI runs the relevant tests, say so.

## Score bounds and special values

- Each dimension's raw sub-score sum maps to the 1–10 scale. Sums of 0 are floored to 1.
- `UNKNOWN` for a *sub-criterion* means there is no evidence either way. Score it 0 and mark it `UNKNOWN`; do not describe it as a failure. If UNKNOWN sub-criteria carry ≥ 40% of a dimension's weight, append `(low evidence)` to the score.
- A sub-criterion that is partly established (e.g. tests exist but were not read) gets the points the established part supports. Count only the unestablished remainder toward the 40% rule.
- Change Quality may be `NOT_ASSESSED` as a whole (see below). The other three are always scored, with `(low evidence)` where needed.
- Don't manufacture precision. Report integers and give no confidence intervals.

---

## A. Author Readiness (1–10)

Scores the **preparation of this PR**, not the person. **Count only what the author supplied or linked**: the PR body, the author's own comments, linked issues or docs, and commit messages. Explanations the AI reconstructed from the diff earn **0 points**.

| Sub-criterion | Pts | 0 | Half | Full |
|---|---|---|---|---|
| Clear intent and requirements | 0–2 | No "why", or the title only | Why stated, but requirements or acceptance are vague | Problem, goal and acceptance criteria are clear or linked |
| Scope and important data flows explained | 0–2 | No description of what changed | Lists changes, but not the key flows or affected areas | Explains the main flow or state changes and what is intentionally unchanged |
| Verification summary | 0–3 | Nothing | 1: "tested locally" with no detail · 2: names the tests or commands run | 3: commands, results and scenarios incl. edge cases, or links to CI/screenshots |
| Known risks and reviewer guidance | 0–2 | None | Mentions risks *or* review focus | Both risks/rollback notes and where to focus |
| Focused, reviewable scope | 0–1 | Mixed concerns, or large with no structure | — | Single concern, *or* large but split into logical commits or with a reading order |

Raw max = 10, so the score is the raw sum (minimum 1).

The size rule is about focus, not lines: a 2,000-line mechanical rename with a clear note can earn the point. A small PR that mixes two unrelated concerns (e.g. a concurrency fix plus an auth change) earns 0, unless the author explains why they ship together.

**How to score specific author content:**
- **Contradicted claims earn nothing.** If observed evidence contradicts an author claim, that claim earns 0 and gets a CONTEXT_GAP or VERIFICATION_GAP. Examples: "tests for every handler" when 4 are missing; "duplicate skipped" when the test only seeds a row by hand. Accurate-but-incomplete claims keep partial credit.
- **Unreadable links get at most half credit.** A link to an external doc you can't read (non-GitHub, or not allowed under hard rule 5) is worth at most half credit for the criterion it supports. Mark the checklist item UNKNOWN, not PASS.
- **Superseded bodies.** In recheck, if the body is stale but the author corrected it in a later comment, score the latest author-supplied state and log the stale body as a MINOR CONTEXT_GAP.
- **Verification-summary levels:** "tested locally" = 1; naming the suite or command ("ran the integration suite, all green") = 2; commands **plus** results, scenarios, or links to runs = 3.

## B. Change Quality (1–10 or NOT_ASSESSED)

**Return `NOT_ASSESSED`** when any of these is true:
- The mode is triage and not every top-risk path was read in full.
- The coverage log shows fewer than all high-risk paths inspected.
- The diff could not be retrieved, or key files could not be read at the head revision.

When `NOT_ASSESSED`, still list spot-check observations as HYPOTHESES. "No bugs found" never raises this score by itself; points require positive evidence that the inspected logic handles its cases.

| Sub-criterion | Pts | Guidance |
|---|---|---|
| Functional correctness | 0–3 | 3: logic verified for main + edge paths you read · 2: main path OK, minor unclear edges · 1: plausible but untraced branches · 0: confirmed defect |
| Security and data integrity | 0–2 | 2: inputs validated, authz preserved, writes atomic or idempotent where needed · 1: unclear spots · 0: confirmed vuln or data-loss path |
| API contracts and state consistency | 0–2 | 2: compatible or versioned, migrations reversible, state transitions coherent · 1: undocumented contract change · 0: breaking change without handling |
| Architecture and maintainability | 0–2 | 2: fits existing patterns · 1: duplication or layering smell · 0: structural problem that will cost later |
| Complexity and regression concerns | 0–1 | 1: complexity proportional, regression surface understood · 0: high regression surface, not contained |

A **confirmed BLOCKER defect caps Change Quality at 3**, regardless of the other sub-scores.

## C. Verification Confidence (1–10)

How much **observed evidence** shows that the important behavior works? Do not double-count Author Readiness: a well-written claim is not evidence.

| Sub-criterion | Pts | Guidance |
|---|---|---|
| CI and automated test evidence | 0–3 | 3: required checks green (CI_GITHUB) and they run the relevant suites · 2: green but relevance unclear · 1: pending, partial, or only AUTHOR_REPORTED · 0: failing or none |
| Critical behavior and edge-case coverage | 0–3 | 3: tests target the risky paths incl. failure/edge cases · 2: happy path tested · 1: tests exist but miss the risky path · 0: none |
| Integration and contract validation | 0–2 | 2: integration/contract/migration tests or equivalent evidence · 1: partial · 0: none where needed · NOT_APPLICABLE → award 2 and say so |
| Manual or UI verification | 0–1 | 1: screenshots, recordings or manual steps provided where UI or ops behavior changed · NOT_APPLICABLE → award 1 and say so |
| Evidence traceability | 0–1 | 1: claims link to runs, logs or commands a reviewer can reproduce · 0: unlinked claims |

`TEST_SOURCE` can earn points under *coverage* (the tests exist and target the path). It earns points under *CI* only if a CI_GITHUB check plausibly runs them.

**Relevance of CI:**
- A green check counts as *relevant* (3 pts) only when you can see that it runs the suite containing the targeting tests: a workflow file or job log you read, or a check named for that suite.
- If you can't see that, it is "relevance unclear" (2 pts).
- If the PR adds behavior but no test targets it, green CI is worth at most 1.
- If CI skipped testing the head (e.g. "regular PR; skipping tests"), green checks are worth 0 for this criterion, even with a "tests passed" label. Read what the gate actually asserts.

**Manual / ops verification:** this applies when the change alters something a human or operator would observe: UI, emitted webhooks or emails, deploy steps, auth behavior visible to callers. Pure internal logic with no observable surface is NOT_APPLICABLE.

## D. Operational Risk (1–10, HIGHER = RISKIER)

This scores the *potential consequence if the change is wrong*, not how likely it is to be wrong, and **not line count**.

Rate each factor Low (0) / Medium (1) / High (2):

| Factor | Examples of High |
|---|---|
| Impact severity | money movement, auth, data loss, legal/PII |
| Blast radius | all users/tenants, shared library, core path |
| Reversibility | irreversible migration (column/table drop), data rewrite, *new or changed* external side effects at scale (emails, payments, partner webhooks). An unchanged existing side-effect path is Medium at most |
| Security implications | new input surfaces, permission changes, secret handling |
| Data integrity | writes or deletes, concurrency, idempotency |
| Cross-system dependencies | API/schema contracts with other services or clients |
| Deployment and recovery | needs coordinated deploy, no feature flag, no rollback path |

Map the sum (0–14) to the 1–10 scale: `0→1, 1–2→2, 3→3, 4→4, 5–6→5, 7→6, 8–9→7, 10–11→8, 12–13→9, 14→10`.

Then apply these overrides:
- A docs, tests or comments-only change is at most 2.
- A schema migration that can't be reversed, or code that moves money, is at least 6.

Mitigations (a feature flag or staged rollout, reversible migrations, idempotency keys) **reduce the relevant factor** and must be cited.

## How the scores interact (they don't average)

- Low Author Readiness with high Change Quality means the code is fine but the context is poor, which is a COMMENT-type situation.
- High Author Readiness with a confirmed defect means REQUEST_CHANGES; the good documentation does not offset the defect.
- High Operational Risk raises the evidence bar for APPROVE_CANDIDATE (see decision-policy.md) but never decides the outcome by itself.
