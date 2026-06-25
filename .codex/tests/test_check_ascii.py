from __future__ import annotations

from conftest import load_codex_script


check_ascii = load_codex_script("check_ascii")


def test_find_violations_reports_first_non_ascii_byte(tmp_path) -> None:
    path = tmp_path / "sample.md"
    path.write_bytes(b"one\ntwo \xc3\xa9\n")

    violations = check_ascii.find_violations([path], tmp_path)

    assert violations == ["sample.md:2:5: non-ASCII byte 0xc3"]


def test_find_violations_accepts_ascii(tmp_path) -> None:
    path = tmp_path / "sample.py"
    path.write_text("print('ok')\n", encoding="ascii")
    assert check_ascii.find_violations([path], tmp_path) == []
