# pr-change-walkthrough + pr-risk-review

Two small, user-invoked skills for risk-based PR review:

```
/pr-change-walkthrough <PR>   → what changed in system behavior (before / after / why)
/pr-risk-review <PR>          → what could break, and where a human should look
human reads the pointed-at code → human decides
```

They complement `/pr-explainer`, which builds a long teaching page. These produce a short, interactive review page:
- evidence links to GitHub permalinks at the analyzed SHA
- a "reviewed" checkbox on each item, saved in the browser
- P0/P1/P2 filters on risks

The terminal gets a few-line summary.

## Install

Both skills live in this repo and are symlinked as personal skills:

```
ln -s "$PWD/pr-change-walkthrough" ~/.claude/skills/pr-change-walkthrough
ln -s "$PWD/pr-risk-review"        ~/.claude/skills/pr-risk-review
```

Both set `disable-model-invocation: true`, so they run only when you type the slash command. Neither pins a model; both inherit the session model.

## Usage

```
/pr-change-walkthrough 22470
/pr-change-walkthrough https://github.com/org/repo/pull/22470
/pr-risk-review 22470
/pr-risk-review 22470 --no-html   # full report in the terminal, write nothing
/pr-risk-review 22470 --refresh   # ignore any cached report
```

- A bare number means the PR belongs to the repo in the current directory. A URL works from any directory.
- They need `gh` to be authenticated.
- **Local mode:** the checkout's `origin` is the PR's repo. The skills may run `git fetch --no-tags origin pull/<n>/head`, which only adds objects and updates `FETCH_HEAD`. After that, every read is a revision-exact `git show`, `git diff` or `git grep`.
- **Remote mode:** any other directory. Reads go through GET-only `gh api`. Raw `contents` reads are deliberately not pre-approved, so expect permission prompts. Caller search can't be pinned to a revision, and the cache is off.

## How they share context (optional)

1. **Same conversation:** if `/pr-change-walkthrough` already ran for the same head SHA, `/pr-risk-review` reuses its behavior analysis.
2. **File cache:** every run (except `--no-html`) writes `<n>-walkthrough.{md,html}` or `<n>-risks.{md,html}` to `~/.cache/pr-review/<owner>/<repo>/`.
   - `$PR_REVIEW_DIR` replaces the `~/.cache/pr-review` root; `<owner>/<repo>/` is still appended.
   - The folder is outside every repo, so reports cannot be committed by accident.
   - It works in both local and remote mode.
   - Each `.md` file starts with a header recording repo, PR, base ref, merge-base SHA, head SHA, timestamp and skill version.
   - A cached report is reused only when repo, PR, head and merge-base all match and the skill version is the same.
   - Any mismatch is reported as `Stale cache ignored: …`, and the analysis runs fresh.

With `--no-html` nothing is written. Each skill works without the other and without any cache.

## Cost controls

- PR metadata and the file list are injected before the model starts (`!` preprocessing), which saves a tool-call turn.
- Reading is tiered: the file list first, then core diffs file by file, then base versions, direct callers and related tests only when a claim needs them.
- Noise files (lockfiles, generated code, snapshots) are skipped. The full diff is fetched only for PRs under about 400 lines.
- There are no subagents, and no tests are run.
- The model writes only the Markdown report. `scripts/render_report.py` (stdlib Python) turns it into the HTML page, so the HTML costs no model tokens. `pr-change-walkthrough/scripts/render_report.py` is a symlink to the same file.
- Output is capped at 5 detailed changes or 5 risks. Anything past the cap is still named on one line (`Also changed` or `Other P2 candidates`). P0 and P1 risks are never cut. A `Coverage:` line says what was not read.
- Security-sensitive paths are exempt from the budget, so critical risks are never dropped to save tokens.
