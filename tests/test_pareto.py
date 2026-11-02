from itertools import product
from pathlib import Path
import json

import pytest
import z3

from src.knowledge_base import KnowledgeBase
from src.model import PackageVersion, Repository, State, Version, parse_alternative
from src.parser import load_repository
from src.validator import validate_state


V = Version.parse


def original_case():
    repo = load_repository(Path(__file__).resolve().parents[1] / "examples/repo_example.json")
    return repo, State({"a": V("1.0"), "b": V("1.0")}, {"a", "b"})


def test_original_frontier_has_both_and_only_nondominated_alternatives():
    from src.updates import analyze_update
    repo, before = original_case()
    analysis = analyze_update(KnowledgeBase(repo), None, before)
    assert analysis.newest == {"a": V("2.0"), "b": V("2.0")}
    assert set(analysis.conflicting_packages) == {"a", "b"}
    assert analysis.conflict
    actual = {(row.state.installed["a"], row.state.installed["b"]) for row in analysis.frontier}
    assert actual == {(V("2.0"), V("1.0")), (V("1.1"), V("2.0"))}
    for row in analysis.frontier:
        assert row.state.manual == {"a", "b"}
        assert validate_state(repo, row.state) == []
    for omit in [None, *range(len(analysis.conflict))]:
        solver = z3.Solver()
        solver.add([a.formula for i, a in enumerate(analysis.conflict) if i != omit])
        assert solver.check() == (z3.unsat if omit is None else z3.sat)


def test_updating_only_a_has_no_conflict():
    from src.updates import analyze_update
    repo, before = original_case()
    analysis = analyze_update(KnowledgeBase(repo), {"a"}, before)
    assert analysis.newest == {"a": V("2.0")}
    assert analysis.conflict is None
    assert analysis.frontier == []


def test_newest_reachable_versions_respect_manual_packages():
    from src.updates import analyze_update
    repo = Repository([
        PackageVersion("a", V("1")),
        PackageVersion("a", V("2"), (parse_alternative("b >=2"),)),
        PackageVersion("b", V("1")),
    ])
    analysis = analyze_update(KnowledgeBase(repo), {"a"}, State({"a": V("1"), "b": V("1")}, {"b"}))
    assert analysis.newest == {"a": V("1")}
    assert analysis.conflict is None


def test_frontier_matches_independent_enumeration_with_unrelated_selected_package():
    from src.updates import analyze_update
    original, _ = original_case()
    repo = Repository([*(pv for p in ("a", "b") for pv in original.versions(p)),
                       PackageVersion("c", V("1")), PackageVersion("c", V("2"))])
    before = State({p: V("1") for p in ("a", "b", "c")}, {"a", "b", "c"})
    analysis = analyze_update(KnowledgeBase(repo), None, before)
    assert set(analysis.conflicting_packages) == {"a", "b"}
    points = set()
    for versions in product(repo.versions("a"), repo.versions("b"), repo.versions("c")):
        state = State({pv.package: pv.version for pv in versions})
        if not validate_state(repo, state):
            points.add(tuple(repo.obsolescence(p, state.installed[p]) for p in ("a", "b")))
    expected = {point for point in points if not any(
        other != point and all(a <= b for a, b in zip(other, point)) for other in points)}
    actual = {tuple(repo.obsolescence(p, row.state.installed[p]) for p in ("a", "b")) for row in analysis.frontier}
    assert actual == expected
    assert all(row.state.installed["c"] == V("2") for row in analysis.frontier)


def test_empty_update_has_no_conflict():
    from src.updates import analyze_update
    analysis = analyze_update(KnowledgeBase(Repository([])), None, State())
    assert analysis.newest == {}
    assert analysis.frontier == []


def test_unknown_does_not_create_a_false_pareto_conflict(monkeypatch):
    from src.updates import analyze_update
    repo, before = original_case()
    monkeypatch.setattr(z3.Solver, "check", lambda self: z3.unknown)
    monkeypatch.setattr(z3.Solver, "reason_unknown", lambda self: "test timeout")
    with pytest.raises(RuntimeError, match="test timeout"):
        analyze_update(KnowledgeBase(repo), None, before)


def test_frontier_includes_all_combinations_of_independent_conflicts():
    from src.updates import analyze_update
    original, _ = original_case()
    repo = Repository([*(pv for p in ("a", "b") for pv in original.versions(p)),
        PackageVersion("c", V("1")), PackageVersion("c", V("1.1")),
        PackageVersion("c", V("2"), (parse_alternative("d <2"),)),
        PackageVersion("d", V("1")),
        PackageVersion("d", V("2"), (parse_alternative("c <2"),)),
    ])
    before = State({p: V("1") for p in ("a", "b", "c", "d")}, {"a", "b", "c", "d"})
    analysis = analyze_update(KnowledgeBase(repo), None, before)
    expected = {left + right for left, right in product(
        [(V("2"), V("1")), (V("1.1"), V("2"))], repeat=2)}
    actual = {tuple(row.state.installed[p] for p in ("a", "b", "c", "d")) for row in analysis.frontier}
    assert actual == expected
    assert set(analysis.conflicting_packages) == {"a", "b", "c", "d"}


def test_recorded_original_update_and_pareto_examples_are_valid():
    root = Path(__file__).resolve().parents[1]
    document = json.loads((root / "results/eight-point-examples.json").read_text(encoding="utf-8"))
    repo = load_repository(root / "examples/repo_example.json")
    row = document["update_all"]
    state = State({p: V(v) for p, v in row["state"].items()}, set(row["manual"]))
    assert validate_state(repo, state) == row["validation_errors"] == []
    assert row["changes"] == ["Upgrade lib: 1.0 -> 1.5", "Install util==2.0"]
    frontier = document["a_and_b"]["frontier"]
    assert {(row["state"]["a"], row["state"]["b"]) for row in frontier} == {("2.0", "1.0"), ("1.1", "2.0")}
    for row in frontier:
        state = State({p: V(v) for p, v in row["state"].items()}, set(row["manual"]))
        assert validate_state(repo, state) == row["validation_errors"] == []
    assert document["a_only"]["selected"] == {"a": "2.0", "b": "1.0"}
