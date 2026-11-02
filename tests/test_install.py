from copy import deepcopy
from itertools import product

import pytest
import z3

from src.knowledge_base import KnowledgeBase
from src.model import PackageVersion, Repository, Requirement, State, Version, parse_alternative
from src.solver import install
from src.validator import validate_state


V = Version.parse


def pv(name, version="1", requires=(), conflicts=()):
    return PackageVersion(name, V(version), tuple(map(parse_alternative, requires)),
                          tuple(map(Requirement.parse, conflicts)))


def solve(packages, requests, state=None):
    repo = Repository(packages)
    return install(KnowledgeBase(repo), map(Requirement.parse, requests), state=state)


def test_install_preserves_existing_packages_and_manual_flags():
    before = State({"app": V("1"), "lib": V("1"), "unused": V("1")}, {"app"})
    original = deepcopy(before)
    result = solve([
        pv("app", requires=("lib",)), pv("lib"), pv("lib", "2"), pv("unused"),
        pv("new", requires=("lib",)),
    ], ["new", "lib"], before)

    assert result.state == State({**before.installed, "new": V("1")}, {"app", "new", "lib"})
    assert before == original


PRIORITY_CASES = [
    # Keep a package even when that requires a version change.
    ([pv("app", requires=("lib >=2",)), pv("lib"), pv("lib", "2"),
      pv("tool", conflicts=("lib >=2",)), pv("tool", "2")],
     State({"tool": V("1")}, {"tool"}), ["app"],
     {"tool": V("2"), "app": V("1"), "lib": V("2")}),
    # Keeping an existing version outranks freshness of a new request.
    ([pv("app"), pv("app", "2", requires=("lib >=2",)), pv("lib"), pv("lib", "2")],
     State({"lib": V("1")}), ["app"], {"lib": V("1"), "app": V("1")}),
    # Freshness of a new request outranks the number of newly installed packages.
    ([pv("app"), pv("app", "2", requires=("lib",)), pv("lib"), pv("keep")],
     State({"keep": V("1")}), ["app"], {"keep": V("1"), "app": V("2"), "lib": V("1")}),
    # Fewer new packages outranks freshness of a new dependency.
    ([pv("app", requires=("lib",)), pv("lib"), pv("lib", "2", requires=("extra",)),
      pv("extra"), pv("keep")], State({"keep": V("1")}), ["app"],
     {"keep": V("1"), "app": V("1"), "lib": V("1")}),
    # With earlier criteria tied, select the newest other new dependency.
    ([pv("app", requires=("lib",)), pv("lib"), pv("lib", "2"), pv("keep")],
     State({"keep": V("1")}), ["app"],
     {"keep": V("1"), "app": V("1"), "lib": V("2")}),
]


@pytest.mark.parametrize("packages,before,requests,expected", PRIORITY_CASES)
def test_existing_install_optimization_priority(packages, before, requests, expected):
    result = solve(packages, requests, before)

    assert result.state.installed == expected
    assert validate_state(Repository(packages), result.state, map(Requirement.parse, requests)) == []


@pytest.mark.parametrize("packages,before,requests,expected", PRIORITY_CASES)
def test_existing_install_matches_independent_exhaustive_optimum(packages, before, requests, expected):
    repo = Repository(packages)
    parsed = list(map(Requirement.parse, requests))
    requested = {r.package for r in parsed}
    names = repo.package_names()

    def score(state):
        old = set(before.installed)
        new = set(state.installed) - old
        def obs(selected):
            return sum(repo.obsolescence(p, state.installed[p]) for p in selected)
        return (
            len(old - state.installed.keys()),
            sum(before.installed[p] != state.installed[p] for p in old & state.installed.keys()),
            obs(new & requested), len(new), obs(new - requested),
        )

    scores = []
    for versions in product(*[[None, *repo.versions(p)] for p in names]):
        candidate = State({p: version.version for p, version in zip(names, versions) if version is not None})
        if not validate_state(repo, candidate, parsed):
            scores.append(score(candidate))

    result = install(KnowledgeBase(repo), parsed, state=before)
    assert score(result.state) == min(scores)


def test_empty_initial_state_preserves_original_objectives():
    repo = Repository([pv("app"), pv("app", "2", requires=("lib",)), pv("lib")])
    requests = [Requirement.parse("app")]
    original = install(KnowledgeBase(repo), requests)
    explicit = install(KnowledgeBase(repo), requests, state=State())

    assert explicit == original
    assert explicit.state == State({"app": V("2"), "lib": V("1")}, {"app"})


def test_existing_requested_package_stays_at_its_old_version_unless_constrained():
    result = solve([pv("app"), pv("app", "2")], ["app"], State({"app": V("1")}))
    assert result.state == State({"app": V("1")}, {"app"})


def test_install_can_remove_manual_packages_when_request_requires_it():
    result = solve([pv("app", conflicts=("tool",)), pv("tool")], ["app"],
                   State({"tool": V("1")}, {"tool"}))
    assert result.state == State({"app": V("1")}, {"app"})


def test_install_downgrade_preserves_existing_manual_status():
    result = solve([pv("app"), pv("app", "2")], ["app ==1"], State({"app": V("2")}, {"app"}))
    assert result.state == State({"app": V("1")}, {"app"})


def test_unsatisfiable_install_does_not_modify_initial_state():
    before = State({"app": V("1")}, {"app"})
    original = deepcopy(before)
    assert solve([pv("app")], ["app ==1", "app ==2"], before) is None
    assert before == original


def test_invalid_initial_state_reports_all_violations():
    with pytest.raises(ValueError) as error:
        solve([pv("app", requires=("lib",)), pv("lib")], [],
              State({"app": V("1"), "ghost": V("1")}))
    assert "unsatisfied requirement" in str(error.value)
    assert "ghost==1" in str(error.value)


def test_empty_repository_and_requests_produce_empty_state():
    assert solve([], [], State()).state == State()


def test_install_verifies_solver_result(monkeypatch):
    from src import solver
    monkeypatch.setattr(solver, "solve_lex", lambda *args: solver.Solution(State({"ghost": V("1")})))
    with pytest.raises(ValueError) as error:
        solve([pv("app")], ["app"])
    assert "ghost==1" in str(error.value)
    assert "Unsatisfied request" in str(error.value)


def test_unknown_is_not_reported_as_unsatisfiable(monkeypatch):
    monkeypatch.setattr(z3.Optimize, "check", lambda self: z3.unknown)
    monkeypatch.setattr(z3.Optimize, "reason_unknown", lambda self: "test timeout")
    with pytest.raises(RuntimeError, match="test timeout"):
        solve([pv("app")], ["app"])
