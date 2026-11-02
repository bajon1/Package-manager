from itertools import product
import random

import pytest

from src.knowledge_base import KnowledgeBase
from src.model import PackageVersion, Repository, Requirement, Version, parse_alternative
from src.solver import install


V = Version.parse


def pv(name, version="1", requires=(), conflicts=()):
    return PackageVersion(name, V(version), tuple(map(parse_alternative, requires)),
                          tuple(map(Requirement.parse, conflicts)))


def independent_score(repo, selected, requests):
    def matches(requirement):
        version = selected.get(requirement.package)
        return version is not None and requirement.matches(version)
    for package, version in selected.items():
        installed = next(pv for pv in repo.versions(package) if pv.version == version)
        if any(not any(map(matches, alternatives)) for alternatives in installed.requires):
            return None
        if any(map(matches, installed.conflicts)):
            return None
    if not all(map(matches, requests)):
        return None
    requested = {r.package for r in requests}
    requested_obs = other_obs = 0
    for package, version in selected.items():
        newer = sum(pv.version > version for pv in repo.versions(package))
        if package in requested:
            requested_obs += newer
        else:
            other_obs += newer
    return requested_obs, len(selected), other_obs


def assert_exhaustive_optimum(repo, texts):
    requests = list(map(Requirement.parse, texts))
    names = repo.package_names()
    scores = []
    for versions in product(*[[None, *repo.versions(p)] for p in names]):
        selected = {p: pv.version for p, pv in zip(names, versions) if pv is not None}
        score = independent_score(repo, selected, requests)
        if score is not None:
            scores.append(score)
    result = install(KnowledgeBase(repo), requests)
    if not scores:
        assert result is None
    else:
        assert result is not None
        assert independent_score(repo, result.state.installed, requests) == min(scores)
        assert tuple(result.values.values()) == min(scores)
        assert result.state.manual == {r.package for r in requests}


@pytest.mark.parametrize("packages,expected", [
    # Fresh requested version wins even when it needs more dependencies.
    ([pv("app"), pv("app", "2", requires=("lib",)), pv("lib")], {"app": V("2"), "lib": V("1")}),
    # A smaller dependency closure wins over fresher dependencies.
    ([pv("app", requires=("lib",)), pv("lib"), pv("lib", "2", requires=("extra",)), pv("extra")],
     {"app": V("1"), "lib": V("1")}),
    # With the first two objectives tied, choose fresher dependencies.
    ([pv("app", requires=("lib",)), pv("lib"), pv("lib", "2")], {"app": V("1"), "lib": V("2")}),
])
def test_empty_install_lexicographic_priorities(packages, expected):
    repo = Repository(packages)
    result = install(KnowledgeBase(repo), [Requirement.parse("app")])
    assert result.state.installed == expected
    assert_exhaustive_optimum(repo, ["app"])


def test_empty_install_optimality_on_seeded_small_repositories():
    rng = random.Random(2026)
    for _ in range(24):
        packages = []
        for name in ("a", "b", "c"):
            others = [p for p in ("a", "b", "c") if p != name]
            for version in ("1", "2"):
                requires = ()
                if rng.random() < 0.6:
                    requires = (rng.choice(others) + rng.choice(("", " ==1", " >=2")),)
                conflicts = (rng.choice(others) + " >=2",) if rng.random() < 0.4 else ()
                packages.append(pv(name, version, requires, conflicts))
        repo = Repository(packages)
        assert_exhaustive_optimum(repo, rng.sample(["a", "b", "c"], rng.randint(1, 3)))
    assert_exhaustive_optimum(Repository([pv("a")]), ["a ==2"])
    assert_exhaustive_optimum(Repository([pv("a")]), ["a ==1", "a !=1"])
