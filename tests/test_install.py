
import itertools
import json
import random
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.knowledge_base import KnowledgeBase
from src.model import Requirement
from src.parser import load_repository
from src.solver import install


def consistent(repo, assignment):
    for package, version in assignment.items():
        pv = next(p for p in repo.versions(package) if p.version == version)
        for alternative in pv.requires:
            if not any(r.package in assignment and r.matches(assignment[r.package])
                       for r in alternative):
                return False
        for c in pv.conflicts:
            if c.package in assignment and c.matches(assignment[c.package]):
                return False
    return True


def satisfies(requests, assignment):
    return all(r.package in assignment and r.matches(assignment[r.package]) for r in requests)


def criteria(repo, requests, assignment):
    req_pkgs = {r.package for r in requests}
    obs = lambda p: repo.obsolescence(p, assignment[p])
    return (sum(obs(p) for p in assignment if p in req_pkgs),
            len(assignment),
            sum(obs(p) for p in assignment if p not in req_pkgs))


def brute_force(repo, requests):
    names = repo.package_names()
    options = [[None] + [pv.version for pv in repo.versions(p)] for p in names]
    best = None
    for combo in itertools.product(*options):
        assignment = {p: v for p, v in zip(names, combo) if v is not None}
        if consistent(repo, assignment) and satisfies(requests, assignment):
            value = criteria(repo, requests, assignment)
            if best is None or value < best:
                best = value
    return best


def random_repo_file(rng, n_packages):
    names = [f"p{i}" for i in range(n_packages)]
    packages = {}
    for name in names:
        versions = {}
        for v in range(rng.randint(1, 3)):
            details = {}
            others = [n for n in names if n != name]
            if others and rng.random() < 0.7:
                details["requires"] = [
                    " | ".join(f"{o}{rng.choice(['', ' >=1.1', ' <1.2', ' ==1.0'])}"
                               for o in rng.sample(others, rng.randint(1, min(2, len(others)))))
                    for _ in range(rng.randint(1, 2))]
            if others and rng.random() < 0.4:
                details["conflicts"] = [f"{rng.choice(others)}{rng.choice(['', ' >=1.1', ' <1.2'])}"]
            versions[f"1.{v}"] = details
        packages[name] = {"versions": versions}
    return names, {"packages": packages}


def test_against_brute_force():
    rng = random.Random(2026)
    checked = unsat = 0
    for _ in range(150):
        names, doc = random_repo_file(rng, rng.randint(2, 5))
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(doc, f)
        repo = load_repository(f.name)
        requests = [Requirement.parse(n) for n in rng.sample(names, rng.randint(1, 2))]
        expected = brute_force(repo, requests)
        solution = install(KnowledgeBase(repo), requests)
        if expected is None:
            assert solution is None
            unsat += 1
        else:
            assert solution is not None
            assignment = dict(solution.state.installed)
            assert consistent(repo, assignment) and satisfies(requests, assignment)
            assert criteria(repo, requests, assignment) == expected
        checked += 1
    print(f"ok: {checked} repositories, including {unsat} without a solution")


def test_repo_100():
    t0 = time.perf_counter()
    repo = load_repository(Path(__file__).resolve().parent.parent / "repo_100.json")
    kb = KnowledgeBase(repo)
    t1 = time.perf_counter()
    print(f"\nversions: {len(kb.x)}, axioms: {len(kb.axioms)}, KB time: {t1 - t0:.2f}s")
    for text in ["aiohttp", "boto3 botocore", "pytest", "quartz-cli", "heron-compat",
                 "pebble-compat", "pebble-compat==1.2", "fjord-client", "iris-cli", "nova-api"]:
        requests = [Requirement.parse(t) for t in text.split()]
        s0 = time.perf_counter()
        solution = install(kb, requests)
        dt = time.perf_counter() - s0
        if solution is None:
            print(f"{text:22} no solution ({dt:.2f}s)")
        else:
            assert consistent(repo, dict(solution.state.installed))
            print(f"{text:22} {len(solution.state.installed)} packages, {list(solution.values.values())}, {dt:.2f}s")


if __name__ == "__main__":
    test_against_brute_force()
    test_repo_100()
