"""
dbt_diagnostics/schema_version.py

Auto-detect the dbt artifact schema version from the artifact itself and
report whether the tool has been validated against it. The tool never asks
the user to declare a dbt version: every dbt artifact embeds its own schema
version under metadata.dbt_schema_version (a URL such as
"https://schemas.getdbt.com/dbt/manifest/v12.json"), so the artifact is
self-describing. Asking the user would be redundant and a new failure surface.

Design contract (matches the project scope guard and Definition of Done):
  - Detection is best-effort and NEVER raises. A missing, malformed, or
    unrecognized metadata block degrades to an "unknown" version with a note.
  - On an unvalidated schema version the tool emits a note and keeps going
    (parsing is attempted anyway); it does not fail. This mirrors the
    "degrade to unverified, never crash" rule used by the live probes.

The supported set is intentionally narrow (the versions we have real,
captured golden fixtures for). Widening it is a deliberate act: capture a
golden fixture on the new version, confirm the classifiers parse it, then add
the version here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# Schema versions we have validated against captured golden fixtures.
# Keyed by artifact kind -> set of supported major integers.
# Current ground truth: dbt-core 1.11.x emits manifest v12 and run-results v6.
SUPPORTED_SCHEMAS: dict[str, set[int]] = {
    "manifest": {12},
    "run-results": {6},
}

# Map the artifact's own top-level shape to a kind when metadata is absent.
# run_results.json has a "results" list; manifest.json has "nodes".
_KIND_BY_KEY = (
    ("results", "run-results"),
    ("nodes", "manifest"),
)

_SCHEMA_URL_RE = re.compile(
    r"/dbt/(?P<kind>[a-z_-]+)/v(?P<major>\d+)", re.IGNORECASE
)


@dataclass
class ArtifactVersion:
    """The detected schema identity of a single dbt artifact."""

    kind: str = "unknown"            # "manifest" | "run-results" | "unknown"
    schema_major: Optional[int] = None
    schema_url: Optional[str] = None
    dbt_version: Optional[str] = None
    supported: bool = False
    note: Optional[str] = None

    def to_json_dict(self) -> dict:
        return {
            "kind": self.kind,
            "schema_major": self.schema_major,
            "schema_url": self.schema_url,
            "dbt_version": self.dbt_version,
            "supported": self.supported,
            "note": self.note,
        }


@dataclass
class CompatibilityReport:
    """Combined schema identity for a run_results + manifest pair."""

    run_results: ArtifactVersion = field(default_factory=ArtifactVersion)
    manifest: ArtifactVersion = field(default_factory=ArtifactVersion)

    @property
    def all_supported(self) -> bool:
        return self.run_results.supported and self.manifest.supported

    @property
    def notes(self) -> list[str]:
        """Human-readable notes for any artifact that is not validated."""
        out = []
        for art in (self.run_results, self.manifest):
            if art.note:
                out.append(art.note)
        return out

    def to_json_dict(self) -> dict:
        return {
            "run_results": self.run_results.to_json_dict(),
            "manifest": self.manifest.to_json_dict(),
            "all_supported": self.all_supported,
        }


def _normalize_kind(raw: str) -> str:
    """Map schema-URL kind spellings to our canonical kind."""
    k = raw.lower().replace("_", "-")
    if k in ("run-results", "runresults"):
        return "run-results"
    if k == "manifest":
        return "manifest"
    return "unknown"


def _infer_kind_from_shape(artifact: dict, expected: Optional[str]) -> str:
    """Fallback kind detection from the artifact's own keys."""
    if not isinstance(artifact, dict):
        return expected or "unknown"
    # Only attempt shape-based inference when the caller gave no expectation.
    # When expected is set the caller already knows what artifact this is (e.g.
    # the CLI loaded it as "run-results"); guessing from keys would only
    # introduce false-positive reclassification if a future schema adds a key
    # named "results" or "nodes".
    if expected in ("manifest", "run-results"):
        return expected
    for key, kind in _KIND_BY_KEY:
        if key in artifact:
            return kind
    return "unknown"


def detect_artifact_version(
    artifact: object, expected_kind: Optional[str] = None
) -> ArtifactVersion:
    """
    Detect the schema version of one dbt artifact. Never raises.

    expected_kind ("manifest" | "run-results") is a hint used only when the
    metadata block is missing or unparseable; the embedded schema URL always
    wins when present.
    """
    av = ArtifactVersion()

    if not isinstance(artifact, dict):
        av.kind = expected_kind or "unknown"
        av.note = (
            f"could not detect dbt schema version for {av.kind}: "
            "artifact is not a JSON object; parsing may be approximate"
        )
        return av

    metadata = artifact.get("metadata")
    schema_url = None
    if isinstance(metadata, dict):
        schema_url = metadata.get("dbt_schema_version")
        dbt_version = metadata.get("dbt_version")
        if isinstance(dbt_version, str):
            av.dbt_version = dbt_version
    if isinstance(schema_url, str):
        av.schema_url = schema_url
        m = _SCHEMA_URL_RE.search(schema_url)
        if m:
            av.kind = _normalize_kind(m.group("kind"))
            try:
                av.schema_major = int(m.group("major"))
            except (TypeError, ValueError):
                av.schema_major = None

    # Fall back to shape-based kind detection if the URL was absent/unparseable.
    if av.kind == "unknown":
        av.kind = _infer_kind_from_shape(artifact, expected_kind)

    supported_majors = SUPPORTED_SCHEMAS.get(av.kind, set())
    if av.schema_major is None:
        av.supported = False
        av.note = (
            f"could not detect the {av.kind} schema version "
            "(metadata.dbt_schema_version missing or unrecognized); "
            "parsing may be approximate"
        )
    elif av.schema_major in supported_majors:
        av.supported = True
        av.note = None
    else:
        av.supported = False
        validated = ", ".join(f"v{v}" for v in sorted(supported_majors)) or "none"
        av.note = (
            f"{av.kind} schema v{av.schema_major} has not been validated "
            f"(validated: {validated}); results may be approximate. "
            "Capture a golden fixture on this dbt version to validate it."
        )
    return av


def check_compatibility(
    run_results: object, manifest: object
) -> CompatibilityReport:
    """
    Detect the schema version of a run_results + manifest pair. Never raises.
    Returns a CompatibilityReport whose .notes carry any unvalidated-version
    warnings (empty when both artifacts are on a validated schema).
    """
    return CompatibilityReport(
        run_results=detect_artifact_version(run_results, "run-results"),
        manifest=detect_artifact_version(manifest, "manifest"),
    )
