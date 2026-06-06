"""
dbt_diagnostics/classifiers/__init__.py

Classifier registry. Import all classifier classes here; the dispatcher
in main.py iterates CLASSIFIER_REGISTRY to find the right handler.
"""

from dbt_diagnostics.classifiers.base import BaseClassifier, DiagnosticContext
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
