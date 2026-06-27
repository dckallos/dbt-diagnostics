# dbt_diagnostics CHANGELOG

## [Unreleased]

### Add the Codex quality gate

- I added `bash .codex/bin/action.sh codex-quality` as a credential-free
  semantic quality gate for Codex-authored work.
- I added a governance-boundary checker that rejects skill or instruction text
  that authorizes GitHub metadata mutation from read-only surfaces.
- I made `issue-work` hand nonconformant issue body updates back to the
  maintainer or a separately authorized writer flow instead of allowing the
  skill to update the live issue body.

### Define the synthesis review packet contract

- I added the v1 `synthesis-review-packet` schema docs and machine schema for
  bounded LLM backlog review evidence.
- I added `validate_synthesis_review_packet()` so malformed, stale,
  over-budget, or mutation-shaped packets are rejected before any downstream
  LLM review consumes them.
- The packet contract remains read-only and advisory: no CLI command, builder,
  retrieval path, verdict schema, comments collection, or GitHub write path is
  added.

### Expose the read-only Project planner wrapper

- I added `bash .codex/bin/action.sh project-plan` as the stable Codex wrapper
  for the existing advisory Project planner.
- The wrapper delegates through `.codex/bin/triage-project-plan.sh`, forwards
  arguments to `python scripts/triage/triage.py project-plan`, and does not add
  any GitHub write path.
- I documented the wrapper alongside the existing read-only audit and frontier
  actions.

### Add read-only backlog synthesis signals

- I added a `backlog-synthesis` governance command that emits deterministic
  candidate signals for likely duplicates, explicit overlap, split candidates,
  semantic disposition hypotheses, and dependency-order inversions.
- I kept the existing readiness `recommended_disposition` map mechanical while
  surfacing semantic disposition hypotheses as additive audit fields and as a
  local synthesis override.
- I added the `backlog-synthesis` skill so cross-issue verdicts are proposed
  from the bounded signal artifact for maintainer review, with no tracker
  mutation path.
- I documented and validated the backlog-synthesis signal contract in
  `docs/BACKLOG_SYNTHESIS_SIGNALS_SCHEMA_V1.md` and
  `docs/backlog-synthesis-signals-schema-v1.json`.

### Add governance issue-kind classification

- I added a dedicated `governance` issue kind for process and tracker-contract
  decisions so they no longer have to masquerade as product test-verification
  work.
- I added the `governance:` title prefix to triage policy and kept genuine
  `test:` issues classified as `test_verification`.
- Governance issues require the reduced decision section set and do not require
  product-test sections by kind.

### Add read-only GitHub Project desired-state planning

- I added a `project-plan` governance command that emits a deterministic
  desired GitHub Project layout from an existing snapshot and readiness audit.
  It assigns audit-state columns, issue placement, and ordering without reading
  GitHub.
- I added dependency-inversion warnings when the planned order puts an issue
  before one of its direct dependencies.
- The emitted Project plan is not an approval bundle and contains no metadata
  operations, issue bodies, or state changes. Project and metadata writes remain
  unsupported by this planner.
- I added `validate_project_plan()` and a CLI self-check so malformed, stale,
  or mutation-shaped Project plans are rejected before they are emitted.
- I documented the Project plan contract in `docs/PROJECT_PLAN_SCHEMA_V1.md`
  and added the matching machine schema at `docs/project-plan-schema-v1.json`.

### Add issue contract, readiness audit, and read-only relay coordination

- I added the versioned issue contract and separate governance/readiness states.
- I exposed the documented command surface: `snapshot`, `audit`, `plan`,
  `project-plan`, `apply`, `contract`, `review-packet`, `standardize`, and
  `frontier`.
- I made audit output directly consumable by deterministic audit and
  implementation frontier selection, including explicit empty selection and
  bounded coordinator/worker-packet validation.
- I kept contract review, review packets, and body standardization local-only.
  Issue-body mutation remains forbidden and the metadata mutation allowlist is
  unchanged.
- I added focused governance tests, Codex relay documentation, stable read-only
  wrappers, and minimal repository skills.
