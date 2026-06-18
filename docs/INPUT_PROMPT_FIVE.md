Pass 5 -- issue definition and creation. The analysis is finished; this pass turns
the verified findings into a clean, de-duplicated, sequenced set of GitHub issues,
and creates them. No further code review here.

Sources:
- Project files: OUTPUT_ONE.md, OUTPUT_TWO.md, OUTPUT_THREE.md (the change plan),
  and OUTPUT_FOUR.md (the red-team). Prefer OUTPUT_FOUR's [PROVEN] findings plus
  OUTPUT_THREE's changes as the basis for committed work; treat [SPECULATIVE]
  items as "investigate/spike" issues, not committed scope. Where OUTPUT_FOUR
  refuted or corrected a Pass-3 change, follow OUTPUT_FOUR.
- GitHub MCP is connected to dckallos/dbt-diagnostics. Read code from the
  `donkey-kong-sandbox` branch when you need to confirm scope. Issues and epics
  are repo-wide, not branch-specific. Follow the repo conventions in AGENTS.md and
  CONTRIBUTING.md (ASCII-only, conventional commit/issue style, additive --json,
  one PR per issue, NO automated-authorship markers anywhere).

Work in this order, and PRINT the plan before creating anything:

1. Inventory what already exists. List all open issues and the epics (e.g. #4,
   #48) and recently closed/merged work (e.g. the PR that closed #39/#40/#42), so
   nothing is duplicated. Mark which prior findings are ALREADY tracked.

2. Map findings -> issues. For each verified finding/change not already tracked,
   decide: extend an existing issue or create a new one. Group cohesively -- do
   not file 27 micro-issues where a handful of independently shippable issues fit
   (one PR per issue). Note what is already covered and should NOT be re-filed.

3. Draft each new issue: conventional imperative title, one-paragraph scope,
   acceptance criteria, suggested labels, dependencies/sequence on other issues,
   and the parent epic. Keep scope to something one PR can land.

4. Sequence into waves matching OUTPUT_THREE's ordering (correctness-critical
   first), and call out blockers between issues.

5. Create them via MCP -- token-aware. Create the highest-priority,
   fully-specified issues first. If you approach your budget limit, STOP creating,
   emit the remaining issues as ready-to-paste Markdown drafts, and state exactly
   where you stopped so a follow-up chat can finish. Never create a half-specified
   issue, and never create a duplicate of an existing one.

Before creating anything, output the full plan (existing vs new, the mapping, and
the ordered list you intend to create) for a sanity check. Then create, then list
the created-issue numbers/links, then any deferred drafts.
