"""
dbt_diagnostics/models.py

Structured output types for the diagnostic tool. Classifiers return these
instead of printing directly, allowing main.py to choose the renderer
(human-readable, JSON, CI-friendly).
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ColumnMismatch:
    """One column-level mismatch within a contract violation."""
    column_name: str
    definition_type: str
    contract_type: str
    mismatch_reason: str


@dataclass
class TraceLocation:
    """Where in the source a problem originates."""
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    cte_name: Optional[str] = None
    expression: Optional[str] = None


@dataclass
class UpstreamOrigin:
    """If a column is inherited from an upstream model."""
    model_id: str
    file_path: Optional[str] = None


@dataclass
class ColumnInfo:
    """A column as reported by DESCRIBE TABLE."""
    name: str
    data_type: str


@dataclass
class EnrichmentData:
    """
    Live-queried facts from Snowflake that ground the explanation.
    Populated by the enricher layer when --live is passed.
    None when running offline.
    """
    actual_param_values: dict[str, str] = field(default_factory=dict)
    actual_columns: list[ColumnInfo] = field(default_factory=list)
    object_exists: Optional[bool] = None
    matched_query_text: Optional[str] = None
    matched_error_message: Optional[str] = None
    matched_error_code: Optional[str] = None


@dataclass
class DiagnosticFinding:
    """
    One actionable finding within a diagnostic report.
    A single error can produce multiple findings (e.g., one per mismatched column).
    """
    summary: str
    location: Optional[TraceLocation] = None
    upstream_origin: Optional[UpstreamOrigin] = None
    explanation: Optional[str] = None
    fix_suggestion: Optional[str] = None
    session_params_to_check: list[str] = field(default_factory=list)
    diagnostic_params: list[str] = field(default_factory=list)
    enrichment: Optional[EnrichmentData] = None


@dataclass
class DiagnosticReport:
    """
    The full diagnostic output for one error result from run_results.json.
    Returned by each classifier's diagnose() method.
    """
    unique_id: str
    error_class: str
    raw_message: str
    findings: list[DiagnosticFinding] = field(default_factory=list)
    skipped_downstream: list[str] = field(default_factory=list)
    cascade_note: Optional[str] = None

    @property
    def has_findings(self) -> bool:
        return len(self.findings) > 0
