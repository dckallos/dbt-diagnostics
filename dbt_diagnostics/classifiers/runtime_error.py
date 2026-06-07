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
from dbt_diagnostics.tracers.snippet import extract_snippet


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
# Extract the fully-qualified object name from "Object/Schema/Table/View/Database 'X' does not exist"
_OBJECT_NAME_RE = re.compile(
    r"(Object|Schema|Table|View|Database) '([^']+)' does not exist"
)
# Extract the identifier name from "invalid identifier 'X'"
_IDENTIFIER_RE = re.compile(r"invalid identifier '([^']+)'")
# Extract object type + name from privilege errors
_PRIVILEGE_RE = re.compile(
    r"Insufficient privileges to operate on (\w+) '([^']+)'"
)
# Extract the specific required privilege from "must have X granted on Y Z"
_REQUIRED_PRIVILEGE_RE = re.compile(
    r"must have ([\w ]+?) granted on (\w+) ([\w.]+)"
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
            if finding is None:
                # Drift evidence found -- delegate to SchemaChangeErrorClassifier
                from dbt_diagnostics.classifiers.schema_change_error import (
                    SchemaChangeErrorClassifier,
                )
                delegate = SchemaChangeErrorClassifier(
                    result=self.result, context=self.context
                )
                return delegate.diagnose()
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
        4. Schema/database not accessible (shared database, missing IMPORTED PRIVILEGES)
        """
        match = _OBJECT_NAME_RE.search(self.message)
        if match:
            object_type = match.group(1).lower()  # "object", "schema", "table", etc.
            object_name = match.group(2)
        else:
            object_type = "object"
            object_name = "UNKNOWN"

        # Check if this object is a known node in the manifest
        is_known_ref = self._is_known_manifest_object(object_name)

        # Check if it's a parent that may have failed
        parents = self.context.dag_walker.get_parents(self.unique_id)
        parent_failed = self._check_parent_references_object(parents, object_name)

        # Build location
        model_path = self.context.dag_walker.get_model_path(self.unique_id)
        location = TraceLocation(file_path=model_path)

        # Try to find which line references this object in compiled SQL
        line_num = None
        if self.compiled_code:
            line_num = self._find_object_line(object_name)
            if line_num:
                location.line_number = line_num

        # Build compiled snippet
        snippet = None
        if self.compiled_code and line_num:
            snippet = extract_snippet(self.compiled_code, line_num)

        # Build lineage trail for the missing object
        lineage_trail = self.context.dag_walker.trace_object_lineage(
            self.unique_id,
            object_name,
            run_results=self.context.run_results,
        )

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
        elif object_type == "schema":
            # Schema-level "does not exist" typically means a shared/system
            # database whose grants are missing (e.g. SNOWFLAKE.ACCOUNT_USAGE)
            parts = object_name.split(".")
            db_name = parts[0] if parts else object_name
            explanation = (
                f"Schema '{object_name}' does not exist or is not authorized. "
                f"This typically means the database '{db_name}' requires "
                f"IMPORTED PRIVILEGES or the executing role lacks USAGE on "
                f"the schema."
            )
            fix = (
                f"Grant access to the shared database:\n"
                f"GRANT IMPORTED PRIVILEGES ON DATABASE {db_name} "
                f"TO ROLE <your_transformer_role>;\n"
                f"Or verify the schema exists: "
                f"SHOW SCHEMAS LIKE '{parts[-1] if len(parts) > 1 else object_name}' "
                f"IN DATABASE {db_name};"
            )
        elif object_type == "database":
            explanation = (
                f"Database '{object_name}' does not exist or is not authorized. "
                f"The executing role may lack USAGE on this database."
            )
            fix = (
                f"Grant access: GRANT USAGE ON DATABASE {object_name} "
                f"TO ROLE <your_transformer_role>;\n"
                f"Or verify it exists: SHOW DATABASES LIKE '{object_name}';"
            )
        else:
            explanation = (
                f"{object_type.capitalize()} '{object_name}' is NOT declared "
                f"in the manifest. "
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

        # Use object_type in the summary for clarity
        summary_label = object_type.capitalize() if object_type != "object" else "Object"
        return DiagnosticFinding(
            summary=f"{summary_label} not found: {object_name}",
            location=location,
            explanation=explanation,
            fix_suggestion=fix,
            target_object=object_name,
            compiled_snippet=snippet,
            lineage_trail=lineage_trail,
        )

    def _diagnose_invalid_identifier(self) -> Optional[DiagnosticFinding]:
        """
        Invalid identifier (000904).

        The column name referenced in SQL doesn't exist in the source table.
        Common causes: column renamed upstream, typo, case sensitivity.

        When find_column_origin() finds the column declared in an upstream
        manifest node, this is schema drift -- delegate to
        SchemaChangeErrorClassifier for a richer diagnosis. Returns None
        in that case (the caller must check and use the delegated report).
        """
        match = _IDENTIFIER_RE.search(self.message)
        identifier = match.group(1) if match else "UNKNOWN"

        # Check if this identifier appears in any parent's columns
        upstream_origin = self.context.dag_walker.find_column_origin(
            self.unique_id, identifier
        )

        if upstream_origin:
            # Drift evidence found -- delegate to SchemaChangeErrorClassifier
            # which produces a more specific "schema_change_error" report.
            return None

        # No drift evidence: typo or removed column with no manifest trace
        location = self._extract_location()

        # Build compiled snippet around the error line
        snippet = None
        if self.compiled_code and location.line_number:
            snippet = extract_snippet(self.compiled_code, location.line_number)

        # Build column lineage trail
        lineage_trail = self.context.dag_walker.trace_column_lineage(
            self.unique_id,
            identifier,
            run_results=self.context.run_results,
        )

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

        return DiagnosticFinding(
            summary=f"Invalid identifier: {identifier}",
            location=location,
            upstream_origin=None,
            explanation=explanation,
            fix_suggestion=fix,
            target_identifier=identifier,
            compiled_snippet=snippet,
            lineage_trail=lineage_trail,
        )

    def _diagnose_permission_denied(self) -> DiagnosticFinding:
        """
        Insufficient privileges (003001).

        The role running dbt doesn't have the necessary grants.
        Snowflake 003001 messages always state the exact required privilege
        in the form "must have X granted on Y Z".
        """
        match = _PRIVILEGE_RE.search(self.message)
        if match:
            obj_type = match.group(1)
            obj_name = match.group(2)
        else:
            obj_type = "object"
            obj_name = "UNKNOWN"

        # Extract the specific required privilege (e.g. "CREATE VIEW")
        priv_match = _REQUIRED_PRIVILEGE_RE.search(self.message)
        if priv_match:
            required_privilege = priv_match.group(1).upper()
            priv_obj_type = priv_match.group(2).upper()
            priv_fq_name = priv_match.group(3)
        else:
            required_privilege = None
            priv_obj_type = obj_type.upper()
            priv_fq_name = obj_name

        model_path = self.context.dag_walker.get_model_path(self.unique_id)
        location = TraceLocation(file_path=model_path)

        # Try to find the line referencing the object
        line_num = None
        if self.compiled_code:
            line_num = self._find_object_line(obj_name)
            if line_num:
                location.line_number = line_num

        # Build compiled snippet
        snippet = None
        if self.compiled_code and line_num:
            snippet = extract_snippet(self.compiled_code, line_num)

        # Build object lineage trail
        lineage_trail = self.context.dag_walker.trace_object_lineage(
            self.unique_id,
            obj_name,
            run_results=self.context.run_results,
        )

        if required_privilege:
            explanation = (
                f"The role executing this model lacks {required_privilege} "
                f"on {priv_obj_type.lower()} '{priv_fq_name}'. "
                f"This is a GRANT issue, not a code bug."
            )
            fix = (
                f"Grant the required privilege:\n"
                f"GRANT {required_privilege} ON {priv_obj_type} {priv_fq_name} "
                f"TO ROLE <your_transformer_role>;\n"
                f"Or verify current grants:\n"
                f"SHOW GRANTS ON {priv_obj_type} {priv_fq_name};"
            )
        else:
            explanation = (
                f"The role executing this model lacks privileges on "
                f"{obj_type} '{obj_name}'. "
                f"This is a GRANT issue, not a code bug."
            )
            fix = (
                f"Grant access to the executing role:\n"
                f"GRANT USAGE ON {obj_type.upper()} {obj_name} "
                f"TO ROLE <your_transformer_role>;\n"
                f"Or verify current grants:\n"
                f"SHOW GRANTS ON {obj_type.upper()} {obj_name};"
            )

        return DiagnosticFinding(
            summary=f"Insufficient privileges on {obj_type} {obj_name}",
            location=location,
            explanation=explanation,
            fix_suggestion=fix,
            compiled_snippet=snippet,
            lineage_trail=lineage_trail,
        )

    def _diagnose_generic(self) -> DiagnosticFinding:
        """Fallback for unrecognized Database Error subtypes."""
        model_path = self.context.dag_walker.get_model_path(self.unique_id)
        location = TraceLocation(file_path=model_path)

        # Try to extract line/position from error message
        line_match = _LINE_POS_RE.search(self.message)
        snippet = None
        if line_match:
            line_num = int(line_match.group(1))
            position = int(line_match.group(2))
            location.line_number = line_num
            if self.compiled_code:
                snippet = extract_snippet(
                    self.compiled_code, line_num, error_position=position
                )

        return DiagnosticFinding(
            summary=f"Database error in {self.unique_id}",
            location=location,
            explanation=self.message[:500],
            compiled_snippet=snippet,
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
