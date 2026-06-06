"""
dbt_diagnostics/classifiers/contract_violation.py

Classifies and diagnoses dbt model contract violations. Parses the mismatch
table from the error message, then uses the column tracer and DAG walker to
find the root cause (file, line, CTE, expression).
"""

import re
from pathlib import Path
from typing import Optional

from dbt_diagnostics.tracers.dag_walker import DagWalker
from dbt_diagnostics.tracers.column_tracer import ColumnTracer


# Regex for pipe-delimited mismatch table rows
_TABLE_ROW_RE = re.compile(
    r"\|\s*(?P<column_name>\S+)\s*\|"
    r"\s*(?P<definition_type>[^|]*?)\s*\|"
    r"\s*(?P<contract_type>[^|]*?)\s*\|"
    r"\s*(?P<mismatch_reason>[^|]*?)\s*\|"
)
_HEADER_RE = re.compile(r"\|\s*column_name\s*\|", re.IGNORECASE)
_SEPARATOR_RE = re.compile(r"\|\s*-+\s*\|")

# Session params relevant to specific type mismatches
TIMESTAMP_PARAMS = [
    "TIMESTAMP_TYPE_MAPPING",
    "TIMESTAMP_INPUT_FORMAT",
    "TIMESTAMP_OUTPUT_FORMAT",
    "TIMEZONE",
]


def parse_mismatch_table(message: str) -> list[dict]:
    """Extract structured mismatch records from the pipe-delimited error table."""
    records = []
    for line in message.splitlines():
        line = line.strip()
        if _HEADER_RE.search(line) or _SEPARATOR_RE.search(line):
            continue
        match = _TABLE_ROW_RE.search(line)
        if match:
            records.append({
                "column_name": match.group("column_name").strip(),
                "definition_type": match.group("definition_type").strip(),
                "contract_type": match.group("contract_type").strip(),
                "mismatch_reason": match.group("mismatch_reason").strip(),
            })
    return records


class ContractViolationClassifier:
    """Diagnoses a dbt contract violation with full root cause tracing."""

    def __init__(self, result: dict, dag_walker: DagWalker, column_tracer: ColumnTracer):
        self.result = result
        self.dag_walker = dag_walker
        self.column_tracer = column_tracer
        self.unique_id = result.get("unique_id", "unknown")
        self.message = result.get("message", "")
        self.compiled_code = result.get("compiled_code", "")

    def diagnose(self):
        """Run the full diagnosis and print results."""
        mismatches = parse_mismatch_table(self.message)

        if not mismatches:
            print("\n  Could not parse mismatch table from error message.")
            return

        for mismatch in mismatches:
            self._diagnose_single_mismatch(mismatch)

    def _diagnose_single_mismatch(self, mismatch: dict):
        """Diagnose one column mismatch: trace the column, find root cause."""
        col = mismatch["column_name"]
        def_type = mismatch["definition_type"] or "(missing)"
        con_type = mismatch["contract_type"] or "(missing)"
        reason = mismatch["mismatch_reason"]

        print(f"\n  MISMATCH:")
        print(f"    Column:          {col}")
        print(f"    Model produces:  {def_type}")
        print(f"    Contract expects: {con_type}")
        print(f"    Reason:          {reason}")

        # Trace the column through compiled SQL (sqlglot)
        trace_result = None
        if self.compiled_code:
            trace_result = self.column_tracer.trace_column(col, self.compiled_code)

        # Find the source file and line number
        model_path = self.dag_walker.get_model_path(self.unique_id)
        line_number = None
        if model_path:
            # model_path is relative to the dbt project (e.g. "models/marts/dim_artists.sql")
            source_file = self.column_tracer.models_dir.parent / model_path
            line_number = self.column_tracer.find_line_number(source_file, col)

        # Trace upstream to find if column is inherited or introduced here
        upstream_origin = self.dag_walker.find_column_origin(self.unique_id, col)

        # Print ROOT CAUSE
        print(f"\n  ROOT CAUSE:")

        if model_path:
            print(f"    File:       {model_path}")
        if line_number:
            print(f"    Line:       {line_number}")
        if trace_result and trace_result.cte_name:
            print(f"    CTE:        {trace_result.cte_name}")
        if trace_result:
            print(f"    Expression: {trace_result.expression} AS {col.lower()}")

        # Explain WHY the type mismatch occurs
        print()
        if trace_result and trace_result.is_function_call:
            self._explain_function_type(trace_result, def_type, con_type)
        elif reason == "missing in definition":
            print(f"    The contract declares {col} but the model SQL does not produce it.")
        elif reason == "missing in contract":
            print(f"    The model SQL produces {col} but the contract does not declare it.")

        # Report origin (inherited vs introduced here)
        if upstream_origin:
            print(f"\n    This column is INHERITED from: {upstream_origin['model']}")
            if upstream_origin["file"]:
                print(f"    Upstream file: {upstream_origin['file']}")
        else:
            print(f"\n    This column is INTRODUCED in this model (not inherited from upstream).")

        # Session params to check (if timestamp-related)
        if "TIMESTAMP" in def_type or "TIMESTAMP" in con_type:
            print(f"\n  SESSION PARAMS TO VERIFY:")
            for param in TIMESTAMP_PARAMS:
                print(f"    SHOW PARAMETERS LIKE '{param}' IN ACCOUNT;")

    def _explain_function_type(self, trace_result, def_type: str, con_type: str):
        """Explain why a function call produces an unexpected type."""
        expr = trace_result.expression

        if "CURRENT_TIMESTAMP" in expr.upper():
            print(f"    CURRENT_TIMESTAMP() returns TIMESTAMP_LTZ by default in Snowflake.")
            print(f"    The account parameter TIMESTAMP_TYPE_MAPPING controls this.")
            print(f"    The contract expects {con_type}.")
            print()
            print(f"    To fix, cast explicitly in the model SQL:")
            print(f"      CURRENT_TIMESTAMP()::TIMESTAMP_NTZ AS {trace_result.column_name.lower()}")
        elif "SYSDATE" in expr.upper():
            print(f"    SYSDATE() returns TIMESTAMP_LTZ in Snowflake.")
        else:
            print(f"    The expression `{expr}` produces {def_type}.")
            print(f"    The contract expects {con_type}.")
