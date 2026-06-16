"""
dbt_diagnostics/tests/chaos/injectors.py

Seeded failure-injection over real dbt artifacts.

This is the "failure injector" for the test suite: instead of asserting only
that known-good fixtures classify correctly (happy path), it takes a REAL,
captured run_results artifact and deliberately perturbs it, then asserts one of
two contracts holds:

  - ROBUSTNESS mutations break the shape of the artifact (truncate a string,
    drop a field, null out compiled_code, flip a status, inject unicode). The
    contract: the tool must DEGRADE, never raise. Concretely here, classify()
    must return either a known classifier class or None -- never an exception.

  - DETECTION mutations inject a *known fault signature* into the error message
    (a contract violation, a compilation error, a timeout, a data error, a
    plain database error). The contract: the classifier dispatch must LOCALIZE
    that fault -- classify() must return exactly the classifier we injected.
    This is the part that proves dbt-diagnostics actually finds the planted bug,
    not just that it does not crash.

Determinism: exploration is random (a fresh seed visits a different sequence of
mutations), but every run is fully REPRODUCIBLE from its seed. The engine
records the seed and the ordered list of mutations it applied, so a failure in
CI can be replayed exactly by re-running with the same seed. This is the
"non-deterministic in exploration, deterministic in reproduction" model.

Pure standard library + the package under test: no pytest, no Hypothesis. That
keeps it runnable as a plain script for environments that cannot install the
test extras, and importable from the pytest chaos tier.

The injected signatures are kept in sync with the `matches()` methods in
dbt_diagnostics/classifiers/*. If a classifier's signature changes, update
KNOWN_SIGNATURES here and the detection tests will keep them honest.
"""

from __future__ import annotations

import copy
import json
import random
from dataclasses import dataclass, field
from typing import Callable, Optional


# Error-message signatures that each classifier keys on. These mirror the
# `matches()` methods in dbt_diagnostics/classifiers/ exactly. The registry
# dispatch order (contract -> compilation -> timeout -> data -> runtime) means
# a message must carry ONLY the target signature to be unambiguous, so each
# template below avoids accidentally embedding a higher-precedence signature.
KNOWN_SIGNATURES: dict[str, str] = {
    "contract_violation": (
        "Compilation Error in model orders (models/orders.sql)\n"
        "  This model has an enforced contract that failed.\n"
        "  Columns with data_type mismatch: total_amount"
    ),
    # NOTE: contract precedes compilation in the registry; the contract phrase
    # wins even though "Compilation Error" is present. That ordering is exactly
    # what we want to lock, so this template intentionally contains both.
    "compilation_error": (
        "Compilation Error in model stg_orders (models/staging/stg_orders.sql)\n"
        "  Model 'model.shop.stg_orders' depends on a node named 'missing' "
        "which was not found"
    ),
    "timeout_error": (
        "Database Error in model big_agg (models/marts/big_agg.sql)\n"
        "  000630 (57014): Statement reached its statement or warehouse timeout "
        "of 120 second(s) and was canceled."
    ),
    "data_error": (
        "Database Error in model revenue (models/marts/revenue.sql)\n"
        "  100132 (22000): Numeric value '9e99' is out of range"
    ),
    "runtime_error": (
        "Database Error in model stg_x (models/staging/stg_x.sql)\n"
        "  002003 (42S02): SQL compilation error:\n"
        "  Object 'DB.SCHEMA.MISSING' does not exist or not authorized."
    ),
}

# Mutations that should leave the artifact classifiable as None (no signature).
_NO_SIGNATURE_MESSAGE = (
    "Some unstructured failure text with no recognizable Snowflake error code "
    "and nothing the registry keys on."
)


@dataclass
class Expectation:
    """What the harness asserts after a mutation is applied."""

    # "robust": classify() must not raise (returns a class or None).
    # "detect": classify() must return exactly `expected_class`.
    mode: str
    expected_class: Optional[str] = None


@dataclass
class Mutation:
    """A single named perturbation plus the contract it must satisfy."""

    name: str
    apply: Callable[[dict, random.Random], dict]
    expectation: Expectation


def _first_result(artifact: dict) -> Optional[dict]:
    results = artifact.get("results") if isinstance(artifact, dict) else None
    if isinstance(results, list) and results:
        first = results[0]
        return first if isinstance(first, dict) else None
    return None


# --------------------------------------------------------------------------
# Robustness mutations: break the shape; the tool must degrade, never raise.
# --------------------------------------------------------------------------

def _mut_truncate_message(artifact: dict, rng: random.Random) -> dict:
    r = _first_result(artifact)
    if r is not None and isinstance(r.get("message"), str):
        msg = r["message"]
        cut = rng.randint(0, max(0, len(msg) - 1))
        r["message"] = msg[:cut]
    return artifact


def _mut_drop_message(artifact: dict, rng: random.Random) -> dict:
    r = _first_result(artifact)
    if r is not None:
        r.pop("message", None)
    return artifact


def _mut_null_compiled_code(artifact: dict, rng: random.Random) -> dict:
    r = _first_result(artifact)
    if r is not None:
        r["compiled_code"] = None
    return artifact


def _mut_message_to_none(artifact: dict, rng: random.Random) -> dict:
    r = _first_result(artifact)
    if r is not None:
        r["message"] = None
    return artifact


def _mut_inject_unicode(artifact: dict, rng: random.Random) -> dict:
    r = _first_result(artifact)
    if r is not None:
        r["message"] = "\u0000\ufffd embedded NUL and replacement chars \U0001f4a5"
    return artifact


def _mut_flip_status(artifact: dict, rng: random.Random) -> dict:
    r = _first_result(artifact)
    if r is not None:
        r["status"] = rng.choice(["success", "skipped", "pass", "", "weird"])
    return artifact


def _mut_drop_adapter_response(artifact: dict, rng: random.Random) -> dict:
    r = _first_result(artifact)
    if r is not None:
        r.pop("adapter_response", None)
    return artifact


def _mut_empty_results(artifact: dict, rng: random.Random) -> dict:
    if isinstance(artifact, dict):
        artifact["results"] = []
    return artifact


# --------------------------------------------------------------------------
# Detection mutations: inject a known fault; dispatch must localize it.
# --------------------------------------------------------------------------

def _make_inject_signature(target_class: str) -> Callable[[dict, random.Random], dict]:
    def _apply(artifact: dict, rng: random.Random) -> dict:
        r = _first_result(artifact)
        if r is not None:
            r["status"] = "error"
            r["message"] = KNOWN_SIGNATURES[target_class]
        return artifact

    return _apply


def _mut_strip_signature(artifact: dict, rng: random.Random) -> dict:
    r = _first_result(artifact)
    if r is not None:
        r["message"] = _NO_SIGNATURE_MESSAGE
    return artifact


def build_mutation_catalog() -> list[Mutation]:
    """All mutations the engine can draw from, with their contracts."""
    robustness = [
        Mutation("truncate_message", _mut_truncate_message, Expectation("robust")),
        Mutation("drop_message", _mut_drop_message, Expectation("robust")),
        Mutation("null_compiled_code", _mut_null_compiled_code, Expectation("robust")),
        Mutation("message_to_none", _mut_message_to_none, Expectation("robust")),
        Mutation("inject_unicode", _mut_inject_unicode, Expectation("robust")),
        Mutation("flip_status", _mut_flip_status, Expectation("robust")),
        Mutation("drop_adapter_response", _mut_drop_adapter_response, Expectation("robust")),
        Mutation("empty_results", _mut_empty_results, Expectation("robust")),
    ]
    detection = [
        Mutation(
            f"inject_{cls}",
            _make_inject_signature(cls),
            Expectation("detect", expected_class=cls),
        )
        for cls in KNOWN_SIGNATURES
    ]
    detection.append(
        Mutation("strip_signature", _mut_strip_signature, Expectation("detect", None))
    )
    return robustness + detection


@dataclass
class ChaosResult:
    """The outcome of one engine run, enough to replay it exactly."""

    seed: int
    applied: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


class ChaosEngine:
    """
    Seeded failure-injection driver.

    Give it a base artifact and a seed; it deep-copies the artifact, picks a
    mutation at random, applies it, and checks the mutation's contract against
    classify(). Every run is reproducible from its seed.
    """

    def __init__(self, classify_fn: Callable[[str], object], seed: Optional[int] = None):
        self._classify = classify_fn
        self.seed = random.randrange(2**31) if seed is None else seed
        self._rng = random.Random(self.seed)
        self._catalog = build_mutation_catalog()

    def _check(self, mutation: Mutation, artifact: dict) -> Optional[str]:
        """Return a failure description, or None if the contract held."""
        r = _first_result(artifact)
        message = ""
        if r is not None and isinstance(r.get("message"), str):
            message = r["message"]
        try:
            result = self._classify(message)
        except Exception as exc:  # noqa: BLE001 - the whole point is to catch any raise
            return f"{mutation.name}: classify() raised {type(exc).__name__}: {exc}"

        exp = mutation.expectation
        if exp.mode == "robust":
            # Any non-raising outcome (a class or None) satisfies robustness.
            return None
        # detection mode
        got = getattr(result, "error_class", None) if result is not None else None
        if exp.expected_class is None:
            if result is not None:
                return (
                    f"{mutation.name}: expected no classifier (unknown) but got "
                    f"{got!r}"
                )
            return None
        if got != exp.expected_class:
            return (
                f"{mutation.name}: expected class {exp.expected_class!r} but got "
                f"{got!r}"
            )
        return None

    def run(self, base_artifact: dict, rounds: int = 50) -> ChaosResult:
        """Apply `rounds` random mutations to fresh copies of base_artifact."""
        result = ChaosResult(seed=self.seed)
        for _ in range(rounds):
            mutation = self._rng.choice(self._catalog)
            artifact = copy.deepcopy(base_artifact)
            try:
                mutated = mutation.apply(artifact, self._rng)
            except Exception as exc:  # noqa: BLE001
                result.applied.append(mutation.name)
                result.failures.append(
                    f"{mutation.name}: mutation itself raised "
                    f"{type(exc).__name__}: {exc}"
                )
                continue
            result.applied.append(mutation.name)
            failure = self._check(mutation, mutated)
            if failure:
                result.failures.append(failure)
        return result


def load_artifact(path) -> dict:
    with open(path) as f:
        return json.load(f)
