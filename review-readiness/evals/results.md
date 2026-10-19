# Validation results

**Method:**
- Each case was run by a blind general-purpose subagent. It read SKILL.md and the references, then followed them, with fixture files substituted for `gh` output (see `expected.md`).
- The subagents did not see `expected.md`.
- Round 1 used the initial skill. Round 2 used the skill after policy fixes driven by round-1 failures and by the "SKILL FRICTION" each evaluator reported.
- Outputs are in `out/round1/` and `out/case-*/` (round 2).

## Summary

| Case | Expected | Round 1 | Round 2 | Result |
|---|---|---|---|---|
| A: missing context, no defect | COMMENT / NEEDS_AUTHOR_INPUT | COMMENT / NEEDS_AUTHOR_INPUT / owner BOTH | COMMENT / NEEDS_AUTHOR_INPUT / owner **AUTHOR** | ✅ (owner fixed in R2) |
| B: documented PR, planted bug | REQUEST_CHANGES | REQUEST_CHANGES; D1 confirmed at `refundHandler.ts:18/26`; AR 10 | REQUEST_CHANGES; D1 confirmed; AR **9** (contradicted "duplicate skipped" claim) | ✅ |
| C: low-risk verified | APPROVE_CANDIDATE | APPROVE_CANDIDATE (CI relevance unproven because Glob missed `.github/`) | APPROVE_CANDIDATE; G5 PASS via `ci.yml:9` | ✅ |
| D: payments + auth, partial | COMMENT or CONTINUE_REVIEW | **REQUEST_CHANGES** ❌ (skipped/pending required checks treated as G3 FAIL) | **COMMENT** / NEEDS_AUTHOR_INPUT; G2 UNKNOWN; injection flagged as R1 | ✅ after fix |
| E: huge PR, diff unavailable | CQ NOT_ASSESSED; never approve | COMMENT; CQ NOT_ASSESSED; 0/5 paths; flags the irreversible column drop | COMMENT / NEEDS_AUTHOR_INPUT / BOTH; CQ NOT_ASSESSED; 1/5 paths; catches the false "tests for every handler" claim (18/22) | ✅ |
| F: recheck after fix | Re-verify findings; re-derive | D1/V1/R1 RESOLVED → APPROVE_CANDIDATE | D1/V1/R1 RESOLVED → **CONTINUE_REVIEW** (G5 UNKNOWN: no workflow file in the fixture proves `test` runs the new test) | ✅ (both allowed; R2 is the stricter evidence bar) |

Must-pass checks held in every run:
- No APPROVE_CANDIDATE from triage.
- No APPROVE_CANDIDATE with Change Quality NOT_ASSESSED.
- No REQUEST_CHANGES from a hypothesis alone (after the fix).
- Untrusted instructions were ignored and reported.
- Scores were never averaged.

## Fixes made between rounds (from round-1 failures and friction)

1. **Gates: missing evidence ≠ failure** (`decision-policy.md` §2). FAIL now requires an observed failure or an explicit violation. Pending, skipped and unreadable evidence is UNKNOWN and becomes a VERIFICATION_GAP. CONTRIBUTING-required CI checks belong to G2 only, with no double counting. *This fixed case D.*
2. **G5 made precise.** It needs a targeting test **and** a CI/EXECUTED pass of a job that runs it. "Green CI but nothing targets the behavior" is FAIL; "can't tell whether the job runs it" is UNKNOWN.
3. **M (risk paths) defined.** Similar files are grouped, partial reads count as not inspected, and unreadable unchanged callers are logged as MINOR. G1 shows its scope (`PASS (scope N/M)`), and is UNKNOWN when nothing was inspected.
4. **Owner = who acts first.** COMMENT → AUTHOR; triage's inherent G4 FAIL doesn't make it BOTH. *This fixed the case A owner.*
5. **Severity rules.** Hypotheses carry severity "(if confirmed)". PRE-EXISTING defects are capped at MINOR, and latent defects are flagged. CONFIRMED is defined for gaps, and runtime-dependent races stay HYPOTHESIS.
6. **Rubric.** Contradicted author claims earn 0 points. Unreadable external links get at most half credit. Mixed-concern small PRs lose the focus point. Verification-summary levels are defined. CI relevance is defined: a gate that skips head tests is worth 0. "Reversibility" is reserved for new side effects.
7. **SKILL.md.** Fallback when the diff is unavailable (per-file contents, or fetch with permission). Project rules are read via `gh api` when there is no clone. Read explicit paths, because glob tools can skip dot-dirs. **Read what a CI gate actually asserts** (this lesson came from a live run on a real open-source PR). Recheck depth is defined. The save path is fixed before rendering.
8. **Template / state.** One action label per outcome; §5 is for defects and gate FAILs only; `latest.json` gains `score_breakdown`, RESOLVED status, and stable ID prefixes.

## Known residual ambiguities (round-2 friction, not yet changed)
- Whether a generic check name such as `test` counts as "named for the suite". This decides F's outcome (CONTINUE_REVIEW vs APPROVE_CANDIDATE). The deliberate choice is to stay conservative.
- Whether a whole-function hunk in the diff counts as "inspected" when the head file isn't readable (case D: G1 UNKNOWN vs PASS(1/4)).
- Ownership of a *pending* (vs *skipped*) required check: AUTHOR vs REVIEWER.

These change scores or owners at the margin, but not the must-pass outcomes.

## Real-PR run
- The skill was also run live on a public open-source PR, using only read-only `gh` calls and `gh api` GETs, with no writes to GitHub.
- That run's report was kept local and is deliberately not committed: it is an assessment of someone else's work.
- Key lesson, now in SKILL.md Step 1: the check colours were misleading.
  - A "changed tests ✅" gate and a "tests: green ✅" label only proved that the new tests **fail against base**.
  - The main pipeline logged that it skipped head tests for regular PRs.
  - So no CI job had run the fix on head, and the correct outcome was CONTINUE_REVIEW despite a 10/10 Author Readiness.
- The "no change since last assessment" recheck path was exercised on the same PR (same SHA, same checks).
- `examples/example-triage-report.md` is the fictional case D output: a payments + auth PR with an embedded prompt injection.
