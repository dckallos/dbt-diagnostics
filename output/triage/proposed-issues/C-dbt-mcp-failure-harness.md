# feat: gated dbt-MCP failure-trigger harness for fixture capture

## Summary

Add an opt-in harness that uses the dbt MCP to trigger real failures in the
local `~/dev/artwork-db` repo and its dbt project `artwork_pipeline`, then feeds
the captured errors into the existing fixture flow so the diagnostics engine is
exercised against genuine, reproducible failures.

## Evidence and confidence

Medium. The fixture-capture flow exists (`docs/FIXTURE_CAPTURE.md`). dbt Labs
recently released an MCP server; the exact tool surface must be verified against
its current docs and the running server before wiring (version-sensitive). The
target repo is private but accessible to the maintainer.

## Current gap

Failure fixtures are captured manually. There is no repeatable way to provoke a
known failure class on demand and snapshot it for regression coverage.

## Acceptance criteria

- An opt-in command (off by default) triggers a chosen failure class in
  `artwork_pipeline` via the dbt MCP and writes a fixture consumable by the
  diagnostics engine.
- Positive: a deliberately broken model produces a captured fixture.
- Negative: with the harness disabled or credentials absent, nothing runs and
  the command says so.
- Degradation: a partial/timeout failure is recorded as such, not as success.
- Cost: any warehouse-scanning step is gated like a Tier-B probe (cost ceiling
  and opt-in), per the scope guard.

## Focused test plan

Offline unit tests with the MCP and dbt calls stubbed: fixture shape, the
disabled path, and the credentials-absent path. Live runs are maintainer-gated.

## Scope and likely files

- A new harness module under dbt_diagnostics/ or scripts/
- docs/FIXTURE_CAPTURE.md
- dbt_diagnostics/fixtures/

## Explicit non-goals

- Not part of the always-on, read-only governance toolchain; this is a separate
  trust domain that performs real side effects and must stay opt-in.
- No automatic execution in CI without explicit approval and credentials.

## Dependencies and traceability

- External: dbt MCP server (verify current tool surface and auth).
- Related: docs/FIXTURE_CAPTURE.md.
