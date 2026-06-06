"""
dbt_diagnostics/classifiers/registry.py

Classifier registry and dispatch logic.
"""

from dbt_diagnostics.classifiers.base import BaseClassifier
from dbt_diagnostics.classifiers.contract_violation import ContractViolationClassifier
from dbt_diagnostics.classifiers.compilation_error import CompilationErrorClassifier
from dbt_diagnostics.classifiers.timeout_error import TimeoutErrorClassifier
from dbt_diagnostics.classifiers.data_error import DataErrorClassifier
from dbt_diagnostics.classifiers.schema_change_error import SchemaChangeErrorClassifier
from dbt_diagnostics.classifiers.runtime_error import RuntimeErrorClassifier

# Order matters: first match wins. Put more specific classifiers first.
CLASSIFIER_REGISTRY: list[type[BaseClassifier]] = [
    ContractViolationClassifier,
    CompilationErrorClassifier,
    TimeoutErrorClassifier,
    DataErrorClassifier,
    SchemaChangeErrorClassifier,
    RuntimeErrorClassifier,
]


def classify(message: str) -> type[BaseClassifier] | None:
    """Return the classifier class that handles this message, or None."""
    for cls in CLASSIFIER_REGISTRY:
        if cls.matches(message):
            return cls
    return None
