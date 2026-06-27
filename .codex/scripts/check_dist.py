#!/usr/bin/env python3
"""Validate built package artifacts without importing the package under test."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.triage import repo_config


FORBIDDEN_PARTS = {
    ".codex",
    ".git",
    ".github",
    ".venv",
    "__pycache__",
}
FORBIDDEN_PREFIXES = (
    "scripts/governance/",
    "scripts/triage/",
)


def _normalize(name: str) -> str:
    return str(PurePosixPath(name.replace("\\", "/")))


def validate_member_names(names: Iterable[str], artifact: Path) -> list[str]:
    normalized = [_normalize(name) for name in names if name]
    errors: list[str] = []

    for name in normalized:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"unsafe path in {artifact.name}: {name}")
            continue
        if FORBIDDEN_PARTS.intersection(path.parts):
            errors.append(f"forbidden path in {artifact.name}: {name}")
        if any(name.startswith(prefix) or f"/{prefix}" in name for prefix in FORBIDDEN_PREFIXES):
            errors.append(f"governance/triage source leaked into {artifact.name}: {name}")

    return errors


def _wheel_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


def _sdist_names(path: Path) -> list[str]:
    with tarfile.open(path, mode="r:gz") as archive:
        return archive.getnames()


def validate(
    dist_dir: Path, *, repo_policy: repo_config.RepoPolicy | None = None
) -> None:
    active_policy = repo_policy or repo_config.load_repo_policy()
    required_wheel_suffixes = active_policy.product.dist.required_wheel_suffixes
    required_sdist_suffixes = active_policy.product.dist.required_sdist_suffixes
    if not required_wheel_suffixes and not required_sdist_suffixes:
        print("SKIP: no package artifact suffix requirements configured")
        return
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    errors: list[str] = []

    if len(wheels) != 1:
        errors.append(f"expected exactly one wheel, found {len(wheels)}")
    if len(sdists) != 1:
        errors.append(f"expected exactly one sdist, found {len(sdists)}")

    for wheel in wheels:
        names = _wheel_names(wheel)
        errors.extend(validate_member_names(names, wheel))
        for suffix in required_wheel_suffixes:
            if not any(name.endswith(suffix) for name in names):
                errors.append(f"wheel is missing required member ending in {suffix}")

    for sdist in sdists:
        names = _sdist_names(sdist)
        errors.extend(validate_member_names(names, sdist))
        for suffix in required_sdist_suffixes:
            if not any(name.endswith("/" + suffix) or name == suffix for name in names):
                errors.append(f"sdist is missing required member ending in {suffix}")

    if errors:
        raise SystemExit("package artifact validation failed:\n- " + "\n- ".join(errors))

    print(f"validated {wheels[0].name} and {sdists[0].name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist_dir", type=Path)
    args = parser.parse_args()
    validate(args.dist_dir.resolve())


if __name__ == "__main__":
    main()
