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
    # Structured type info from contract violation classifier.
    # Populated directly from parsed mismatch data so reconciliation
    # never has to parse the summary string.
    definition_type: Optional[str] = None
    contract_type: Optional[str] = None
    # Structured fields for enricher consumption (Work Item 4).
    # Populated by classifiers so the enricher never needs to regex-parse
    # the summary string to find the target object or identifier.
    target_object: Optional[str] = None
    target_identifier: Optional[str] = None


@dataclass
class DiffResult:
    """Result of comparing a model against a previous manifest version."""
    node_changed: bool
    changed_lines: list[str] = field(default_factory=list)  # unified diff (max 20)
    upstream_changes: list[dict] = field(default_factory=list)  # [{model_id, change_summary}]
    columns_added: list[str] = field(default_factory=list)
    columns_removed: list[str] = field(default_factory=list)
    columns_type_changed: list[dict] = field(default_factory=list)  # [{name, old_type, new_type}]


@dataclass
class LintFinding:
    """One issue found by pre-execution linting."""
    severity: str  # "warning" or "error"
    check_name: str  # e.g. "type_hazard", "missing_contract_column"
    model_id: str
    file_path: Optional[str]
    line_number: Optional[int]
    message: str
    fix_suggestion: Optional[str] = None

    def to_json_dict(self) -> dict:
        return {
            "severity": self.severity,
            "check_name": self.check_name,
            "model_id": self.model_id,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "message": self.message,
            "fix_suggestion": self.fix_suggestion,
        }


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
    diff: Optional["DiffResult"] = None

    @property
    def has_findings(self) -> bool:
        return len(self.findings) > 0

    def to_json_dict(self) -> dict:
        """
        Produce a stable, versioned JSON representation for CI consumers.
        This schema is documented and will not change without a version bump.
        """
        return {
            "schema_version": "1.0",
            "unique_id": self.unique_id,
            "model_name": self.unique_id.split(".")[-1] if "." in self.unique_id else self.unique_id,
            "error_class": self.error_class,
            "cascade_note": self.cascade_note,
            "findings": [self._finding_to_dict(f) for f in self.findings],
            "skipped_downstream": self.skipped_downstream,
        }

    @staticmethod
    def _finding_to_dict(f: "DiagnosticFinding") -> dict:
        """Convert a finding to a stable dict structure."""
        d: dict = {
            "summary": f.summary,
            "fix_suggestion": f.fix_suggestion,
            "explanation": f.explanation,
            "definition_type": f.definition_type,
            "contract_type": f.contract_type,
            "target_object": f.target_object,
            "target_identifier": f.target_identifier,
        }
        if f.location:
            d["location"] = {
                "file_path": f.location.file_path,
                "line_number": f.location.line_number,
                "cte_name": f.location.cte_name,
                "expression": f.location.expression,
            }
        if f.upstream_origin:
            d["upstream_origin"] = {
                "model_id": f.upstream_origin.model_id,
                "file_path": f.upstream_origin.file_path,
            }
        return d
