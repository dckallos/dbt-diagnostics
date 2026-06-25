from __future__ import annotations

import io
import tarfile
import zipfile

import pytest

from conftest import load_codex_script


check_dist = load_codex_script("check_dist")


def _write_artifacts(dist_dir, *, forbidden: bool = False) -> None:
    wheel = dist_dir / "dbt_diagnostics-0.5.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("dbt_diagnostics/__init__.py", "")
        archive.writestr("dbt_diagnostics/templates/report.j2", "")
        archive.writestr("dbt_diagnostics-0.5.0.dist-info/METADATA", "Name: dbt-diagnostics\n")
        archive.writestr("dbt_diagnostics-0.5.0.dist-info/entry_points.txt", "")

    members = [
        ("dbt_diagnostics-0.5.0/pyproject.toml", b"[project]\n"),
        ("dbt_diagnostics-0.5.0/dbt_diagnostics/__init__.py", b""),
    ]
    if forbidden:
        members.append(
            ("dbt_diagnostics-0.5.0/.codex/README.md", b"not for distribution")
        )

    sdist = dist_dir / "dbt_diagnostics-0.5.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        for name, content in members:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


def test_validate_accepts_minimal_safe_artifacts(tmp_path) -> None:
    _write_artifacts(tmp_path)
    check_dist.validate(tmp_path)


def test_validate_rejects_codex_files_in_sdist(tmp_path) -> None:
    _write_artifacts(tmp_path, forbidden=True)
    with pytest.raises(SystemExit, match="forbidden path"):
        check_dist.validate(tmp_path)
