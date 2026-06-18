Pass 5 -- convert the review into GitHub issues. This is the step that turns
analysis into shippable work, so be disciplined: do not duplicate existing issues,
and do not file work that the red-team did not stand behind.

Sources:
- Project files: OUTPUT_ONE.md, OUTPUT_TWO.md, OUTPUT_THREE.md (the 27-change
  plan), and OUTPUT_FOUR.md (the adversarial red-team). OUTPUT_FOUR is the gate:
  only changes it judged sound ([PROVEN], or [SPECULATIVE] but worth doing) become
  implementation issues. Changes it flagged as wrong, unverified, or theater do
  NOT become implementation issues -- at most a verification task.
- GitHub MCP is connected to dckallos/dbt-diagnostics. Issues and epics are
  repo-wide. Read code from the `donkey-kong-sandbox` branch and read AGENTS.md /
  CONTRIBUTING.md via MCP so issues follow repo conventions (one PR per issue,
  conventional-commit framing, ASCII only, and -- importantly -- NO AI-authorship
  markers anywhere in issue text).

Do the following, in order:

1. Enumerate what already exists. List open issues, recently closed issues, and
   epics (e.g. the live-verification and cross-version-compat epics). This is
   mandatory before proposing anything, so nothing is duplicated.

2. Triage OUTPUT_THREE's 27 changes through OUTPUT_FOUR. For each change mark:
   ready-to-file, needs-verification-first (no real fixture / unconfirmed
   assumption), or drop (red-team rejected it). Show the mapping in a short table.

3. Map ready-to-file work onto: (a) an EXISTING issue/epic it belongs under, or
   (b) a NEW issue. Avoid creating a new issue where an open one already covers it.

4. Specify each NEW issue: title; one-paragraph scope; acceptance criteria;
   suggested labels; parent epic; dependency/sequence on other issues; and the
   files it touches (so file-disjoint issues can become parallel PRs and colliding
   ones are sequenced).

5. Sequence everything into waves that respect dependencies and keep concurrent
   issues file-disjoint, mirroring how the repo already splits one-PR-per-issue.

6. Then decide creation timing by your remaining token budget: CREATE the
   high-confidence, dependency-free issues now via MCP (check once more they do not
   duplicate step 1), and for the rest output ready-to-file specs for a follow-up
   chat. If budget is low, STOP creating and emit specs instead -- a half-created,
   low-quality issue set is worse than a clean spec. State clearly which issues you
   actually created (with numbers/links) versus which you left as specs.

Output: the existing-issue inventory, the triage table, the new-issue specs, the
wave/sequence plan, and a clear list of what you created vs deferred.
