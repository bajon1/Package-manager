import pytest
import z3

from src.knowledge_base import KnowledgeBase
from src.model import PackageVersion, Repository, Requirement, Version, parse_alternative


V = Version.parse


def make_version(package, version, requires=(), conflicts=()):
    return PackageVersion(
        package, V(version),
        tuple(parse_alternative(text) for text in requires),
        tuple(Requirement.parse(text) for text in conflicts),
    )


def check_state(kb, installed, requests=()):
    solver = z3.Solver()
    solver.add([axiom.formula for axiom in kb.axioms])
    selected = {(package, V(version)) for package, version in installed}
    solver.add([variable == (key in selected) for key, variable in kb.x.items()])
    solver.add([kb.request_axiom(Requirement.parse(text)).formula for text in requests])
    return solver.check()


@pytest.mark.parametrize("installed, expected", [
    ([], z3.sat),
    ([("lib", "1")], z3.sat),
    ([("lib", "2")], z3.sat),
    ([("lib", "1"), ("lib", "2")], z3.unsat),
])
def test_at_most_one_version(installed, expected):
    kb = KnowledgeBase(Repository([
        make_version("lib", "1"), make_version("lib", "2"),
    ]))
    assert check_state(kb, installed) == expected


@pytest.mark.parametrize("installed, expected", [
    ([("app", "1")], z3.unsat),
    ([("app", "1"), ("lib", "1")], z3.unsat),
    ([("app", "1"), ("lib", "2")], z3.sat),
    ([("app", "1"), ("lib", "3")], z3.unsat),
    ([("lib", "2")], z3.sat),
    ([("app", "2")], z3.sat),
])
def test_dependency_uses_installed_version_and_all_constraints(installed, expected):
    kb = KnowledgeBase(Repository([
        make_version("app", "1", requires=["lib >=2 <3"]),
        make_version("app", "2"),
        make_version("lib", "1"), make_version("lib", "2"), make_version("lib", "3"),
    ]))
    assert check_state(kb, installed) == expected


@pytest.mark.parametrize("dependencies, expected", [
    ([], z3.unsat),
    ([("fast", "1")], z3.sat),
    ([("slow", "1")], z3.unsat),
    ([("slow", "2")], z3.sat),
    ([("fast", "1"), ("slow", "2")], z3.sat),
])
def test_dependency_alternatives(dependencies, expected):
    kb = KnowledgeBase(Repository([
        make_version("app", "1", requires=["fast | slow >=2"]),
        make_version("fast", "1"),
        make_version("slow", "1"), make_version("slow", "2"),
    ]))
    assert check_state(kb, [("app", "1"), *dependencies]) == expected


def test_all_dependency_groups_are_required():
    kb = KnowledgeBase(Repository([
        make_version("app", "1", requires=["lib", "fast | slow"]),
        make_version("lib", "1"), make_version("fast", "1"), make_version("slow", "1"),
    ]))
    assert check_state(kb, [("app", "1"), ("fast", "1")]) == z3.unsat
    assert check_state(kb, [("app", "1"), ("lib", "1")]) == z3.unsat
    assert check_state(kb, [("app", "1"), ("lib", "1"), ("slow", "1")]) == z3.sat


@pytest.mark.parametrize("requirement", ["ghost", "lib >=9"])
def test_missing_candidates_prevent_installation(requirement):
    kb = KnowledgeBase(Repository([
        make_version("app", "1", requires=[requirement]), make_version("lib", "1"),
    ]))
    assert check_state(kb, [("app", "1")]) == z3.unsat
    assert check_state(kb, []) == z3.sat


def test_missing_alternative_does_not_block_available_alternative():
    kb = KnowledgeBase(Repository([
        make_version("app", "1", requires=["ghost | lib >=2"]), make_version("lib", "2"),
    ]))
    assert check_state(kb, [("app", "1"), ("lib", "2")]) == z3.sat


@pytest.mark.parametrize("installed, expected", [
    ([("legacy", "1")], z3.sat),
    ([("legacy", "1"), ("lib", "1")], z3.sat),
    ([("legacy", "1"), ("lib", "2")], z3.unsat),
    ([("legacy", "1"), ("lib", "3")], z3.unsat),
    ([("legacy", "2"), ("lib", "2")], z3.sat),
    ([("lib", "2")], z3.sat),
])
def test_one_sided_conflict_excludes_every_matching_version(installed, expected):
    kb = KnowledgeBase(Repository([
        make_version("legacy", "1", conflicts=["lib >=2"]),
        make_version("legacy", "2"),
        make_version("lib", "1"), make_version("lib", "2"), make_version("lib", "3"),
    ]))
    assert check_state(kb, installed) == expected


def test_conflict_without_candidates_does_not_prevent_installation():
    kb = KnowledgeBase(Repository([
        make_version("app", "1", conflicts=["ghost", "lib >=9"]), make_version("lib", "1"),
    ]))
    assert check_state(kb, [("app", "1"), ("lib", "1")]) == z3.sat


@pytest.mark.parametrize("installed, requests, expected", [
    ([], ["lib"], z3.unsat),
    ([("lib", "1")], ["lib >=2"], z3.unsat),
    ([("lib", "2")], ["lib >=2"], z3.sat),
    ([("lib", "2")], ["lib >=2", "lib <2"], z3.unsat),
    ([], ["ghost"], z3.unsat),
])
def test_requests(installed, requests, expected):
    kb = KnowledgeBase(Repository([
        make_version("lib", "1"), make_version("lib", "2"),
    ]))
    assert check_state(kb, installed, requests) == expected


def test_empty_repository():
    kb = KnowledgeBase(Repository([]))
    assert kb.x == {}
    assert kb.axioms == []
    assert check_state(kb, []) == z3.sat
    assert check_state(kb, [], ["ghost"]) == z3.unsat
    solver = z3.Solver()
    solver.add(kb.inst("ghost"))
    assert solver.check() == z3.unsat


def test_variables_candidates_and_obsolescence():
    old = make_version("lib", "1")
    new = make_version("lib", "2")
    kb = KnowledgeBase(Repository([old, new]))
    assert set(kb.x) == {("lib", V("1")), ("lib", V("2"))}
    assert kb.var(old).eq(kb.x[("lib", V("1"))])
    assert kb.vars_of("lib") == [kb.var(new), kb.var(old)]
    assert kb.candidates(Requirement.parse("lib >=2")) == [kb.var(new)]
    assert kb.candidates(Requirement.parse("ghost")) == []
    assert kb.obs == {("lib", V("2")): 0, ("lib", V("1")): 1}
    assert z3.is_true(z3.simplify(z3.substitute(kb.inst("lib"), (kb.var(new), z3.BoolVal(True)))))


def test_axiom_labels_and_description():
    kb = KnowledgeBase(Repository([
        make_version("app", "1", requires=["lib >=2"], conflicts=["lib <2"]),
        make_version("lib", "1"), make_version("lib", "2"),
    ]))
    assert {(a.kind, a.label) for a in kb.axioms} == {
        ("A1", "at most one version of package lib"),
        ("A2", "app==1 requires lib >=2"),
        ("A3", "app==1 conflicts with lib <2"),
    }
    description = kb.describe()
    for axiom in kb.axioms:
        assert f"[{axiom.kind}] {axiom.label}:" in description
    request = kb.request_axiom(Requirement.parse("lib >=2"))
    assert request.kind == "REQUEST"
    assert request.label == "request: lib >=2"
