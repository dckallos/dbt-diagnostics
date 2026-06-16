# Test tiers

Tests are organized into tiers by purpose and cost. Every test carries the
matching pytest marker (see `[tool.pytest.ini_options].markers` in
`pyproject.toml`) so CI can run tiers selectively.

| Tier         | Marker        | What it asserts                                            | When it runs        |
|--------------|---------------|------------------------------------------------------------|---------------------|
| unit         | `unit`        | One module/function in isolation.                          | Every PR            |
| contract     | `contract`    | Real/golden artifacts parse and classify to exactly one expected result. | Every PR |
| property     | `property`    | Hypothesis-generated valid artifacts hold invariants.      | Every PR (bounded)  |
| robustness   | `robustness`  | Malformed/adversarial artifacts degrade to `unverified`, never raise. | Every PR |
| e2e          | `e2e`         | Full CLI runs; `--json` validates against the schema.      | Every PR            |
| chaos        | `chaos`       | Seeded failure-injection over real golden artifacts.       | Nightly (high volume) |
| live         | `live`        | Requires a real Snowflake connection.                      | Manual / scheduled  |

## Layout

New tests go in the matching subdirectory:

```
tests/
  contract/      # golden-fixture parsing/classification contracts
  property/      # Hypothesis generators + property tests
  robustness/    # malformed-artifact degradation tests
  e2e/           # CLI + --json schema validation
  chaos/         # seeded failure-injection harness + tests
```

## Migration of the flat suite

The pre-existing flat `test_*.py` files (the historical unit + contract suite)
stay in place and are migrated into tiers opportunistically, one PR at a time,
to keep diffs reviewable. A bulk move in a single PR is intentionally avoided:
it would be a large noisy diff and risk breaking fixture-relative paths that
cannot be re-verified offline. Do not move them wholesale.

## Running a single tier

```
pytest -m unit            # fast PR tier
pytest -m "property"      # property-based tier
pytest -m "chaos"         # nightly failure-injection
pytest -m "not live"      # everything that needs no Snowflake
```
