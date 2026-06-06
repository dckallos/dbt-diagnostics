"""
dbt_diagnostics/classifiers/runtime_error.py

Classifies and diagnoses Snowflake runtime SQL errors that occur during
dbt model execution. Handles:
- Object does not exist (002003)
- Invalid identifier (000904)
- Insufficient privileges (003001)
- Generic SQL compilation/syntax errors (001003)

These errors mean the model compiled (Jinja resolved) but failed at the
Snowflake execution/SQL-compile stage.
"""

import re
from typing import Optional

from dbt_diagnostics.classifiers.base import BaseClassifier, DiagnosticContext
from dbt_diagnostics.models import (
    DiagnosticReport,
    DiagnosticFinding,
    TraceLocation,
    UpstreamOrigin,
)


# Snowflake error code patterns
_OBJECT_NOT_FOUND_RE = re.compile(
    r"(?:002003|Object '([^']+)' does not exist or not authorized)"
)
_INVALID_IDENTIFIER_RE = re.compile(
    r"(?:000904|invalid identifier '([^']+)')"
)
_PERMISSION_DENIED_RE = re.compile(
    r"(?:003001|Insufficient privileges to operate on (\w+) '([^']+)')"
)
_SYNTAX_ERROR_RE = re.compile(
    r"001003.*?SQL compilation error"
)
# Extract line/position from Snowflake error messages
_LINE_POS_RE = re.compile(r"error line (\d+) at position (\d+)")
# Extract the fully-qualified object name from "Object 'X' does not exist"
_OBJECT_NAME_RE = re.compile(r"Object '([^']+)' does not exist")
# Extract the identifier name from "invalid identifier 'X'"
_IDENTIFIER_RE = re.compile(r"invalid identifier '([^']+)'")
# Extract object type + name from privilege errors
_PRIVILEGE_RE = re.compile(
    r"Insufficient privileges to operate on (\w+) '([^']+)'"
)


class RuntimeErrorClassifier(BaseClassifier):
    """
    Diagnoses Snowflake runtime SQL errors.

    Sub-classifies by Snowflake error code and traces the offending
    object/identifier back through the DAG.
    """

    error_class = "runtime_error"

    @classmethod
    def matches(cls, message: str) -> bool:
        return "Database Error" in message

    def diagnose(self) -> DiagnosticReport:
        report = DiagnosticReport(
            unique_id=self.unique_id,
            error_class=self.error_class,
            raw_message=self.message,
        )

        # Sub-classify by error pattern
        if _OBJECT_NOT_FOUND_RE.search(self.message):
            finding = self._diagnose_object_not_found()
        elif _INVALID_IDENTIFIER_RE.search(self.message):
            finding = self._diagnose_invalid_identifier()
        elif _PERMISSION_DENIED_RE.search(self.message):
            finding = self._diagnose_permission_denied()
        else:
            finding = self._diagnose_generic()

        report.findings.append(finding)
        return report

    def _diagnose_object_not_found(self) -> DiagnosticFinding:
        """
        Object does not exist or not authorized (002003).

        Root cause possibilities:
        1. The source table hasn't been created yet (DDL not applied)
        2. The upstream model failed/was skipped (so the ref target is missing)
        3. Permission issue disguised as "does not exist"
        """
        match = _OBJECT_NAME_RE.search(self.message)
        object_name = match.group(1) if match else "UNKNOWN"

        # Check if this object is a known node in the manifest
        is_known_ref = self._is_known_manifest_object(object_name)

        # Check if it's a parent that may have failed
        parents = self.context.dag_walker.get_parents(self.unique_id)
        parent_failed = self._check_parent_references_object(parents, object_name)

        # Build location
        model_path = self.context.dag_walker.get_model_path(self.unique_id)
        location = TraceLocation(file_path=model_path)

        # Try to find which line references this object in compiled SQL
        if self.compiled_code:
            line_num = self._find_object_line(object_name)
            if line_num:
                location.line_number = line_num

        # Build explanation
        if parent_failed:
            explanation = (
                f"Object {object_name} is produced by upstream model "
                f"{parent_failed}. If that model failed or was skipped, "
                f"this table won't exist. Check the upstream error first."
            )
            fix = f"Fix the error in {parent_failed}, then re-run."
        elif is_known_ref:
            explanation = (
                f"Object {object_name} is declared in the manifest but does "
                f"not exist in Snowflake. This usually means the upstream "
                f"model has never been run, or was dropped."
            )
            fix = f"Run the upstream model that produces {object_name}."
        else:
            explanation = (
                f"Object {object_name} is NOT declared in the manifest. "
                f"This could be: (1) a source table whose DDL hasn't been "
                f"applied, (2) a typo in the ref/source name, or (3) a "
                f"permission issue (Snowflake conflates 'not found' with "
                f"'not authorized' in this error)."
            )
            fix = (
                f"Verify the object exists: SHOW TABLES LIKE "
                f"'{object_name.split('.')[-1]}' IN SCHEMA "
                f"{'.'.join(object_name.split('.')[:-1])}; "
                f"If it exists, check GRANTs to the executing role."
            )

        return DiagnosticFinding(
            summary=f"Object not found: {object_name}",
            location=location,
            explanation=explanation,
            fix_suggestion=fix,
        )

    def _diagnose_invalid_identifier(self) -> DiagnosticFinding:
        """
        Invalid identifier (000904).

        The column name referenced in SQL doesn't exist in the source table.
        Common causes: column renamed upstream, typo, case sensitivity.
        """
        match = _IDENTIFIER_RE.search(self.message)
        identifier = match.group(1) if match else "UNKNOWN"

        # Get line/position from error
        location = self._extract_location()

        # Check if this identifier appears in any parent's columns
        upstream_origin = self.context.dag_walker.find_column_origin(
            self.unique_id, identifier
        )

        if upstream_origin:
            explanation = (
                f"Column '{identifier}' was expected from upstream model "
                f"{upstream_origin['model']}, but it doesn't exist there. "
                f"The column may have been renamed or removed upstream."
            )
            fix = (
                f"Check the current columns in {upstream_origin['model']} "
                f"and update this model's SQL to use the correct name."
            )
            upstream = UpstreamOrigin(
                model_id=upstream_origin["model"],
                file_path=upstream_origin.get("file"),
            )
        else:
            explanation = (
                f"Column '{identifier}' does not exist in the source table(s). "
                f"Common causes: typo in column name, column was renamed "
                f"upstream, or case-sensitivity mismatch (Snowflake folds "
                f"unquoted identifiers to UPPERCASE)."
            )
            fix = (
                f"Check available columns: DESCRIBE TABLE <source>; "
                f"Snowflake identifiers are case-sensitive when quoted."
            )
            upstream = None

        return DiagnosticFinding(
            summary=f"Invalid identifier: {identifier}",
            location=location,
            upstream_origin=upstream,
            explanation=explanation,
            fix_suggestion=fix,
        )

    def _diagnose_permission_denied(self) -> DiagnosticFinding:
        """
        Insufficient privileges (003001).

        The role running dbt doesn't have the necessary grants.
        """
        match = _PRIVILEGE_RE.search(self.message)
        if match:
            obj_type = match.group(1)
            obj_name = match.group(2)
        else:
            obj_type = "object"
            obj_name = "UNKNOWN"

        model_path = self.context.dag_walker.get_model_path(self.unique_id)
        location = TraceLocation(file_path=model_path)

        explanation = (
            f"The role executing this model lacks privileges on "
            f"{obj_type} '{obj_name}'. "
            f"This is a GRANT issue, not a code bug."
        )
        fix = (
            f"Grant access to the executing role:\n"
            f"GRANT SELECT ON {obj_type.upper()} {obj_name} "
            f"TO ROLE <your_transformer_role>;\n"
            f"Or verify current grants:\n"
            f"SHOW GRANTS ON {obj_type.upper()} {obj_name};"
        )

        return DiagnosticFinding(
            summary=f"Insufficient privileges on {obj_type} {obj_name}",
            location=location,
            explanation=explanation,
            fix_suggestion=fix,
        )

    def _diagnose_generic(self) -> DiagnosticFinding:
        """Fallback for unrecognized Database Error subtypes."""
        model_path = self.context.dag_walker.get_model_path(self.unique_id)
        location = TraceLocation(file_path=model_path)

        return DiagnosticFinding(
            summary=f"Database error in {self.unique_id}",
            location=location,
            explanation=self.message[:500],
        )

    def _extract_location(self) -> TraceLocation:
        """Extract file path and error line/position from the message."""
        model_path = self.context.dag_walker.get_model_path(self.unique_id)
        location = TraceLocation(file_path=model_path)

        match = _LINE_POS_RE.search(self.message)
        if match:
            location.line_number = int(match.group(1))
        return location

    def _is_known_manifest_object(self, fq_object_name: str) -> bool:
        """Check if an object (by its FQ Snowflake name) maps to a manifest node."""
        # relation_name in manifest nodes is like "ARTWORK_DB.SILVER.STG_MET__ARTWORKS"
        target = fq_object_name.upper()
        for node in self.context.dag_walker.nodes.values():
            relation = (node.get("relation_name") or "").upper()
            if relation == target:
                return True
        # Also check sources
        for source in self.context.dag_walker.sources.values():
            relation = (source.get("relation_name") or "").upper()
            if relation == target:
                return True
        return False

    def _check_parent_references_object(
        self, parent_ids: list[str], object_name: str
    ) -> Optional[str]:
        """Check if any parent produces the missing object (by relation_name)."""
        target = object_name.upper()
        for pid in parent_ids:
            node = self.context.dag_walker.get_node(pid)
            if node:
                relation = (node.get("relation_name") or "").upper()
                if relation == target:
                    return pid
        return None

    def _find_object_line(self, object_name: str) -> Optional[int]:
        """Find which line in compiled SQL references the missing object."""
        target = object_name.upper()
        for i, line in enumerate(self.compiled_code.splitlines(), start=1):
            if target in line.upper():
                return i
        return None
