Pass 4 -- adversarial red-team of the review itself. You are an extreme pessimist:
assume the prior analysis is over-confident and partly wrong, and your job is to
find where. But every concern must be backed by specific evidence -- a fabricated
flaw is as useless as a rubber stamp. Tag each finding [PROVEN] (verified against
the code/artifacts in front of you) or [SPECULATIVE] (a risk you cannot confirm),
and never blur the two.

Sources and how to use them (read carefully -- this determines whether your
findings are real):

- The PACKAGE SOURCE is pasted inline at the very end of this message, after the
  line "=== BEGIN PACKAGE SNAPSHOT ===". It was generated from the
  donkey-kong-sandbox branch and INCLUDES the code, .github/workflows/ci.yml, and
  pyproject.toml. Treat this snapshot as the single authoritative source for all
  code, CI, and packaging questions. Read it in full.
- Do NOT try to clone the repo, fetch code over the web, or pull code through the
  GitHub connector. There is no network for cloning, and the connector is
  search-indexed and default-branch-biased -- it will silently give you the wrong
  branch or empty results. The snapshot is the truth; use it.
- The GitHub connector (dckallos/dbt-diagnostics) is for ONE thing only: the issue
  tracker (question 3). If an issue query returns 0 or empty, say so explicitly
  and stop that section -- do not invent issues or proceed as if you had them.
- Web search IS allowed, but only to verify EXTERNAL facts for question 2 (dbt
  artifact schemas, Snowflake error codes / SHOW output, sqlglot, Python
  behavior). Never use it to reconstruct this package.
- FIXTURES are deliberately NOT in the snapshot. Fixture-naming rule: ONLY files
  named `real_*` are captured from real dbt runs and may be treated as evidence;
  every other fixture in the repo is synthetic / AI-authored and is NOT ground
  truth -- do not treat it as real and do not try to fetch it. For question 2,
  reason about what real fixtures WOULD verify, not about synthetic ones.

Headers in the snapshot use the BASENAME only, so several files share a name
(e.g. __init__.py); infer each file's module from its imports and disambiguate
when you cite it.

Answer all six questions. Lead with the most damaging findings.

1. Completeness and correctness of OUTPUT_THREE. Go change by change (1-27).
   Verify each against the snapshot and flag: does the "before" excerpt match the
   real code? does the "after" patch actually compile and integrate -- real names,
   imports, signatures, and every call site it forgets to update? does it break
   other callers or edge cases? is the "Test" sufficient to catch a regression, or
   is it theater? Is any change logically wrong or resting on an assumption the
   code does not support? Where is more detail needed before it is safe to
   implement, and what changes are MISSING entirely?

2. Gaps from no real fixtures and no web search in the PRIOR passes. Passes 1-3
   never ran the code, executed a test, read a real `real_*` artifact, or verified
   any external fact. Enumerate the specific claims that are therefore UNVERIFIED
   and could be wrong -- e.g. exact dbt artifact field names/shapes, run_results
   carrying compiled_code, SHOW GRANTS row/column positions, Snowflake error-code
   and message formats, sqlglot behavior. For each, verify it now via web search
   where you can, and state the authoritative source; where you cannot, say what
   real artifact would settle it.

3. Issue tracking (GitHub connector, dckallos/dbt-diagnostics). First list the
   issues that ALREADY exist (open and recently closed) and any epics, so nothing
   is duplicated; if the connector returns nothing, say so and stop here. Then map
   OUTPUT_THREE's 27 changes onto (a) existing issues and (b) genuinely new issues
   to create. Propose each new issue (title + one-line scope + labels +
   dependency/sequence). Recommend WHEN to create them: which in this chat vs a
   follow-up chat. Issues are repo-wide, not branch-specific.

4. Snowflake-agnostic architecture. Using the snapshot, read every module that
   touches Snowflake (SQL dialect, SHOW/DESCRIBE, INFORMATION_SCHEMA, error codes
   and messages, the connector, identifier quoting/casing) and judge whether
   OUTPUT_THREE's WarehouseAdapter seam (change 21) is real separation or a thin
   shell that still leaks Snowflake assumptions into classifiers, tracers, and
   enrichers. After all 27 changes, what would still break on a second warehouse
   (BigQuery, Postgres, DuckDB)? Be concrete about what the seam fails to cover.

5. CI and shift-left testing. Read ci.yml and pyproject.toml from the snapshot.
   Assess what CI actually runs today, what it misses, and how to "shift left" on
   integration testing: running the tool against committed `real_*` golden
   artifacts in CI, contract tests on real first-party schemas, a live-Snowflake
   job gated on credentials, pre-commit hooks. Distinguish clearly what can run
   with no warehouse from what needs a real one.

6. What did the human miss? Turn the pessimist's stance on the whole exercise, not
   just the code: all four passes read the same snapshot from the same model
   family (correlated errors, not true independence); fixtures/CI were outside the
   review for most passes; nothing has been executed or merged; the risk of
   analysis-paralysis vs shipping; source-of-truth drift between local, workspace,
   and GitHub. Tell the human plainly what they are not seeing.

Output: a Markdown red-team report, most damaging findings first, every finding
tagged [PROVEN] or [SPECULATIVE] and grounded in the snapshot (or, for question 2,
a cited external source).

=== BEGIN PACKAGE SNAPSHOT ===
