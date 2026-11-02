import json

import pytest

from src.knowledge_base import KnowledgeBase
from src.parser import load_repository, load_requests, load_state, save_state
from src.solver import install, remove, update
from src.explanations import explain
from src.validator import validate_state


@pytest.fixture
def write_pypi(tmp_path):
    def write(packages, environment=None):
        path = tmp_path / "pypi.json"
        path.write_text(json.dumps({"meta": {"environment": environment or {
            "python_version": "3.11", "python_full_version": "3.11.9", "sys_platform": "linux",
        }}, "packages": packages}), encoding="utf-8")
        return path
    return write


def test_pypi_versions_specifiers_and_python_filtering(write_pypi):
    repo = load_repository(write_pypi({
        "app": {"versions": {"1.0": {"requires_dist": ["lib~=1.2,!=1.3.*"]}}},
        "lib": {"versions": {
            "1.2rc1": {}, "1.2": {}, "1.2.post1": {}, "1.3.1": {},
            "1.9": {"requires_python": ">=3.12"}, "2.0": {},
        }},
    }))
    assert [str(pv.version) for pv in repo.versions("lib")] == ["2.0", "1.3.1", "1.2.post1", "1.2", "1.2rc1"]
    req = repo.versions("app")[0].requires[0][0]
    assert [str(pv.version) for pv in repo.matching(req)] == ["1.2.post1", "1.2"]
    assert repo.parse_requirement("lib >=1.2rc1").matches(repo.parse_version("1.2rc2"))


def test_pypi_markers_use_target_environment_and_ignore_extras(write_pypi):
    repo = load_repository(write_pypi({
        "app": {"versions": {"1": {"requires_dist": [
            'linux-lib[optional]>=1; sys_platform == "linux"',
            'windows-lib; sys_platform == "win32"',
            'extra-lib; extra == "test"',
            'core-lib; extra != "test"',
        ]}}},
        "linux-lib": {"versions": {"1": {}}},
        "core-lib": {"versions": {"1": {}}},
    }))
    requirements = repo.versions("app")[0].requires
    assert [group[0].package for group in requirements] == ["linux-lib", "core-lib"]
    assert repo.environment["sys_platform"] == "linux"
    assert install(KnowledgeBase(repo), [repo.parse_requirement("app[extra]")]).state.manual == {"app"}


def test_pypi_request_and_state_files_use_repository_parsers(write_pypi, tmp_path):
    repo = load_repository(write_pypi({"Foo_Bar": {"versions": {
        "1.0rc1": {"requires_dist": None}, "1.0": {"requires_python": None}, "1!2.0+local": {},
    }}}))
    request_file = tmp_path / "requests.txt"
    request_file.write_text('foo-bar >=1.0rc1, <1.0.post1\nignored; sys_platform == "win32"\n', encoding="utf-8")
    requests = load_requests(request_file, repo)
    assert len(requests) == 1
    solution = install(KnowledgeBase(repo), requests)
    assert str(solution.state.installed["foo-bar"]) == "1.0"
    state_file = tmp_path / "state.txt"
    save_state(solution.state, state_file)
    assert load_state(state_file, repo) == solution.state


def test_all_operations_work_with_imported_data(write_pypi):
    from src.updates import analyze_update
    repo = load_repository(write_pypi({
        "app": {"versions": {"1.0rc1": {"requires_dist": ["lib<2"]}, "2": {"requires_dist": ["lib>=2"]}}},
        "lib": {"versions": {"1": {}, "2": {}}},
    }))
    kb = KnowledgeBase(repo)
    before = install(kb, [repo.parse_requirement("app ==1.0rc1")]).state
    assert validate_state(repo, before) == []
    after = update(kb, None, before).state
    assert str(after.installed["app"]) == "2"
    assert analyze_update(kb, None, before).conflict is None
    assert "app" not in remove(kb, {"lib"}, after).state.installed
    assert explain(kb, [repo.parse_requirement("app==1.0rc1"), repo.parse_requirement("lib>=2")])


def test_all_incompatible_versions_are_removed_and_dependencies_become_unsatisfiable(write_pypi):
    repo = load_repository(write_pypi({
        "app": {"versions": {"1": {"requires_dist": ["lib"]}}},
        "lib": {"versions": {"1": {"requires_python": ">=4"}}},
    }))
    assert repo.versions("lib") == []
    assert install(KnowledgeBase(repo), [repo.parse_requirement("app")]) is None


@pytest.mark.parametrize("details", [
    {"requires_dist": "lib"}, {"requires_dist": [None]},
    {"requires_dist": ["bad =>2"]}, {"requires_python": "nonsense"},
])
def test_invalid_pypi_metadata_has_source_location(write_pypi, details):
    path = write_pypi({"app": {"versions": {"1": details}}})
    with pytest.raises(ValueError) as error:
        load_repository(path)
    assert str(path) in str(error.value)
    assert "versions['1']" in str(error.value)


def test_legacy_format_stays_strict_and_ignores_metadata(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({"meta": {"environment": {"python_version": "0"}}, "packages": {
        "app": {"versions": {"1.0-beta": {}}},
    }}), encoding="utf-8")
    with pytest.raises(ValueError, match="Incorrect version"):
        load_repository(path)


def test_pypi_marker_request_error_keeps_original_line_number(write_pypi, tmp_path):
    repo = load_repository(write_pypi({"app": {"versions": {"1": {"requires_dist": []}}}}))
    path = tmp_path / "requests.txt"
    path.write_text("# test\n\napp =>2\n", encoding="utf-8")
    with pytest.raises(ValueError) as error:
        load_requests(path, repo)
    assert "line 3" in str(error.value)


def test_explicit_pypi_mode_supports_repositories_without_metadata_fields(write_pypi):
    repo = load_repository(write_pypi({"app": {"versions": {"1.0rc1": {}, "1.0": {}}}}), pypi=True)
    assert str(repo.versions("app")[0].version) == "1.0"


def test_pypi_cli_uses_pep_requests_and_state_parsers(write_pypi, tmp_path):
    from src.cli import main
    path = write_pypi({"app": {"versions": {"1.0rc1": {"requires_dist": []}, "1.0": {}}}})
    requests = tmp_path / "requests.txt"
    requests.write_text("app ==1.0rc1\n", encoding="utf-8")
    output = tmp_path / "state.txt"
    assert main(["install", str(requests), "--repo", str(path), "--output", str(output)]) == 0
    assert str(load_state(output, load_repository(path)).installed["app"]) == "1.0rc1"


def test_markers_do_not_fall_back_to_the_host_environment(write_pypi):
    path = write_pypi({"app": {"versions": {"1": {"requires_dist": [
        'lib; sys_platform == "win32"',
    ]}}}, "lib": {"versions": {"1": {}}}}, environment={"python_version": "3.11"})
    with pytest.raises(ValueError, match="target environment.*sys_platform"):
        load_repository(path)


def test_marker_variable_names_inside_quoted_values_are_not_environment_fields(write_pypi):
    path = write_pypi({"app": {"versions": {"1": {"requires_dist": [
        'lib; os_name == "sys_platform"',
    ]}}}, "lib": {"versions": {"1": {}}}}, environment={"python_version": "3.11", "os_name": "posix"})
    assert load_repository(path).versions("app")[0].requires == ()
