Pass 4 -- adversarial red-team of the review itself. You are an extreme pessimist:
assume the prior analysis is over-confident and partly wrong, and your job is to
find where. But every concern must be backed by specific evidence from the code or
the artifacts -- a fabricated flaw is as useless as a rubber stamp. Tag each
finding [PROVEN] (you verified it against real code/artifacts) or [SPECULATIVE]
(a risk you cannot confirm from what you read), and never blur the two.

Sources:
- Project files: OUTPUT_ONE.md (breadth review), OUTPUT_TWO.md (architecture
  review), OUTPUT_THREE.md (the 27-change, 4-wave implementation plan). These are
  the material UNDER REVIEW, not trusted conclusions.
- GitHub MCP is connected to dckallos/dbt-diagnostics. The package source was NOT
  pasted into this chat. Read all code, .github/workflows/ci.yml, and pyproject.toml
  from the `donkey-kong-sandbox` branch -- that is the canonical development branch
  AND the exact branch the review snapshot was generated from, so OUTPUT_THREE's
  "before" excerpts must be verified against it, NOT against the repository default
  branch (which lags donkey-kong-sandbox). Use MCP to read every file you need to
  verify a claim; do not rely on memory or on the prior reports where you can read
  the real source instead.

This pass is ANALYSIS ONLY: do not create issues or open PRs here. Issue
definition and creation are handled in a dedicated follow-up pass that consumes
this report.

Answer all five questions. Lead with the most damaging findings.

1. Completeness and correctness of OUTPUT_THREE. Go change by change (1-27).
   For each, verify against the real code via MCP and flag: does the "before"
   excerpt match the current code? does the "after" patch actually compile and
   integrate -- real names, imports, signatures, and every call site it forgets to
   update? does it break other callers or edge cases? is the "Test" sufficient to
   catch a regression, or is it theater? Is any change logically wrong, or does it
   rest on an assumption the code does not support? Where is more detail needed
   before someone could implement it safely, and what changes are MISSING entirely?

2. Gaps from no real fixtures and no web search. No prior pass ran the code,
   executed a test, read a real manifest/run_results/catalog, or verified any
   dbt/Snowflake fact online. Enumerate the specific claims that are therefore
   UNVERIFIED and could be wrong -- for example exact dbt artifact field names and
   shapes, run_results carrying compiled_code, SHOW GRANTS row/column positions,
   Snowflake error-code and message formats, sqlglot behavior. For each, state the
   real artifact or authoritative source that would confirm or refute it.

3. Snowflake-agnostic architecture. Assess how well the plan actually separates
   warehouse-specific logic. Read every module that touches Snowflake (SQL
   dialect, SHOW/DESCRIBE, INFORMATION_SCHEMA, error codes and messages, the
   connector, identifier quoting/casing) and judge whether OUTPUT_THREE's
   WarehouseAdapter seam (change 21) is real separation or a thin shell that still
   leaks Snowflake assumptions into classifiers, tracers, and enrichers. After all
   27 changes, what would still break on a second warehouse (e.g. BigQuery,
   Postgres, DuckDB)? Be concrete about what the seam fails to cover.

4. CI and shift-left testing. Read .github/workflows/ci.yml and pyproject.toml via
   MCP -- they were not in any review snapshot, so no prior pass saw them. Assess
   what CI actually runs today, what it misses, and how to "shift left" on
   integration testing: e.g. running the tool against committed golden artifacts
   in CI, contract tests on real first-party schemas, a live-Snowflake job gated
   on credentials, pre-commit hooks. Distinguish clearly what can run with no
   warehouse from what needs a real one.

5. What did the human miss? Turn the pessimist's stance on the whole exercise, not
   just the code. Name the blind spots in this review process itself -- for
   example: all four passes read the same snapshot produced by the same model
   family (correlated errors, not true independence); the snapshot excluded tests,
   fixtures, and CI; nothing has actually been executed or merged; the risk of
   analysis-paralysis versus shipping; source-of-truth drift between local stage,
   workspace, and GitHub. Tell the human plainly what they are not seeing.

Output: a Markdown red-team report, most damaging findings first, every finding
tagged [PROVEN] or [SPECULATIVE] and grounded in code or artifacts you actually
read via MCP. Save it as OUTPUT_FOUR.md; it is the input to the issue-definition
pass (Pass 5).
