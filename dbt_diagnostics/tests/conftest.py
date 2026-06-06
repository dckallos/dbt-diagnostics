"""
Shared test fixtures for dbt_diagnostics tests.
Loads the JSON artifacts from fixtures/ once per session.
"""

import json
from pathlib import Path

import pytest

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
