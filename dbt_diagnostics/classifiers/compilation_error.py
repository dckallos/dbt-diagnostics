"""
dbt_diagnostics/classifiers/compilation_error.py

Classifies and diagnoses dbt Jinja compilation errors. These fail before
any SQL is generated -- the model's Jinja template couldn't render.

Common causes:
  - Undefined variable/macro (typo in ref() or var())
  - Bad ref target (model doesn't exist)
  - Jinja syntax error
"""

import re
from difflib import get_close_matches
from typing import Optional

from dbt_diagnostics.classifiers.base import BaseClassifier, DiagnosticContext
from dbt_diagnostics.models import (
    DiagnosticReport,
    DiagnosticFinding,
    TraceLocation,
)
from dbt_diagnostics.tracers.snippet import extract_snippet


# Regex patterns for common compilation error shapes
_UNDEFINED_RE = re.compile(r"'(\w+)' is undefined", re.IGNORECASE)
_REF_NOT_FOUND_RE = re.compile(
    r"node '([^']+)' which was not found", re.IGNORECASE
)
_DEPENDS_ON_RE = re.compile(
    r"depends on a node named '([^']+)' which was not found", re.IGNORECASE
)
_JINJA_LINE_RE = re.compile(r"line (\d+)")
_MATERIALIZATION_RE = re.compile(
    r"[Mm]odel must use the (\w+) materialization"
)


class CompilationErrorClassifier(BaseClassifier):
    """Diagnoses dbt Jinja compilation errors."""

    error_class = "compilation_error"

    @classmethod
    def matches(cls, message: str) -> bool:
        return "Compilation Error" in message

    def diagnose(self) -> DiagnosticReport:
        """Analyze the compilation error and return a structured report."""
        report = DiagnosticReport(
            unique_id=self.unique_id,
            error_class=self.error_class,
            raw_message=self.message,
        )

        # No compiled_code exists for true Jinja compilation errors (Jinja failed
        # before SQL generation). But if compiled_code is present (edge case),
        # extract a snippet for context.
        snippet = None
        line_match = _JINJA_LINE_RE.search(self.message)
        if self.compiled_code and line_match:
            snippet = extract_snippet(
                self.compiled_code, int(line_match.group(1))
            )

        finding = self._classify_compilation_error()
        finding.compiled_snippet = snippet
        report.findings.append(finding)
        return report

    def _classify_compilation_error(self) -> DiagnosticFinding:
        """Determine the specific type of compilation error."""
        msg = self.message

        # Case 1: Undefined variable or macro
        undef_match = _UNDEFINED_RE.search(msg)
        if undef_match:
            undefined_name = undef_match.group(1)
            return self._diagnose_undefined(undefined_name)

        # Case 2: ref() target not found
        ref_match = _REF_NOT_FOUND_RE.search(msg) or _DEPENDS_ON_RE.search(msg)
        if ref_match:
            target_name = ref_match.group(1)
            return self._diagnose_ref_not_found(target_name)

        # Case 3: Materialization mismatch (package macro enforces a specific materialization)
        mat_match = _MATERIALIZATION_RE.search(msg)
        if mat_match:
            required_mat = mat_match.group(1)
            return self._diagnose_materialization_mismatch(required_mat)

        # Case 4: Generic compilation error (Jinja syntax, etc.)
        return self._diagnose_generic()

    def _diagnose_undefined(self, undefined_name: str) -> DiagnosticFinding:
        """Diagnose an undefined variable/macro error."""
        # Check if it's a known macro name (ref, source, config, var)
        known_macros = {"ref", "source", "config", "var", "this", "adapter"}

        model_path = self.context.dag_walker.get_model_path(self.unique_id)
        location = TraceLocation(file_path=model_path or None)

        # Try to extract line number from the error message
        line_match = _JINJA_LINE_RE.search(self.message)
        if line_match:
            location.line_number = int(line_match.group(1))

        if undefined_name in known_macros:
            explanation = (
                f"'{undefined_name}' is a dbt built-in but is not available in this context. "
                "This usually means the file is not being processed as a dbt model "
                "(check file location and dbt_project.yml model-paths)."
            )
            fix = (
                f"Verify this file is inside a directory listed in model-paths "
                f"in dbt_project.yml. Ensure dbt can find it."
            )
        else:
            explanation = (
                f"The name '{undefined_name}' is not defined. This is either a typo "
                f"in a macro/variable name, or a custom macro that hasn't been imported."
            )
            fix = (
                f"Check spelling of '{undefined_name}'. If it's a custom macro, "
                f"ensure the package providing it is in packages.yml and run `dbt deps`."
            )

        return DiagnosticFinding(
            summary=f"Undefined name: '{undefined_name}'",
            location=location,
            explanation=explanation,
            fix_suggestion=fix,
        )

    def _diagnose_ref_not_found(self, target_name: str) -> DiagnosticFinding:
        """Diagnose a ref() pointing to a non-existent model."""
        model_path = self.context.dag_walker.get_model_path(self.unique_id)
        location = TraceLocation(file_path=model_path or None)

        # Check if the target exists in the manifest (typo vs genuinely missing)
        all_model_names = set()
        for node_id in self.context.dag_walker.nodes:
            parts = node_id.split(".")
            if len(parts) >= 3:
                all_model_names.add(parts[-1])

        # Simple fuzzy check for typos
        suggestions = get_close_matches(target_name, list(all_model_names), n=3, cutoff=0.6)

        if suggestions:
            explanation = (
                f"ref('{target_name}') points to a model that doesn't exist in the project. "
                f"Similar model names found: {', '.join(suggestions)}. This may be a typo."
            )
            fix = f"Did you mean: ref('{suggestions[0]}')?"
        else:
            explanation = (
                f"ref('{target_name}') points to a model that doesn't exist in this project. "
                f"The model may not have been created yet, or it may be in a different package."
            )
            fix = (
                f"Create the model '{target_name}.sql' in your models/ directory, "
                f"or check if you need to add a package dependency."
            )

        return DiagnosticFinding(
            summary=f"Model not found: ref('{target_name}')",
            location=location,
            explanation=explanation,
            fix_suggestion=fix,
        )

    def _diagnose_materialization_mismatch(self, required_mat: str) -> DiagnosticFinding:
        """Diagnose a materialization constraint enforced by a package macro."""
        model_path = self.context.dag_walker.get_model_path(self.unique_id)
        location = TraceLocation(file_path=model_path or None)

        # Extract the macro name from the call stack if present
        macro_match = re.search(r"in macro (\w+)", self.message)
        macro_name = macro_match.group(1) if macro_match else None

        # Extract the model short name
        parts = self.unique_id.split(".")
        model_name = parts[-1] if len(parts) >= 3 else self.unique_id
        package_name = parts[1] if len(parts) >= 3 else "unknown"

        explanation = (
            f"This model requires materialized='{required_mat}' but is configured "
            f"with a different materialization. "
            f"The constraint is enforced by "
            f"{'macro ' + macro_name if macro_name else 'a package macro'} "
            f"in the '{package_name}' package."
        )
        fix = (
            f"Set the materialization for this model to '{required_mat}'. "
            f"In dbt_project.yml, add under models:\n"
            f"  {package_name}:\n"
            f"    +materialized: {required_mat}\n"
            f"Or set it per-model with a config block: "
            f"{{{{ config(materialized='{required_mat}') }}}}"
        )

        return DiagnosticFinding(
            summary=f"Materialization mismatch: requires '{required_mat}'",
            location=location,
            explanation=explanation,
            fix_suggestion=fix,
        )

    def _diagnose_generic(self) -> DiagnosticFinding:
        """Fallback for compilation errors we can't specifically classify."""
        model_path = self.context.dag_walker.get_model_path(self.unique_id)
        location = TraceLocation(file_path=model_path or None)

        line_match = _JINJA_LINE_RE.search(self.message)
        if line_match:
            location.line_number = int(line_match.group(1))

        # Extract the most useful part of the error message
        lines = self.message.strip().splitlines()
        # Usually the last line has the actual error
        detail = lines[-1].strip() if lines else self.message[:200]

        return DiagnosticFinding(
            summary=f"Jinja compilation failed: {detail[:100]}",
            location=location,
            explanation=(
                "The model's Jinja template could not be compiled. "
                "No SQL was generated. Check the source file for syntax errors."
            ),
            fix_suggestion="Review the Jinja syntax at the reported line in the source file.",
        )
