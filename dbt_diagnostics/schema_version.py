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

# Parses the leading "major.minor" out of a metadata.dbt_version string.
_DBT_VERSION_RE = re.compile(r"\s*(\d+)\.(\d+)")

# Coarse, best-effort mapping of an artifact schema major to the dbt 1.x minor
# RANGE it co-occurs with. Used ONLY for the cross-artifact skew note when
# metadata.dbt_version is absent on one or both artifacts. Unknown majors map to
# nothing (-> no note, never a false positive). Ranges (not points) because a
# single run-results major spans several dbt minors; divergence is reported only
# when the two ranges are disjoint, so co-occurring versions never flag.
# This table is historical (dbt 1.0-1.7); from manifest v12 the major froze and
# evolves additively, so it does not grow per future release.
_OPEN_MINOR = 999
_MAJOR_TO_DBT_MINOR_RANGE: dict[str, dict[int, tuple[int, int]]] = {
    # manifest major -> (low, high) dbt 1.x minor
    "manifest": {
        4: (0, 0), 5: (1, 1), 6: (2, 2), 7: (3, 3), 8: (4, 4),
        9: (5, 5), 10: (6, 6), 11: (7, 7), 12: (8, _OPEN_MINOR),
    },
    # run-results major -> (low, high) dbt 1.x minor
    "run-results": {
        4: (0, 7), 5: (8, 9), 6: (10, _OPEN_MINOR),
    },
}


@dataclass
class ArtifactVersion:
    """The detected schema identity of a single dbt artifact."""

    kind: str = "unknown"            # "manifest" | "run-results" | "unknown"
    schema_major: Optional[int] = None
    schema_url: Optional[str] = None
    dbt_version: Optional[str] = None
    supported: bool = False
    note: Optional[str] = None

    @property
    def dbt_minor(self) -> Optional[tuple[int, int]]:
        """Leading (major, minor) parsed from dbt_version, or None. Never raises."""
        if not isinstance(self.dbt_version, str):
            return None
        m = _DBT_VERSION_RE.match(self.dbt_version)
        if not m:
            return None
        try:
            return (int(m.group(1)), int(m.group(2)))
        except (TypeError, ValueError):
            return None

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
class VersionSkew:
    """
    Cross-artifact version comparison for a run_results + manifest pair.

    A diagnosis can mix artifacts from different dbt versions (real under
    `dbt build --defer --state path/` or multi-invocation workflows): the
    deferred manifest can originate from an older build than the live
    run_results. Correlating fields across such a pair can silently misalign,
    so we surface a note. Detection is best-effort and never fatal.
    """

    diverged: bool = False
    source: str = "unknown"  # "dbt_version" | "schema_major" | "unknown"
    run_results_signal: Optional[str] = None
    manifest_signal: Optional[str] = None
    note: Optional[str] = None

    def to_json_dict(self) -> dict:
        return {
            "diverged": self.diverged,
            "source": self.source,
            "run_results_signal": self.run_results_signal,
            "manifest_signal": self.manifest_signal,
            "note": self.note,
        }


def _ranges_disjoint(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """True when two inclusive (low, high) minor ranges do not overlap."""
    return a[1] < b[0] or b[1] < a[0]


def _compute_skew(
    run_results: ArtifactVersion, manifest: ArtifactVersion
) -> VersionSkew:
    """
    Compare the two artifacts' dbt lines. Never raises.

    Prefers metadata.dbt_version (the fine-grained signal); falls back to a
    coarse schema-major -> dbt-minor-range table only when dbt_version is
    absent. Unknown majors yield no note (never a false positive).
    """
    rr_minor = run_results.dbt_minor
    man_minor = manifest.dbt_minor

    # Primary: both artifacts carry a parseable dbt_version.
    if rr_minor is not None and man_minor is not None:
        diverged = rr_minor != man_minor
        rr_sig = f"{rr_minor[0]}.{rr_minor[1]}"
        man_sig = f"{man_minor[0]}.{man_minor[1]}"
        note = None
        if diverged:
            note = (
                f"manifest from dbt {man_sig} but run_results from dbt {rr_sig} "
                "-- likely a --defer/state run; cross-artifact correlation may "
                "be approximate"
            )
        return VersionSkew(
            diverged=diverged,
            source="dbt_version",
            run_results_signal=rr_sig,
            manifest_signal=man_sig,
            note=note,
        )

    # Fallback: coarse schema-major ranges, only when both majors are mapped.
    rr_range = _MAJOR_TO_DBT_MINOR_RANGE.get("run-results", {}).get(
        run_results.schema_major
    )
    man_range = _MAJOR_TO_DBT_MINOR_RANGE.get("manifest", {}).get(
        manifest.schema_major
    )
    if rr_range is not None and man_range is not None:
        diverged = _ranges_disjoint(rr_range, man_range)
        rr_sig = f"v{run_results.schema_major}"
        man_sig = f"v{manifest.schema_major}"
        note = None
        if diverged:
            note = (
                f"manifest schema {man_sig} and run_results schema {rr_sig} come "
                "from different dbt release lines -- likely a --defer/state run; "
                "cross-artifact correlation may be approximate"
            )
        return VersionSkew(
            diverged=diverged,
            source="schema_major",
            run_results_signal=rr_sig,
            manifest_signal=man_sig,
            note=note,
        )

    # Not enough information to compare: stay silent.
    return VersionSkew(diverged=False, source="unknown")


@dataclass
class CompatibilityReport:
    """Combined schema identity for a run_results + manifest pair."""

    run_results: ArtifactVersion = field(default_factory=ArtifactVersion)
    manifest: ArtifactVersion = field(default_factory=ArtifactVersion)

    @property
    def all_supported(self) -> bool:
        return self.run_results.supported and self.manifest.supported

    @property
    def skew(self) -> VersionSkew:
        """Cross-artifact version comparison (computed; never raises)."""
        return _compute_skew(self.run_results, self.manifest)

    @property
    def notes(self) -> list[str]:
        """Human-readable notes for any artifact that is not validated."""
        out = []
        for art in (self.run_results, self.manifest):
            if art.note:
                out.append(art.note)
        skew_note = self.skew.note
        if skew_note:
            out.append(skew_note)
        return out

    def to_json_dict(self) -> dict:
        return {
            "run_results": self.run_results.to_json_dict(),
            "manifest": self.manifest.to_json_dict(),
            "all_supported": self.all_supported,
            "skew": self.skew.to_json_dict(),
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
