"""
Shared test fixtures for dbt_diagnostics tests.
Loads the JSON artifacts from fixtures/ once per session.
"""

import json
import os
from pathlib import Path

import pytest

# Register Hypothesis profiles so the property/chaos tiers can scale their
# example budget by environment without code changes. PR CI uses "dev"
# (bounded, fast); the nightly hardening job sets HYPOTHESIS_PROFILE=nightly.
try:
    from hypothesis import HealthCheck, settings

    settings.register_profile("dev", max_examples=50)
    settings.register_profile("ci", max_examples=200)
    settings.register_profile(
        "nightly", max_examples=2000, suppress_health_check=[HealthCheck.too_slow]
    )
    settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
except ImportError:
    # Hypothesis is part of the dev/test extra; the rest of the suite runs
    # without it. Property tests are skipped when it is absent.
    import warnings
    warnings.warn(
        "hypothesis not installed; property-based tests will be skipped",
        stacklevel=1,
    )

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def contract_type_mismatch_results():
    """Load the contract type mismatch run_results.json fixture."""
    path = FIXTURES_DIR / "contract_type_mismatch.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def manifest_minimal():
    """Load the minimal manifest.json fixture."""
    path = FIXTURES_DIR / "manifest_minimal.json"
    with open(path) as f:
        return json.load(f)
