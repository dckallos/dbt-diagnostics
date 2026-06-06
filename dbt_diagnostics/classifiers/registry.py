"""
dbt_diagnostics/classifiers/registry.py

Classifier registry and dispatch logic.
"""

from dbt_diagnostics.classifiers.base import BaseClassifier
from dbt_diagnostics.classifiers.contract_violation import ContractViolationClassifier
from dbt_diagnostics.classifiers.runtime_error import RuntimeErrorClassifier

# Order matters: first match wins. Put more specific classifiers first.
CLASSIFIER_REGISTRY: list[type[BaseClassifier]] = [
    ContractViolationClassifier,
    RuntimeErrorClassifier,
]


def classify(message: str) -> type[BaseClassifier] | None:
    """Return the classifier class that handles this message, or None."""
    for cls in CLASSIFIER_REGISTRY:
        if cls.matches(message):
            return cls
    return None
