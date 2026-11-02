import pytest

from src.model import PackageVersion, Repository, Requirement, State, Version, parse_alternative
from src.parser import load_state


def test_load_state_normalizes_names_and_preserves_manual_markers(tmp_path):
    path = tmp_path / "state.txt"
    path.write_text("# Installed packages\n\nApp_Name 1.0 manual # requested\nlib 2\n", encoding="utf-8")

    assert load_state(path) == State(
        {"app-name": Version.parse("1"), "lib": Version.parse("2")},
        {"app-name"},
    )


@pytest.mark.parametrize("text", ["", "\n # comment\n"])
def test_load_empty_state(tmp_path, text):
    path = tmp_path / "state.txt"
    path.write_text(text, encoding="utf-8")

    assert load_state(str(path)) == State()


@pytest.mark.parametrize("entry", [
    "app", "app 1 automatic", "app 1 manual extra", "app invalid",
    "bad/name 1", "app >=1", "app 1 Manual",
])
def test_load_state_rejects_invalid_entries_with_original_line(tmp_path, entry):
    path = tmp_path / "state.txt"
    path.write_text(f"# comment\n\nlib 1\n{entry}\n", encoding="utf-8")

    with pytest.raises(ValueError) as error:
        load_state(path)

    assert f"{path}: line 4:" in str(error.value)


@pytest.mark.parametrize("second", ["App_Name 1", "app-name 2 manual", "APP.NAME 1.0"])
def test_load_state_rejects_duplicate_normalized_packages(tmp_path, second):
    path = tmp_path / "state.txt"
    path.write_text(f"app-name 1\n{second}\n", encoding="utf-8")

    with pytest.raises(ValueError) as error:
        load_state(path)

    assert f"{path}: line 2:" in str(error.value)
    assert "duplicate" in str(error.value)


def test_load_state_reports_unreadable_file(tmp_path):
    path = tmp_path / "missing.txt"

    with pytest.raises(ValueError) as error:
        load_state(path)

    assert str(path) in str(error.value)
    assert isinstance(error.value.__cause__, OSError)


def test_load_state_reports_invalid_encoding(tmp_path):
    path = tmp_path / "state.txt"
    path.write_bytes(b"app 1\n\xff")

    with pytest.raises(ValueError) as error:
        load_state(path)

    assert str(path) in str(error.value)


def test_load_state_validates_against_repository(tmp_path):
    path = tmp_path / "state.txt"
    path.write_text("app 1 manual\nlib 2\n", encoding="utf-8")
    repo = Repository([
        PackageVersion("app", Version.parse("1"), (parse_alternative("lib >=2"),)),
        PackageVersion("lib", Version.parse("2")),
    ])

    assert load_state(path, repository=repo) == State(
        {"app": Version.parse("1"), "lib": Version.parse("2")}, {"app"},
    )


def test_load_state_reports_all_validation_violations(tmp_path):
    path = tmp_path / "state.txt"
    path.write_text("app 1\nlib 1\nghost 1\n", encoding="utf-8")
    repo = Repository([
        PackageVersion("app", Version.parse("1"), (parse_alternative("lib >=2"),),
                       (Requirement.parse("lib"),)),
        PackageVersion("lib", Version.parse("1")),
    ])

    with pytest.raises(ValueError) as error:
        load_state(path, repository=repo)

    message = str(error.value)
    assert str(path) in message
    assert "unsatisfied requirement 'lib >=2'" in message
    assert "conflict 'lib'" in message
    assert "ghost==1: version does not exist" in message


def test_load_state_checks_versions_even_in_empty_repository(tmp_path):
    path = tmp_path / "state.txt"
    path.write_text("app 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="version does not exist"):
        load_state(path, repository=Repository([]))
