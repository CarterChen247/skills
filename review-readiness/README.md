# review-readiness

A Claude Code skill for **PR review decision support**. It helps a human reviewer answer these questions:
- Is this PR ready for review?
- What kind of problem is it?
- What should the author provide?
- What should I read myself?
- Which GitHub review action fits, and on what evidence?

It is **not** a line-by-line code reviewer and **not** a PR explainer:
- `/pr-explainer` (Mastra) answers *what changed, why, and how*.
- `/review-readiness` answers *is it ready, what's missing, and who acts next*.

## Install

Clone the repo anywhere, then link (or copy) the skill folder into your personal skills directory:

```bash
git clone <this-repo-url> skills
mkdir -p ~/.claude/skills
ln -s "$(pwd)/skills/review-readiness" ~/.claude/skills/review-readiness
```

- **Symlink** (above): `git pull` updates the skill in place.
- **Copy** instead, if you prefer a fixed version:

  ```bash
  cp -R skills/review-readiness ~/.claude/skills/
  ```
- **One repo only:** put it in that repo's `.claude/skills/review-readiness/` as a project skill.

Claude Code picks up changes live, without a restart. Check that `/review-readiness` appears in the `/` menu.

Requirements:
- the `gh` CLI, authenticated (`gh auth status`), with read access to the repos you review
- `python3`, for the HTML renderer (preinstalled on macOS and most Linux distributions)

## Use

```text
/review-readiness <PR_NUMBER_OR_URL> [--mode triage|full|recheck]
```

| Mode | When to use it | Cost | Can it end in APPROVE_CANDIDATE? |
|---|---|---|---|
| `triage` (default) | First look: decide whether the PR is worth your time and what to ask for | Low: metadata, CI, file map, spot-check of 1–3 risky hunks | **Never** |
| `full` | You plan to make a merge call | Higher: reads every top-risk path at head, maps tests to behaviors, logs coverage | Yes, if all hard gates pass |
| `recheck` | The author pushed fixes or answered questions | Compares against the saved `latest.json`; re-verifies each previous finding | Yes, at full depth |

Examples:

```text
/review-readiness 512
/review-readiness https://github.com/<owner>/<repo>/pull/123 --mode full
/review-readiness 512 --mode recheck
```

You can also just ask, e.g. "is PR 512 ready for review?". The skill auto-triggers from its description.

### What you get
- **An HTML report that opens in your browser.** It is one self-contained file with a colour-coded decision banner, four score cards, issue and checklist badges, a copy button for the review draft, and collapsible details. Its 14 sections are defined in `references/report-schema.md`.
- A short summary of about 8 lines in the terminal: the decision, the scores, the top issues and the report path.
- **Two separate decisions:** Review Readiness (`READY_FOR_REVIEW` / `NEEDS_AUTHOR_INPUT`) and a Merge Recommendation (`APPROVE_CANDIDATE` / `COMMENT` / `REQUEST_CHANGES` / `CONTINUE_REVIEW`), plus the next responsible owner.
- **Four independent scores** that are never averaged: Author Readiness, Change Quality (or `NOT_ASSESSED`), Verification Confidence, and Operational Risk (higher means riskier).
- **Classified issues:** `CONTEXT_GAP` / `CODE_DEFECT` / `VERIFICATION_GAP` / `DESIGN_RISK` / `REVIEW_INCOMPLETE`, each marked CONFIRMED or HYPOTHESIS.
- **A draft GitHub review comment.** It is never posted.

### Where reports are saved
- **Inside a clone of the PR's repo:** `<repo>/.review-readiness/<owner>__<repo>/pr-<n>/`. The first run adds `.review-readiness/` to `.git/info/exclude`, so reports are never committed. The tracked tree and `.gitignore` are not touched.
- **Anywhere else:** `~/.claude/review-readiness/<owner>__<repo>/pr-<n>/`.
- Each run writes two files and overwrites one:
  - `<UTC-timestamp>-<mode>.json`: the report data, the single source of truth.
  - `<UTC-timestamp>-<mode>.html`: rendered from that JSON.
  - `latest.json`: overwritten with a copy of the JSON; it is the state that `recheck` reads.
- The HTML is produced by `scripts/render_report.py` (Python 3, standard library only). It HTML-escapes all text, because reports quote untrusted PR content.

## Safety model
- **Read-only.** It never comments, approves, requests changes, merges, pushes, commits, checks out or edits.
- **Pre-approved tools** (`allowed-tools`): only read-only `gh pr view/diff/checks`, `gh run view`, `gh repo view`, `gh issue view`, `git log/show/diff/rev-parse/remote/cat-file`, and Read/Grep/Glob.
  - `gh api` is deliberately *not* pre-approved, because it can POST. You'll see a permission prompt, and the skill is instructed to issue GET requests only.
- **Untrusted input.** It ignores instructions embedded in PR bodies, code or CI logs and reports them as findings. The eval case D fixture contains one, which was caught and reported.
- **No execution without asking.** It doesn't run tests, builds or fetches unless you explicitly agree.

## How it decides
The policy is in `references/decision-policy.md`. In short:
1. **Hard gates run first and override scores.**
   - G1: confirmed blocking defect
   - G2: required checks
   - G3: project/security gates
   - G4: coverage of the risk paths
   - G5: critical behavior verified by CI or local execution
2. A gate FAILs only on an *observed* failure or an explicit violation. Pending, skipped or unreadable evidence is `UNKNOWN`, because missing evidence is not bad code.
3. The rules are ordered:
   - REQUEST_CHANGES on a G1/G2/G3 FAIL
   - else COMMENT if the author owns a MAJOR context or verification gap
   - else CONTINUE_REVIEW while the review is incomplete
   - else APPROVE_CANDIDATE, only in full depth with every gate passing

## Files

```
SKILL.md                     workflow, modes, hard rules (loaded on invocation)
references/scoring-rubric.md the 4 dimensions, sub-criteria, evidence-source tags
references/decision-policy.md issue taxonomy, hard gates, decision rules, owners
references/report-schema.md   report JSON schema (v2), field rules, terminal summary format
scripts/render_report.py     validates the JSON and renders the self-contained HTML (stdlib only)
evals/fixtures/case-{a..f}/  synthetic PRs for the 6 acceptance scenarios
evals/expected.md            expected outcomes + fixture-mode substitution rules
evals/results.md             validation results (2 rounds)
examples/                    sample report JSON + rendered HTML (fictional PR from eval case D)
```

## Maintain
- **Changing behavior.** Edit the reference files for policy and scoring, and keep `SKILL.md` for workflow and hard rules. Keep `SKILL.md` under about 200 lines; only its first ~5k tokens survive context compaction, which is why the hard rules sit at the top.
- **Re-validating after any policy or rubric change.** Re-run the fixture evals:
  - Use one general-purpose subagent per case. Tell it to follow `SKILL.md` exactly, but substitute the fixture files for `gh` output as described in the table in `evals/expected.md`.
  - Keep it blind: it must not read `expected.md` or earlier outputs.
  - Write the results to `evals/out/case-<x>/` and compare them with `evals/expected.md`. Record the comparison in `evals/results.md`.
  - Ask each evaluator for a "SKILL FRICTION" list. That list is the best source of the next ambiguity to fix.
- **Adding a scenario.** Create `evals/fixtures/case-<x>/` with `pr.json` (the `gh pr view --json` shape), `checks.json`, and either `diff.patch` or `diff-error.txt`. Optionally add `head/`, `protection.json`, `prev/latest.json` and `incremental.patch`. Add a `case.md` with the mode and availability notes, then add a row to `expected.md`.
- **Composition.**
  - Full mode may invoke the built-in `code-review` skill through the Skill tool, and only with your consent. It never passes `--comment` or `--fix`, and it re-verifies every finding.
  - Skills are composed through the Skill tool, not nested slash commands.
  - If context is the problem, the report suggests the author use a PR explainer such as Mastra's `/pr-explainer`; it doesn't run one itself.
- **Portability.** `argument-hint` and some other keys are Claude Code–only. Uploading this skill to claude.ai or the Skills API would require stripping them down to `name`, `description` and `allowed-tools`.
