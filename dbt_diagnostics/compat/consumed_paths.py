# Registry of dbt-artifact fields dbt-diagnostics consumes, each with version-aware
# fallbacks and a live-warehouse recovery path (offline file is a hint; the warehouse
# is the source of truth).
"""
The single declarative source for "what we read from dbt artifacts, what to fall back
to across versions, and what the live (Tier A) layer does when the offline value is
missing or None". Both the schema-diff tool (scripts/compat/schema_diff.py) and the
runtime accessors (dbt_diagnostics.compat.safe) consume this registry, so the static
compatibility check and the runtime reader can never silently drift apart.

Adding a NEW dbt version never requires editing this file. It changes only when WE
decide to consume a new field (a product decision) or to add a fallback alias after a
confirmed rename (a rare optimization). See docs/RESEARCH_VERSION_COMPAT_FINDINGS.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConsumedPath:
    """One artifact field the tool reads, plus its cross-version survival strategy."""

    artifact: str                       # "manifest" | "run-results"
    path: str                           # dot-path; "[]" descends into dict values/array items
    fallbacks: tuple[str, ...] = ()     # sibling keys to try if the primary leaf is absent
    nullable_expected: bool = False     # None is a normal value (e.g. seeds/tests relation_name)
    adapter_specific: bool = False      # may be absent on non-Snowflake adapters
    live_recovery: str = ""             # Tier-A recovery when the offline value is missing/None
    classifiers: tuple[str, ...] = field(default_factory=tuple)  # readers (for blast-radius)

    @property
    def leaf(self) -> str:
        """Final path token without a trailing '[]'."""
        tail = self.path.split(".")[-1]
        return tail[:-2] if tail.endswith("[]") else tail

    @property
    def parent_path(self) -> str:
        """Everything up to (not including) the leaf token."""
        return ".".join(self.path.split(".")[:-1])


# The full set of dict paths the classifiers/enrichers read today (grepped from
# dbt_diagnostics/classifiers and dbt_diagnostics/enrichers).
REGISTRY: tuple[ConsumedPath, ...] = (
    # ---- manifest.json ----
    ConsumedPath(
        "manifest", "nodes[].relation_name",
        nullable_expected=True,
        live_recovery="build {database}.{schema}.{alias} from the node, confirm via "
                      "INFORMATION_SCHEMA.TABLES / SHOW OBJECTS",
        classifiers=("runtime_error", "data_error"),
    ),
    ConsumedPath(
        "manifest", "nodes[].compiled_code",
        fallbacks=("compiled_sql",),          # renamed in dbt 1.3 / manifest v7
        nullable_expected=True,               # only populated for executed nodes
        live_recovery="read target/compiled/<original_file_path>; else degrade "
                      "(post-hoc, no recompile)",
        classifiers=("compilation_error", "runtime_error", "test_failure"),
    ),
    ConsumedPath(
        "manifest", "nodes[].raw_code",
        fallbacks=("raw_sql",),               # renamed in dbt 1.3 / manifest v7
        classifiers=("compilation_error",),
    ),
    ConsumedPath(
        "manifest", "nodes[].depends_on.nodes",
        live_recovery="reconstruct edges from query lineage if absent",
        classifiers=("test_failure", "runtime_error"),
    ),
    ConsumedPath(
        "manifest", "nodes[].columns",
        live_recovery="INFORMATION_SCHEMA.COLUMNS for the relation",
        classifiers=("schema_change_error", "contract_violation"),
    ),
    ConsumedPath("manifest", "nodes[].resource_type"),
    ConsumedPath("manifest", "nodes[].unique_id"),
    ConsumedPath("manifest", "nodes[].original_file_path"),
    # ---- run_results.json ----
    ConsumedPath("run-results", "results[].status"),
    ConsumedPath("run-results", "results[].message", nullable_expected=True),
    ConsumedPath("run-results", "results[].timing[].started_at", nullable_expected=True),
    ConsumedPath("run-results", "results[].execution_time"),
    ConsumedPath("run-results", "results[].thread_id"),
    ConsumedPath("run-results", "results[].unique_id"),
    ConsumedPath("run-results", "results[].adapter_response", nullable_expected=True),
    ConsumedPath(
        "run-results", "results[].adapter_response.query_id",
        adapter_specific=True, nullable_expected=True,
        live_recovery="correlate QUERY_HISTORY by (user, warehouse, time-window, "
                      "statement hash) when query_id is missing",
    ),
    ConsumedPath(
        "run-results", "results[].adapter_response.rows_affected",
        adapter_specific=True, nullable_expected=True,
    ),
)


def for_artifact(artifact: str) -> tuple[ConsumedPath, ...]:
    """Registry entries for one artifact kind ('manifest' or 'run-results')."""
    return tuple(cp for cp in REGISTRY if cp.artifact == artifact)
