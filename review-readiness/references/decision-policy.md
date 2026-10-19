# Decision Policy

There are two separate decisions:
- **Review Readiness**: can a human review this PR productively *now*?
- **Merge Recommendation**: what GitHub review action fits the evidence?

The **hard gates** are evaluated first. Scores inform the explanation but never override a gate.

---

## 1. Issue taxonomy

| Category | Use when | Typical owner |
|---|---|---|
| `CONTEXT_GAP` | Intent, requirements, design rationale, or scope explanation is missing, unclear, or contradicted by the diff | AUTHOR |
| `CODE_DEFECT` | Correctness, security, data-integrity or contract defect | AUTHOR |
| `VERIFICATION_GAP` | Tests, CI evidence or execution results are insufficient for the risk, including required checks that are pending or skipped | AUTHOR (missing tests or results) or REVIEWER (needs to run or trigger something) |
| `DESIGN_RISK` | Architecture, maintainability, deployment, operational or prompt-injection concern; not a demonstrated defect | BOTH |
| `REVIEW_INCOMPLETE` | The reviewer or AI hasn't inspected enough to judge, e.g. uninspected risk paths or unreadable files | REVIEWER |

### Required fields per issue
`ID · Category · Severity · Status · Evidence (with source tag) · Confidence (High/Med/Low) · Owner (AUTHOR | REVIEWER | BOTH) · Next action`

**Status values:**
- `CONFIRMED` or `HYPOTHESIS` for new issues.
- In recheck, a previous issue's status is `RESOLVED`, `STILL_OPEN` or `CANNOT_VERIFY`.
- Keep RESOLVED issues in `latest.json`; drop them from the main table except in the Δ block.

**IDs** use a category prefix whatever the status: `C` context, `D` defect, `V` verification, `R` design risk, `I` incomplete review. A defect hypothesis is still `D#`.

### Severity
- **BLOCKER**: must be resolved before merge (data loss, security hole, broken contract, failing required gate, crash on a main path).
- **MAJOR**: should be resolved or explicitly accepted before merge.
- **MINOR**: nice to fix; not decision-relevant.

For a HYPOTHESIS, give the severity *if confirmed* and write it as `BLOCKER (if confirmed)`. "High-impact hypothesis" means a hypothesis that would be MAJOR or BLOCKER if confirmed.

Adjustments:
- **Pre-existing** defects (present on base, not made worse or newly reachable by this PR) are labeled `PRE-EXISTING`, capped at MINOR, and never gate the PR.
- **Latent** defects (CONFIRMED in code, but unreachable from current callers): set severity by the realistic reachable impact and note "latent".

### CONFIRMED vs HYPOTHESIS
- **CODE_DEFECT CONFIRMED** means you read the code (or ran it) and can state the input or state, the path through `file:line`, and the wrong outcome.
  - If the scenario depends on runtime conditions you could not observe (deployment topology, ingress config, real concurrency), it stays a HYPOTHESIS. The one exception is a precondition the PR itself documents as normal. For example, if the author says "Stripe redelivers events", redelivery counts as established.
- **Gap CONFIRMED** (CONTEXT, VERIFICATION, REVIEW_INCOMPLETE) means the absence was verified. For example, the body is empty, or no test file touches the path.
- **HYPOTHESIS** is plausible but not demonstrated. A HYPOTHESIS can never trigger REQUEST_CHANGES on its own, but a high-impact hypothesis can force COMMENT or CONTINUE_REVIEW.

---

## 2. Hard gates (evaluate in order; record each as PASS / FAIL / UNKNOWN)

**Core principle:** FAIL needs an observed failure or an explicit violation. Not-yet-available evidence (pending, skipped, unreadable) is **UNKNOWN**, never FAIL, because missing evidence is not bad code. Every UNKNOWN on a gate also becomes a VERIFICATION_GAP or REVIEW_INCOMPLETE issue, with an owner who can resolve it.

| Gate | PASS | FAIL | UNKNOWN |
|---|---|---|---|
| G1 Confirmed blocking defect | No CONFIRMED BLOCKER defect *in the inspected scope*. Always write the scope: `PASS (scope N/M)` | ≥1 CONFIRMED CODE_DEFECT with severity BLOCKER | Use UNKNOWN when there are 0 inspected risk paths |
| G2 Required checks | All required checks completed successfully | A required check (from branch protection or project rules) **completed with failure/error** on head | The required set is unreadable (403) and nothing failed, **or** a required check is pending, skipped, cancelled, or never ran on head |
| G3 Security or project gate | No mandated gate exists (files absent / 404 = "none declared"), or every mandated gate is met | A mandated gate is **explicitly violated** by the PR as it stands. Examples: CONTRIBUTING requires tests for bug fixes and the PR adds none; a required security scan *reports findings*; CODEOWNERS approval is impossible because the owner is the author | The gate's evidence is pending, skipped or unreadable (403) |
| G4 Coverage | Every path in M was inspected | Fewer than all of M inspected (**always FAIL in triage**) | Not used |
| G5 Critical verification | Each critical behavior on a top-risk path has a test that targets it (TEST_SOURCE) **and** a CI_GITHUB or EXECUTED pass of a job that runs that test | Green CI exists but no test targets the behavior, or the head was never tested in CI or locally here | A targeting test exists and CI is green, but you can't establish that the job runs it |

How to read the gates in specific cases:
- **"Required checks" from project rules.** CONTRIBUTING statements like "PRs labeled X need green Y" make Y a required check under G2. Don't double-count them under G3. G3 covers rules that are not CI checks.
- **What M (the risk paths) is.** M is the top risk paths you selected in Step 2: 3–5, or fewer for small PRs, minimum 1.
  - Many near-identical files (e.g. 22 handlers) count as **one** path; record which were sampled.
  - Reading only part of a path counts as **not inspected**.
  - Unchanged callers you couldn't read are not in M. Log them as a MINOR `REVIEW_INCOMPLETE`.
- **Unrelated failures.** A failing check that is demonstrably unrelated (e.g. an infra flake with the same failure on base) is recorded as UNKNOWN with that evidence. It is not FAIL.

---

## 3. Merge Recommendation (first matching rule wins)

1. **REQUEST_CHANGES** if G1 FAIL, G2 FAIL, or G3 FAIL.
   - Name the evidence and give actionable remediation.
   - This applies even if every score is high. Good documentation never cancels a confirmed defect.
2. **COMMENT** if rule 1 doesn't apply and either holds:
   - ≥1 AUTHOR-owned `CONTEXT_GAP` or `VERIFICATION_GAP` of severity MAJOR or higher, or
   - a high-impact HYPOTHESIS that only the author can answer (intent, deployment or config facts).
   - This includes high-risk PRs whose missing piece is author-supplied evidence (test results, migration plan, rollback notes) and required checks the author must make run (pending or skipped on head).
3. **CONTINUE_REVIEW** if none of the above, and any of these is true:
   - G4 or G5 is not PASS
   - a MAJOR+ `REVIEW_INCOMPLETE` remains
   - a high-impact HYPOTHESIS the reviewer can settle remains

   The owner is REVIEWER, and the next action is concrete: which paths to read and what to run or trigger. In triage this is the ceiling when no author gaps exist.
4. **APPROVE_CANDIDATE** only if **all** of these hold:
   - Mode is `full`, or `recheck` at full depth (every risk path in M re-read at the new head).
   - G1, G4 and G5 are PASS. G2 and G3 are PASS, or UNKNOWN only because the rules are unreadable (403), with Operational Risk ≤ 3 and all visible checks green.
   - No open BLOCKER or MAJOR issues remain; MINORs are listed.
   - Remaining risk is acceptable for the category. When Operational Risk ≥ 7, also require Verification Confidence ≥ 7 and an explicit rollback or mitigation story (author-supplied or in code).
   - If any condition is unmet, fall back to rule 3.
   - This is a *candidate*: the human decides and clicks Approve. The skill never approves.

### Tie-breaking: COMMENT vs CONTINUE_REVIEW
Ask *who must act next*:
- If the author must supply something before review can progress, choose COMMENT.
- If the reviewer must investigate further and the author has already supplied what's reasonable, choose CONTINUE_REVIEW.
- If both, choose COMMENT and list the reviewer's open items as well.

---

## 4. Review Readiness

- **NEEDS_AUTHOR_INPUT** if any of these hold:
  - The PR is a draft.
  - Rule 1 fired: the author must fix something, whatever the cause.
  - There is an AUTHOR-owned MAJOR+ CONTEXT_GAP: intent unclear enough that a reviewer can't judge correctness, or the description contradicts the diff on a risk path.
  - There is an AUTHOR-owned MAJOR+ VERIFICATION_GAP on a risk path. Judge each risk path separately: a path that changes behavior with no evidence for that path counts, even when unrelated CI is green.
- **READY_FOR_REVIEW** otherwise, even when the merge recommendation is CONTINUE_REVIEW. Reviewer-side incompleteness does not make a PR "not ready".

Readiness and merge recommendation are independent. For example:
- NEEDS_AUTHOR_INPUT + REQUEST_CHANGES: a well-prepared PR with a confirmed bug. Say explicitly that preparation was good (high Author Readiness) and the blocker is the defect.
- READY_FOR_REVIEW + CONTINUE_REVIEW: the author's work is done and the reviewer's isn't.
- NEEDS_AUTHOR_INPUT + COMMENT: the typical "1,800 lines, empty description" PR.

---

## 5. Next responsible owner (who acts *first*)

- REQUEST_CHANGES → **AUTHOR**
- COMMENT → **AUTHOR**. Use **BOTH** only when MAJOR+ reviewer work doesn't depend on the author's answers and should proceed in parallel. Triage's inherent G4 FAIL alone doesn't make it BOTH.
- CONTINUE_REVIEW → **REVIEWER** (this includes "ask a maintainer to trigger CI")
- APPROVE_CANDIDATE → **REVIEWER**, for the final human sign-off

---

## 6. "What would change the decision"

List the 1–3 smallest pieces of evidence or fixes that would move the recommendation. Project each one on its own, assuming everything else is unchanged, and name the rule that would then apply:
- "A green `integration` run on head (clears V1) → rule 2 no longer fires → CONTINUE_REVIEW."
- "Fixing `src/ledger.ts:142` (double-apply on retry) plus a regression test clears G1. V2 would still keep it at COMMENT."

---

## 7. Acceptance mapping (sanity reference)

| Scenario | Expected |
|---|---|
| A: missing context and verification, no defect | COMMENT / NEEDS_AUTHOR_INPUT / owner AUTHOR |
| B: well documented, confirmed blocking bug | REQUEST_CHANGES / NEEDS_AUTHOR_INPUT |
| C: low risk, clear, CI green, full review done | APPROVE_CANDIDATE / READY_FOR_REVIEW |
| D: high-risk transactions/security, key paths unverified, required checks pending or skipped | COMMENT if author evidence is missing; CONTINUE_REVIEW if only reviewer work is pending. **Not** REQUEST_CHANGES unless something actually failed or a defect is confirmed |
| E: AI inspected a small fraction, no bugs found | Change Quality NOT_ASSESSED; CONTINUE_REVIEW, or COMMENT if author gaps also exist (rule 2 precedes rule 3); never APPROVE_CANDIDATE |
| F: recheck after the fix and new evidence | Previous findings → RESOLVED/STILL_OPEN with evidence; recommendation re-derived with the reason for the change |
