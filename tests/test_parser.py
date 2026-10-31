import json
from pathlib import Path

import pytest

from src.model import Requirement, Version
from src.parser import load_repository


@pytest.fixture
def write_repository(tmp_path):
    def write(data):
        path = tmp_path / "repo.json"
        path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
        return path
    return write


def test_load_repository(write_repository, capsys):
    path = write_repository({
        "meta": {"anything": [1, None]},
        "packages": {
            "App_Name": {"versions": {"1.0": {
                "requires": ["LIB >= 1.0, <2 | other"],
                "conflicts": ["lib >=2"],
            }}},
            "lib": {"versions": {"1.0": {}, "2.0": {}, "1.5": {}}},
            "other": {"versions": {"1": {}}},
        },
    })
    repo = load_repository(path)
    assert sorted(repo.package_names()) == ["app-name", "lib", "other"]
    assert [str(p.version) for p in repo.versions("lib")] == ["2.0", "1.5", "1.0"]
    app = repo.versions("app-name")[0]
    assert app.requires == ((Requirement.parse("lib >=1.0 <2"), Requirement.parse("other")),)
    assert app.conflicts == (Requirement.parse("lib >=2"),)
    assert repo.obsolescence("lib", Version.parse("1.0.0")) == 2
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("data, location", [
    ([], "$"),
    ({}, "packages"),
    ({"packages": [], "meta": {}}, "packages"),
    ({"packages": {}, "extra": 1}, "extra"),
    ({"packages": {"bad name": {"versions": {"1": {}}}}}, "packages['bad name']"),
    ({"packages": {"": {"versions": {"1": {}}}}}, "packages['']"),
    ({"packages": {"app": []}}, "packages['app']"),
    ({"packages": {"app": {}}}, "packages['app'].versions"),
    ({"packages": {"app": {"versions": [], "extra": 1}}}, "packages['app'].extra"),
    ({"packages": {"app": {"versions": []}}}, "packages['app'].versions"),
    ({"packages": {"app": {"versions": {}}}}, "packages['app'].versions"),
    ({"packages": {"app": {"versions": {"1-beta": {}}}}}, "packages['app'].versions['1-beta']"),
    ({"packages": {"app": {"versions": {"1": []}}}}, "packages['app'].versions['1']"),
    ({"packages": {"app": {"versions": {"1": {"extra": 1}}}}}, "packages['app'].versions['1'].extra"),
])
def test_invalid_repository_structure(write_repository, data, location):
    with pytest.raises(ValueError) as error:
        load_repository(write_repository(data))
    assert location in str(error.value)


@pytest.mark.parametrize("field", ["requires", "conflicts"])
@pytest.mark.parametrize("value, suffix", [
    (None, ""), ("lib", ""), ({}, ""), (42, ""),
    ([None], "[0]"), ([{}], "[0]"), ([4], "[0]"),
    (["lib", ""], "[1]"), (["lib =>2"], "[0]"),
    (["lib >=1..0"], "[0]"), (["bad name"], "[0]"),
    (["lib >=1<2"], "[0]"),
    (["lib |"], "[0]"), (["APP_name"], "[0]"),
])
def test_invalid_dependencies(write_repository, field, value, suffix):
    data = {"packages": {"App.Name": {"versions": {"1": {field: value}}}}}
    with pytest.raises(ValueError) as error:
        load_repository(write_repository(data))
    assert f"packages['App.Name'].versions['1'].{field}{suffix}" in str(error.value)


@pytest.mark.parametrize("field, text", [
    ("requires", "lib | app-name >=2"),
    ("conflicts", "lib | other"),
])
def test_invalid_alternatives(write_repository, field, text):
    data = {"packages": {"App.Name": {"versions": {"1": {field: [text]}}}}}
    with pytest.raises(ValueError) as error:
        load_repository(write_repository(data))
    assert f"packages['App.Name'].versions['1'].{field}[0]" in str(error.value)


@pytest.mark.parametrize("text, location", [
    ('{"packages": {}, "packages": {}}', "packages"),
    ('{"packages": {"app": {"versions": {"1": {}}}, "app": {"versions": {"2": {}}}}}', "packages['app']"),
    ('{"packages": {"Foo_Bar": {"versions": {"1": {}}}, "foo-bar": {"versions": {"2": {}}}}}', "packages['foo-bar']"),
    ('{"packages": {"app": {"versions": {"1": {}, "1": {}}}}}', "packages['app'].versions['1']"),
    ('{"packages": {"app": {"versions": {"1.0": {}, "1.0.0": {}}}}}', "packages['app'].versions['1.0.0']"),
    ('{"packages": {"app": {"versions": {}, "versions": {"1": {}}}}}', "packages['app'].versions"),
    ('{"packages": {"app": {"versions": {"1": {"requires": [], "requires": []}}}}}', "packages['app'].versions['1'].requires"),
])
def test_duplicate_keys_and_equivalent_values(write_repository, text, location):
    with pytest.raises(ValueError) as error:
        load_repository(write_repository(text))
    assert location in str(error.value)


def test_json_syntax_error_has_line_and_filename(write_repository):
    path = write_repository('{\n"packages": {\n}\n')
    with pytest.raises(ValueError) as error:
        load_repository(path)
    assert "4" in str(error.value)
    assert "repo.json" in str(error.value)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_non_json_constants_rejected(write_repository, constant):
    with pytest.raises(ValueError):
        load_repository(write_repository('{"packages": {}, "meta": ' + constant + '}'))


def test_empty_repository_is_allowed(write_repository):
    assert load_repository(write_repository({"packages": {}})).package_names() == []


def test_missing_file_has_readable_error(tmp_path):
    with pytest.raises(ValueError) as error:
        load_repository(tmp_path / "missing.json")
    assert "missing.json" in str(error.value)


def test_missing_requirements_warn_without_rejecting_repository(write_repository, capsys):
    data = {"packages": {"app": {"versions": {"1": {"requires": ["ghost", "app-lib >=9"]}}},
                         "app-lib": {"versions": {"1": {}}}}}
    repo = load_repository(write_repository(data))
    assert len(repo.warnings()) == 2
    stderr = capsys.readouterr().err
    assert "ghost" in stderr and "app-lib >=9" in stderr
    assert "app==1" in stderr


@pytest.mark.parametrize("path", sorted((Path(__file__).resolve().parents[1] / "data").glob("repo_*.json")), ids=lambda p: p.name)
def test_supplied_repositories_load(path, capsys):
    repo = load_repository(path)
    assert len(repo.package_names()) == int(path.stem.split("_")[1])
    assert len(capsys.readouterr().err.splitlines()) == len(repo.warnings())
