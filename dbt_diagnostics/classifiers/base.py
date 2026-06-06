"""
dbt_diagnostics/classifiers/base.py

Abstract base class for error classifiers. Each classifier:
1. Accepts a run_results error dict + shared context (tracers, paths)
2. Returns a DiagnosticReport (structured data, no side effects)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dbt_diagnostics.models import DiagnosticReport
from dbt_diagnostics.tracers.dag_walker import DagWalker
from dbt_diagnostics.tracers.column_tracer import ColumnTracer


@dataclass
class DiagnosticContext:
    """
    Shared resources available to all classifiers.
    Each classifier uses what it needs and ignores the rest.
    """
    dag_walker: DagWalker
    column_tracer: ColumnTracer
    models_dir: Path
    compiled_dir: Path


class BaseClassifier(ABC):
    """
    Base class for all error classifiers.

    Subclasses MUST implement:
        - error_class (class attribute): short identifier like "contract_violation"
        - matches(message) (classmethod): return True if this classifier handles it
        - diagnose(): return a DiagnosticReport
    """

    error_class: str = "unknown"

    def __init__(self, result: dict, context: DiagnosticContext):
        self.result = result
        self.context = context
        self.unique_id = result.get("unique_id", "unknown")
        self.message = result.get("message", "")
        self.compiled_code = result.get("compiled_code", "")

    @classmethod
    @abstractmethod
    def matches(cls, message: str) -> bool:
        """Return True if this classifier handles the given error message."""
        ...

    @abstractmethod
    def diagnose(self) -> DiagnosticReport:
        """Analyze the error and return a structured report."""
        ...
