Pass 3 of the multi-pass review -- the most detailed pass. Assumes the project
instructions are set. The strategy and architecture are already settled in the
project files `OUTPUT_ONE.md` (landscape) and `OUTPUT_TWO.md` (architecture,
design, and the rewrite/refactor verdict). Do NOT re-argue what or why; this pass
delivers the HOW at the lowest practical granularity. The package source is the
project file `code-snapshot.md` -- read it in full (paste inline below the marker
for fidelity) and treat it as authoritative.

Produce a granular, prioritized enhancement specification. Work through the
package subsystem by subsystem (and file by file within each). For every concrete
change, give:

- Location: file (basename + the module you infer it lives in), class/function,
  and the specific construct or lines.
- Problem: one or two sentences, tied to a specific Pass 1 or Pass 2 finding where
  applicable (cite it by name).
- Before: a short verbatim excerpt from the snapshot (only the relevant region).
- After: a concrete Python patch -- real signatures, types, and control flow --
  minimal and self-contained. Show only the changed region; do not reprint whole
  files. If you introduce an API not in the snapshot, label it [NEW].
- Why it's safe: what behavior is preserved or intentionally changed, and which
  edge cases the change covers.
- Test: the specific test to add and its tier (unit / contract / robustness /
  e2e), including the case that would fail against today's code.
- Effort/risk: small | medium | large, plus any ordering dependency on another
  listed change.

Organize the changes into prioritized waves (for example: correctness-critical
first, then the portability seam, then performance and maintainability), and
order changes within each wave so earlier ones unblock later ones. Prefer many
small, independently reviewable changes over a few large ones; if Pass 2 called
for a substantial refactor or rewrite of a subsystem, decompose it here into an
ordered sequence of safe, individually shippable steps.

Flag any change that cannot be made safely without a test fixture or information
absent from the snapshot, and state exactly what is needed. If a proposed change
conflicts with a Pass 2 decision, surface the conflict rather than silently
diverging.

Output: a Markdown enhancement spec organized by wave, then by file.

=== BEGIN PACKAGE SNAPSHOT ===
