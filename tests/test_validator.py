from copy import deepcopy

import pytest

from src.model import PackageVersion, Repository, Requirement, State, Version, parse_alternative
from src.validator import requirement_satisfied, validate_state


V = Version.parse


@pytest.fixture
def repository():
    return Repository([
        PackageVersion("app", V("1"), (
            parse_alternative("lib >=2 <3"),
            parse_alternative("json-fast | json-slow >=1"),
        )),
        PackageVersion("app", V("2")),
        PackageVersion("lib", V("1")),
        PackageVersion("lib", V("2.5")),
        PackageVersion("json-fast", V("1")),
        PackageVersion("json-slow", V("1")),
        PackageVersion("legacy", V("1"), conflicts=(Requirement.parse("lib >=2"),)),
    ])


@pytest.mark.parametrize("installed, requirement, expected", [
    ({}, "lib", False),
    ({"lib": V("1")}, "lib >=2", False),
    ({"lib": V("2.5")}, "lib >=2 <3", True),
    ({"lib": V("3")}, "lib >=2 <3", False),
    ({"lib": V("1")}, "lib", True),
    ({"lib": V("1.0")}, "lib ==1.0.0", True),
])
def test_requirement_satisfied(installed, requirement, expected):
    assert requirement_satisfied(State(installed), Requirement.parse(requirement)) is expected


def test_empty_state(repository):
    assert validate_state(repository, State()) == []
    assert validate_state(Repository([]), State()) == []


@pytest.mark.parametrize("json_packages", [
    {"json-fast": V("1")},
    {"json-slow": V("1")},
    {"json-fast": V("1"), "json-slow": V("1")},
])
def test_valid_state_and_alternatives(repository, json_packages):
    state = State({"app": V("1"), "lib": V("2.5"), **json_packages})
    assert validate_state(repository, state) == []


@pytest.mark.parametrize("installed, expected", [
    ({"ghost": V("1")}, "ghost==1: version does not exist in the repository"),
    ({"app": V("9")}, "app==9: version does not exist in the repository"),
])
def test_unknown_package_or_version(repository, installed, expected):
    assert validate_state(repository, State(installed)) == [expected]


def test_equivalent_version_exists_in_repository(repository):
    assert validate_state(repository, State({"lib": V("1.0.0")})) == []


@pytest.mark.parametrize("lib_packages", [{}, {"lib": V("1")}])
def test_missing_or_incompatible_dependency(repository, lib_packages):
    state = State({"app": V("1"), "json-slow": V("1"), **lib_packages})
    assert validate_state(repository, state) == [
        "app==1: unsatisfied requirement 'lib >=2 <3'",
    ]


def test_no_alternative_satisfied(repository):
    state = State({"app": V("1"), "lib": V("2.5")})
    assert validate_state(repository, state) == [
        "app==1: unsatisfied requirement 'json-fast | json-slow >=1'",
    ]


def test_dependencies_belong_to_the_installed_version(repository):
    assert validate_state(repository, State({"app": V("2")})) == []


@pytest.mark.parametrize("lib_packages, expected", [
    ({}, []),
    ({"lib": V("1")}, []),
    ({"lib": V("2.5")}, ["legacy==1: conflict 'lib >=2' matches installed lib==2.5"]),
])
def test_one_sided_conflict(repository, lib_packages, expected):
    assert validate_state(repository, State({"legacy": V("1"), **lib_packages})) == expected


def test_optional_requests(repository):
    state = State({"lib": V("2.5")})
    assert validate_state(repository, state) == []
    assert validate_state(repository, state, [Requirement.parse("lib >=2")]) == []
    assert validate_state(repository, state, [
        Requirement.parse("app"), Requirement.parse("lib <2"),
    ]) == [
        "Unsatisfied request 'app'",
        "Unsatisfied request 'lib <2'",
    ]


def test_collects_all_errors_without_changing_inputs(repository):
    state = State({"ghost": V("1"), "legacy": V("1"), "app": V("1"), "lib": V("2.5")}, {"app"})
    requests = [Requirement.parse("tool"), Requirement.parse("lib <2")]
    original_state = deepcopy(state)
    original_versions = {p: list(repository.versions(p)) for p in repository.package_names()}
    original_requests = list(requests)

    assert validate_state(repository, state, requests) == [
        "app==1: unsatisfied requirement 'json-fast | json-slow >=1'",
        "ghost==1: version does not exist in the repository",
        "legacy==1: conflict 'lib >=2' matches installed lib==2.5",
        "Unsatisfied request 'tool'",
        "Unsatisfied request 'lib <2'",
    ]
    assert state == original_state
    assert requests == original_requests
    assert {p: repository.versions(p) for p in repository.package_names()} == original_versions


def test_unknown_installed_version_does_not_stop_other_checks(repository):
    state = State({"app": V("1"), "lib": V("9"), "legacy": V("1")})
    assert validate_state(repository, state) == [
        "app==1: unsatisfied requirement 'lib >=2 <3'",
        "app==1: unsatisfied requirement 'json-fast | json-slow >=1'",
        "legacy==1: conflict 'lib >=2' matches installed lib==9",
        "lib==9: version does not exist in the repository",
    ]


def test_collects_all_missing_dependencies_for_one_package(repository):
    assert validate_state(repository, State({"app": V("1")})) == [
        "app==1: unsatisfied requirement 'lib >=2 <3'",
        "app==1: unsatisfied requirement 'json-fast | json-slow >=1'",
    ]


def test_transitive_dependency_is_checked():
    repository = Repository([
        PackageVersion("app", V("1"), (parse_alternative("lib"),)),
        PackageVersion("lib", V("1"), (parse_alternative("util >=2"),)),
        PackageVersion("util", V("2")),
    ])
    state = State({"app": V("1"), "lib": V("1")})
    assert validate_state(repository, state) == [
        "lib==1: unsatisfied requirement 'util >=2'",
    ]
    state.install("util", V("2"))
    assert validate_state(repository, state) == []


def test_satisfied_circular_dependencies_are_valid():
    repository = Repository([
        PackageVersion("app", V("1"), (parse_alternative("lib"),)),
        PackageVersion("lib", V("1"), (parse_alternative("app"),)),
    ])
    assert validate_state(repository, State({"app": V("1"), "lib": V("1")})) == []


@pytest.mark.parametrize("version, expected", [
    ("1", ["legacy==1: conflict 'lib >=2' matches installed lib==2.5"]),
    ("2", []),
])
def test_conflicts_belong_to_the_installed_version(version, expected):
    repository = Repository([
        PackageVersion("legacy", V("1"), conflicts=(Requirement.parse("lib >=2"),)),
        PackageVersion("legacy", V("2")),
        PackageVersion("lib", V("2.5")),
    ])
    state = State({"legacy": V(version), "lib": V("2.5")})
    assert validate_state(repository, state) == expected
