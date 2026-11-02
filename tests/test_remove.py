from copy import deepcopy
from itertools import product
from pathlib import Path

import pytest

from src.knowledge_base import KnowledgeBase
from src.model import PackageVersion, Repository, Requirement, State, Version, parse_alternative
from src.parser import load_repository, load_state
from src.validator import validate_state


V = Version.parse


def pv(name, version="1", requires=()):
    return PackageVersion(name, V(version), tuple(map(parse_alternative, requires)))


CASES = [
    # Protect an untargeted manual package despite a version change and a new dependency.
    ([pv("app", requires=("lib",)), pv("app", "2", requires=("helper",)), pv("lib"), pv("helper")],
     State({"app": V("1"), "lib": V("1")}, {"app"}), {"app": V("2"), "helper": V("1")}),
    # Avoid changing a retained version even when retaining it needs a new dependency.
    ([pv("app", requires=("lib | helper",)), pv("app", "2"), pv("lib"), pv("helper")],
     State({"app": V("1"), "lib": V("1")}, {"app"}), {"app": V("1"), "helper": V("1")}),
    # Avoid new dependencies before trying to minimize removed automatic packages.
    ([pv("app", requires=("lib | helper",)), pv("lib"), pv("helper")],
     State({"app": V("1"), "lib": V("1")}), {}),
    # Among equal earlier objectives, keep an unrelated automatic package.
    ([pv("lib"), pv("orphan")], State({"lib": V("1"), "orphan": V("1")}), {"orphan": V("1")}),
]


@pytest.mark.parametrize("packages,before,expected", CASES)
def test_removal_priorities(packages, before, expected):
    from src.solver import remove
    original = deepcopy(before)
    repo = Repository(packages)
    result = remove(KnowledgeBase(repo), {"lib"}, before)

    assert result.state.installed == expected
    assert result.state.manual == before.manual & expected.keys()
    assert before == original
    assert validate_state(repo, result.state) == []


@pytest.mark.parametrize("packages,before,expected", CASES)
@pytest.mark.parametrize("autoremove", [False, True])
def test_removal_matches_exhaustive_optimum(packages, before, expected, autoremove):
    from src.solver import remove
    repo = Repository(packages)
    names = repo.package_names()
    targeted = {"lib"}

    def score(candidate):
        old = before.installed.keys()
        current = candidate.installed.keys()
        return (
            len((before.manual - targeted) - current),
            sum(before.installed[p] != candidate.installed[p] for p in old & current),
            len(current - old),
            len(current) if autoremove else len(old - current),
        )

    scores = []
    for versions in product(*[[None, *repo.versions(p)] for p in names]):
        candidate = State({p: pv.version for p, pv in zip(names, versions) if pv is not None})
        if not targeted & candidate.installed.keys() and not validate_state(repo, candidate):
            scores.append(score(candidate))
    result = remove(KnowledgeBase(repo), targeted, before, autoremove=autoremove)
    assert score(result.state) == min(scores)
    assert tuple(result.values.values()) == min(scores)


def test_autoremove_preserves_manual_packages_and_required_dependencies():
    from src.solver import remove
    repo = Repository([pv("app", requires=("lib",)), pv("lib"), pv("target"), pv("orphan")])
    before = State({p: V("1") for p in ("app", "lib", "target", "orphan")}, {"app", "target"})
    normal = remove(KnowledgeBase(repo), {"target"}, before)
    automatic = remove(KnowledgeBase(repo), {"target"}, before, autoremove=True)
    assert normal.state == State({p: V("1") for p in ("app", "lib", "orphan")}, {"app"})
    assert automatic.state == State({"app": V("1"), "lib": V("1")}, {"app"})
    assert list(normal.values.values())[:3] == list(automatic.values.values())[:3]


def test_removal_can_downgrade_a_manual_dependent():
    from src.solver import remove
    repo = Repository([pv("app"), pv("app", "2", requires=("lib",)), pv("lib")])
    before = State({"app": V("2"), "lib": V("1")}, {"app"})
    assert remove(KnowledgeBase(repo), {"lib"}, before).state == State({"app": V("1")}, {"app"})


@pytest.mark.parametrize("targeted", [set(), {"unknown"}])
def test_removing_nothing_or_unknown_package_is_a_no_op(targeted):
    from src.solver import remove
    repo = Repository([pv("app")])
    before = State({"app": V("1")}, {"app"})
    assert remove(KnowledgeBase(repo), targeted, before).state == before
    assert remove(KnowledgeBase(Repository([])), targeted, State()).state == State()


@pytest.mark.parametrize("targeted,autoremove,expected,manual", [
    ({"lib"}, False, {"json-slow": "1.0"}, set()),
    ({"tool"}, True, {"app": "1.0", "lib": "1.0"}, {"app"}),
])
def test_instructor_removal_examples(targeted, autoremove, expected, manual):
    from src.solver import remove
    examples = Path(__file__).resolve().parents[1] / "examples"
    repo = load_repository(examples / "repo_example.json")
    before = load_state(examples / "state_example.txt", repo)
    result = remove(KnowledgeBase(repo), targeted, before, autoremove=autoremove)
    assert result.state == State({p: V(v) for p, v in expected.items()}, manual)
    assert validate_state(repo, result.state) == []


def test_removal_rejects_invalid_initial_state():
    from src.solver import remove
    with pytest.raises(ValueError, match="Invalid initial state"):
        remove(KnowledgeBase(Repository([])), {"ghost"}, State({"ghost": V("1")}))


def test_removal_verifies_consistency_and_absence_of_targets(monkeypatch):
    from src import solver
    repo = Repository([pv("app"), pv("lib")])
    monkeypatch.setattr(solver, "solve_lex", lambda *args: solver.Solution(State({"lib": V("1"), "ghost": V("1")})))
    with pytest.raises(ValueError) as error:
        solver.remove(KnowledgeBase(repo), {"lib"}, State())
    assert "lib" in str(error.value)
    assert "ghost" in str(error.value)


def test_load_package_names_accepts_only_names_and_comments(tmp_path):
    from src.parser import load_package_names
    path = tmp_path / "remove.txt"
    path.write_text("# packages\nApp_Name # normalized\n\nLIB\napp-name\n", encoding="utf-8")
    assert load_package_names(path) == {"app-name", "lib"}


@pytest.mark.parametrize("text", ["lib >=1", "bad name", "app | tool"])
def test_load_package_names_reports_original_line(tmp_path, text):
    from src.parser import load_package_names
    path = tmp_path / "remove.txt"
    path.write_text(f"# comment\n\n{text}\n", encoding="utf-8")
    with pytest.raises(ValueError) as error:
        load_package_names(path)
    assert f"{path}: line 3:" in str(error.value)
