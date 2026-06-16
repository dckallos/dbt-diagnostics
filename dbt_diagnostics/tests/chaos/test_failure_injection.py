"""
Chaos tier: seeded failure-injection over real dbt artifacts.

These tests drive dbt_diagnostics.tests.chaos.injectors.ChaosEngine against the
real classifier dispatch. Two contracts are asserted:

  - robustness: no mutation, however malformed, makes classify() raise.
  - detection: an injected known fault signature is localized to exactly the
    classifier that owns it.

Reproducibility: the multi-seed robustness sweep uses a fixed list of seeds so
CI is deterministic. If a seed ever fails, the assertion message prints the
seed and the exact mutation sequence so it can be replayed with one command:

    pytest -m chaos -k replay --seed=<N>

The nightly job widens the seed range (see .github/workflows); the PR tier
stays bounded so it is fast.
"""

import pytest

from dbt_diagnostics.classifiers import classify
from dbt_diagnostics.tests.chaos.injectors import (
    KNOWN_SIGNATURES,
    ChaosEngine,
    build_mutation_catalog,
    load_artifact,
)

pytestmark = pytest.mark.chaos

# Real, captured artifacts the engine perturbs. Every one of these is a genuine
# Snowflake failure captured from dbt-core 1.11.x (run-results v6).
REAL_ARTIFACTS = [
    "real_object_not_exist_002003.json",
    "real_invalid_identifier_000904.json",
    "real_numeric_overflow_100132.json",
    "real_string_too_long_100078.json",
    "real_division_by_zero_100035.json",
    "real_syntax_error_001003.json",
    "real_privileges_003001.json",
]

# Bounded for PR CI. The nightly job overrides via -p chaos volume.
PR_SEEDS = [1, 7, 42, 1234, 99999, 2026]
PR_ROUNDS = 100


def _fixture_path(name):
    from pathlib import Path

    return Path(__file__).parent.parent.parent / "fixtures" / name


@pytest.mark.parametrize("target_class", sorted(KNOWN_SIGNATURES))
def test_injected_signature_is_localized(target_class):
    """A message carrying only one fault signature dispatches to its owner."""
    got = classify(KNOWN_SIGNATURES[target_class])
    assert got is not None, f"{target_class} signature classified as unknown"
    assert got.error_class == target_class


@pytest.mark.parametrize("seed", PR_SEEDS)
def test_chaos_sweep_never_breaks_contract(seed):
    """
    Mixed robustness + detection mutations against a real artifact: nothing
    raises, and every detection mutation is localized correctly.
    """
    artifact = load_artifact(_fixture_path("real_object_not_exist_002003.json"))
    engine = ChaosEngine(classify, seed=seed)
    result = engine.run(artifact, rounds=PR_ROUNDS)
    assert result.ok, (
        f"chaos contract violated (replay with seed={result.seed}).\n"
        f"applied sequence: {result.applied}\n"
        f"failures:\n  " + "\n  ".join(result.failures)
    )


@pytest.mark.parametrize("artifact_name", REAL_ARTIFACTS)
def test_every_real_artifact_survives_injection(artifact_name):
    """Robustness holds across all captured real artifacts, not just one."""
    artifact = load_artifact(_fixture_path(artifact_name))
    result = ChaosEngine(classify, seed=2026).run(artifact, rounds=PR_ROUNDS)
    assert result.ok, (
        f"{artifact_name}: chaos contract violated (replay seed={result.seed}).\n"
        f"failures:\n  " + "\n  ".join(result.failures)
    )


def test_runs_are_reproducible_from_seed():
    """Same seed -> identical applied-mutation sequence (deterministic replay)."""
    artifact = load_artifact(_fixture_path("real_object_not_exist_002003.json"))
    a = ChaosEngine(classify, seed=555).run(artifact, rounds=80)
    b = ChaosEngine(classify, seed=555).run(artifact, rounds=80)
    assert a.applied == b.applied


def test_catalog_covers_both_modes():
    """Guard the catalog so a refactor cannot silently drop a contract mode."""
    modes = {m.expectation.mode for m in build_mutation_catalog()}
    assert modes == {"robust", "detect"}
