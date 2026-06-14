# Contributing

Read `AGENTS.md` first. This file defines the branch/PR workflow, the release
process, and what "done" means here, concretely enough to check.

## Branch model

```
main                      stable / released
  ^  PR at release milestones only
donkey-kong-sandbox       integration / development (default for daily work)
  ^  squash-merge; one issue per PR; CI green
feat/<issue#>-<slug>      short-lived feature branch
```

- All work branches off `donkey-kong-sandbox` and PRs back into it.
- `main` stays stable; `donkey-kong-sandbox` is promoted to `main` only at
  release milestones, via its own PR.
- One PR implements one issue. Example branch: `feat/7-root-cause-aggregator`.
- Squash-merge to keep history linear and readable.

## Commit style

- Conventional subjects: `feat:`, `fix:`, `docs:`, `chore:`, `test:`,
  `refactor:`. Imperative mood ("add", not "added").
- The body explains WHY, not just what.
- ASCII-only (no smart quotes, em dashes, arrows).

## Voice and authorship

Everything written in this repo -- commits, PR descriptions, issues, code
comments, CHANGELOG entries, docs -- is in my own first-person voice. No
automated-authorship markers: no "Generated with ...", no `Co-Authored-By`
trailers, no third-party attribution. Plain, direct engineering prose.

## Definition of Done (per PR)

A PR is ready to merge only when ALL of these hold:

- [ ] Linked to an issue (`Closes #N`) that traces to an epic.
- [ ] Tests added or updated; `pytest` green locally and in CI.
- [ ] `CHANGELOG.md` updated under `## [Unreleased]` if behavior changed.
- [ ] Offline behavior defined (the feature degrades to `unverified` + the
      query to run when no Snowflake connection is available).
- [ ] No Tier-B (warehouse-scanning) probe runs without a cost gate.
- [ ] No re-entry into static-lint space (see AGENTS.md scope guard).
- [ ] `--json` `schema_version` change, if any, is additive-only.
- [ ] The relevant design doc is still consistent with the change.

## Versioning and releases

Semantic versioning. The version lives in `[project].version` in
`pyproject.toml` and is the single source of truth.

- **Per feature PR (into `donkey-kong-sandbox`):** do NOT bump the version. Add
  a `CHANGELOG.md` entry under `## [Unreleased]`.
- **At a release (PR `donkey-kong-sandbox` -> `main`):** bump the version once,
  covering everything accumulated under `## [Unreleased]`.

Choosing the bump from what is in `## [Unreleased]`:
- new diagnostic / capability -> minor
- bug fix only -> patch
- breaking `--json` `schema_version` change -> major (while pre-1.0, a flagged
  minor is acceptable, but call it out in the CHANGELOG)

Release checklist:
1. Decide the bump from the `## [Unreleased]` section.
2. Bump `[project].version` in `pyproject.toml`.
3. Rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD`; add a fresh empty
   `## [Unreleased]`.
4. Open the release PR `donkey-kong-sandbox -> main`, titled `release: vX.Y.Z`.
5. After merge, tag `vX.Y.Z` and cut a GitHub Release from the CHANGELOG section.

## schema_version policy (--json output)

- The `--json` schema is **additive-only** within a major version: new keys may
  be added; existing keys are never removed or renamed.
- Any breaking shape change requires a major `schema_version` bump and a note
  in `CHANGELOG.md` plus the design doc.

## Cost tiers (probes)

- **Tier A** ($0 cloud-services metadata: SHOW / INFORMATION_SCHEMA / DESCRIBE
  / SHOW GRANTS) -- may run unconditionally.
- **Tier B** (warehouse-scanning: COUNT DISTINCT, anti-joins, row sampling) --
  must be gated by a cost ceiling and be opt-in. See
  `docs/DESIGN_LIVE_VERIFICATION.md` section 3.1.

## Branch protection (apply once on donkey-kong-sandbox)

Repo settings (Settings -> Branches -> Add rule) for `donkey-kong-sandbox`:

- Require a pull request before merging.
- Require status checks to pass (select the CI workflow).
- Require linear history.
- Do not allow direct pushes.

Equivalent via the GitHub CLI:

```
gh api -X PUT repos/dckallos/dbt-diagnostics/branches/donkey-kong-sandbox/protection \
  -F required_pull_request_reviews.required_approving_review_count=1 \
  -F required_status_checks.strict=true \
  -F 'required_status_checks.contexts[]=test' \
  -F enforce_admins=false \
  -F required_linear_history=true \
  -F restrictions=
```

## Local development

```
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,live]"
pytest
```
