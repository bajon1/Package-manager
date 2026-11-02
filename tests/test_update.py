from copy import deepcopy
from itertools import product
from pathlib import Path

import pytest

from src.knowledge_base import KnowledgeBase
from src.model import PackageVersion, Repository, Requirement, State, Version, parse_alternative
from src.parser import load_repository, load_state
from src.validator import validate_state


V = Version.parse


def pv(name, version="1", requires=(), conflicts=()):
    return PackageVersion(name, V(version), tuple(map(parse_alternative, requires)),
                          tuple(map(Requirement.parse, conflicts)))


CASES = [
    ([pv("app"), pv("app", "2", conflicts=("tool",)), pv("tool")],
     State({"app": V("1"), "tool": V("1")}, {"app"}),
     {"app": V("2")}),
    ([pv("app", requires=("lib ==1",)), pv("app", "2", requires=("lib ==2",)),
      pv("lib"), pv("lib", "2"), pv("tool", conflicts=("lib >=2",)), pv("tool", "2")],
     State({"app": V("1"), "lib": V("1"), "tool": V("1")}, {"app"}),
     {"app": V("2"), "lib": V("2"), "tool": V("2")}),
    ([pv("app"), pv("app", "2", requires=("lib >=2 | helper",)), pv("lib"), pv("lib", "2"), pv("helper")],
     State({"app": V("1"), "lib": V("1")}, {"app"}),
     {"app": V("2"), "lib": V("1"), "helper": V("1")}),
    ([pv("app"), pv("app", "2", requires=("lib",)), pv("lib"), pv("lib", "2", requires=("extra",)), pv("extra")],
     State({"app": V("1")}, {"app"}), {"app": V("2"), "lib": V("1")}),
    ([pv("app"), pv("app", "2", requires=("lib",)), pv("lib"), pv("lib", "2")],
     State({"app": V("1")}, {"app"}), {"app": V("2"), "lib": V("2")}),
]


@pytest.mark.parametrize("packages,before,expected", CASES)
def test_update_lexicographic_priorities(packages, before, expected):
    from src.solver import update
    original = deepcopy(before)
    repo = Repository(packages)
    result = update(KnowledgeBase(repo), {"app"}, before)
    assert result.state.installed == expected
    assert result.state.manual == before.manual
    assert before == original
    assert validate_state(repo, result.state) == []


@pytest.mark.parametrize("packages,before,expected", CASES)
def test_update_matches_exhaustive_optimum(packages, before, expected):
    from src.solver import update
    repo = Repository(packages)
    names = repo.package_names()
    selected = {"app"}

    def score(candidate):
        old = before.installed.keys()
        current = candidate.installed.keys()
        def obs(target):
            return sum(repo.obsolescence(p, candidate.installed[p]) for p in target)
        return (obs(selected), len(old - current),
                sum(before.installed[p] != candidate.installed[p] for p in (old & current) - selected),
                len(current - old), obs(current))

    scores = []
    for versions in product(*[[None, *repo.versions(p)] for p in names]):
        candidate = State({p: pv.version for p, pv in zip(names, versions) if pv is not None})
        if (before.manual | selected) <= candidate.installed.keys() and not validate_state(repo, candidate):
            scores.append(score(candidate))
    result = update(KnowledgeBase(repo), selected, before)
    assert score(result.state) == min(scores)
    assert tuple(result.values.values()) == min(scores)


def test_update_preserves_manual_and_selected_automatic_packages():
    from src.solver import update
    repo = Repository([pv("app"), pv("app", "2", conflicts=("tool",)), pv("tool")])
    before = State({"app": V("1"), "tool": V("1")}, {"tool"})
    result = update(KnowledgeBase(repo), {"app"}, before)
    assert result.state == before
    assert result.state.manual == {"tool"}


def test_default_update_targets_all_installed_packages():
    from src.solver import update
    repo = Repository([pv("app"), pv("app", "2"), pv("lib"), pv("lib", "2")])
    before = State({"app": V("1"), "lib": V("1")}, {"app"})
    assert update(KnowledgeBase(repo), None, before).state == State({"app": V("2"), "lib": V("2")}, {"app"})
    assert update(KnowledgeBase(repo), set(), before).state == before
    assert update(KnowledgeBase(repo), None, State()).state == State()


def test_original_update_all_example():
    from src.solver import update
    examples = Path(__file__).resolve().parents[1] / "examples"
    repo = load_repository(examples / "repo_example.json")
    before = load_state(examples / "state_example.txt", repo)
    result = update(KnowledgeBase(repo), None, before)
    assert result.state == State({"app": V("1.0"), "tool": V("1.1"), "lib": V("1.5"),
                                  "json-slow": V("1.0"), "util": V("2.0")}, {"app", "tool"})


def test_update_rejects_uninstalled_targets():
    from src.solver import update
    with pytest.raises(ValueError, match="not installed"):
        update(KnowledgeBase(Repository([pv("app")])), {"app"}, State())


def test_update_verifies_preserved_packages(monkeypatch):
    from src import solver
    repo = Repository([pv("app")])
    monkeypatch.setattr(solver, "solve_lex", lambda *args: solver.Solution(State()))
    with pytest.raises(ValueError, match="app"):
        solver.update(KnowledgeBase(repo), {"app"}, State({"app": V("1")}, {"app"}))
