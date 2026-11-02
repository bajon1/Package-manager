from pathlib import Path

import pytest

from src.model import Constraint, Requirement, Version
from src.parser import load_requests


def test_load_requests_ignores_comments_and_blank_lines(tmp_path):
    path = tmp_path / "requests.txt"
    path.write_text(
        "# Installation requests\n\n  App_Name >=1, <2  # choose a version\n"
        "  # another comment\nlib\nother !=3\n",
        encoding="utf-8",
    )

    assert load_requests(path) == [
        Requirement("app-name", (
            Constraint(">=", Version.parse("1")),
            Constraint("<", Version.parse("2")),
        )),
        Requirement("lib"),
        Requirement("other", (Constraint("!=", Version.parse("3")),)),
    ]


@pytest.mark.parametrize("text", ["", "\n # only a comment\n\n"])
def test_load_requests_empty_file(tmp_path, text):
    path = tmp_path / "requests.txt"
    path.write_text(text, encoding="utf-8")

    assert load_requests(str(path)) == []


@pytest.mark.parametrize("text", ["lib =>2", "bad name", "lib | other"])
def test_load_requests_reports_filename_and_original_line(tmp_path, text):
    path = tmp_path / "requests.txt"
    path.write_text(f"# comment\n\napp\n{text}\n", encoding="utf-8")

    with pytest.raises(ValueError) as error:
        load_requests(path)

    assert f"{path}: line 4:" in str(error.value)
    assert text in str(error.value)


def test_load_requests_reports_unreadable_file(tmp_path):
    path = tmp_path / "missing.txt"

    with pytest.raises(ValueError) as error:
        load_requests(path)

    assert str(path) in str(error.value)
    assert isinstance(error.value.__cause__, OSError)


def test_load_requests_reports_invalid_utf8(tmp_path):
    path = tmp_path / "requests.txt"
    path.write_bytes(b"app\n\xff")

    with pytest.raises(ValueError) as error:
        load_requests(path)

    assert str(path) in str(error.value)


def test_load_supplied_requests():
    path = Path(__file__).resolve().parents[1] / "data" / "requests_10.txt"

    assert load_requests(path) == [
        Requirement("attrs"), Requirement("filelock"), Requirement("quartz-kit"),
    ]
