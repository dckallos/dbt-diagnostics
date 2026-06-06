"""
dbt_diagnostics/linters/base.py

Abstract base class for pre-execution linters.
Each linter checks compiled SQL for potential issues before dbt build runs.
"""

from abc import ABC, abstractmethod

from dbt_diagnostics.models import LintFinding


class BaseLinter(ABC):
    """
    Base class for all pre-execution linters.

    Subclasses MUST implement:
        - check_name (class attribute): short identifier like "type_hazard"
        - lint(model_id, compiled_sql, manifest_node) -> list[LintFinding]
    """

    check_name: str = "unknown"

    @abstractmethod
    def lint(
        self,
        model_id: str,
        compiled_sql: str,
        manifest_node: dict,
    ) -> list[LintFinding]:
        """
        Analyze compiled SQL and return any findings.

        Args:
            model_id: The dbt unique_id of the model
            compiled_sql: The compiled SQL text
            manifest_node: The full manifest node dict for this model

        Returns:
            List of LintFinding objects (empty if no issues)
        """
        ...
