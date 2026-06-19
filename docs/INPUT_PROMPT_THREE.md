Pass 3 -- the granular, execution-level pass. The strategy and architecture are
already settled in the two project files OUTPUT_ONE.md (breadth: correctness
triage, portability, testing/perf/security/CLI) and OUTPUT_TWO.md (architecture,
design, concrete refactors, and the rewrite verdict). The package source is pasted
inline after the marker -- read it in full and treat it as authoritative. The two
prior reports are the agreed agenda, not the source of truth: where a prior claim
conflicts with the code, the code wins -- say so and correct it.

Your job is to turn the agreed findings into a concrete, ordered, file- and
function-level change plan. Do not re-argue strategy or re-summarize the reports.

First, a brief reconciliation (keep it short):
- The findings BOTH reports raised independently (e.g. lineage flat-list treated
  as an edge path; live-probe None treated as "absent"; overloaded
  DiagnosticFinding; grouping/render duplication) -- treat these as highest
  confidence.
- Findings only one report raised -- confirm or reject each against the code in
  one line.
- The one place the reports DISAGREE: the rewrite-vs-refactor verdict
  (OUTPUT_ONE: no rewrite; OUTPUT_TWO: substantial subsystem refactor). Decide
  which the code supports and state it in one sentence. Do not split the
  difference for diplomacy.

Then the change plan. Group changes into prioritized waves (correctness-critical
first; then the structural refactors the reports call for; then the
database-portability seam; then maintainability/cleanup). Order changes within
each wave so earlier ones unblock later ones, and prefer many small,
independently shippable changes over a few large ones. For each change:

- Location: file (basename + inferred module), class/function, the specific lines
  or construct.
- Source: which prior finding it implements (OUTPUT_ONE / OUTPUT_TWO / both), or
  [NEW] if you are adding it.
- Before: a short verbatim excerpt from the snapshot.
- After: a concrete Python patch -- real signatures, types, control flow --
  minimal and self-contained; show only the changed region; label any new API
  [NEW]. Where OUTPUT_TWO already sketched a target shape, refine it into a patch
  against the real code rather than repeating the sketch.
- Why it's safe: behavior preserved or intentionally changed, and the edge cases.
- Test: the specific test to add and its tier (unit/contract/robustness/e2e),
  including the case that fails against today's code.
- Effort/risk: small | medium | large, plus any ordering dependency.

Decompose the larger subsystem refactors the reports recommend (lineage graph,
typed live-probe gateway, evidence/verdict separation, centralized artifact
views) into ordered sequences of individually safe, reviewable steps -- not a
single big-bang change. Flag any change that cannot be made safely without a test
fixture or information absent from the snapshot, and say exactly what is needed.
If two recommended changes conflict, surface it rather than silently choosing.

Output: a Markdown change plan -- the brief reconciliation first, then waves, then
files within each wave.

=== BEGIN PACKAGE SNAPSHOT ===
