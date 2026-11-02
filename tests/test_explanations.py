from pathlib import Path
import json

import pytest
import z3

from src.knowledge_base import KnowledgeBase
from src.model import PackageVersion, Repository, Requirement, Version
from src.parser import load_repository, load_requests


def assert_minimal(core):
    assert core
    solver = z3.Solver()
    solver.add([a.formula for a in core])
    assert solver.check() == z3.unsat
    for index in range(len(core)):
        solver = z3.Solver()
        solver.add([a.formula for i, a in enumerate(core) if i != index])
        assert solver.check() == z3.sat


@pytest.mark.parametrize("directory,size", [("examples", None), ("data", 100)])
def test_instruction_and_group_conflicts_have_minimal_readable_cores(directory, size):
    from src.explanations import explain
    root = Path(__file__).resolve().parents[1] / directory
    suffix = "example" if size is None else str(size)
    kb = KnowledgeBase(load_repository(root / f"repo_{suffix}.json"))
    requests = load_requests(root / f"requests_{suffix}.txt")
    core = explain(kb, requests)

    assert_minimal(core)
    assert any(a.kind == "REQUEST" for a in core)
    assert all(a.label and a.kind in {"A1", "A2", "A3", "REQUEST"} for a in core)


def test_duplicate_request_labels_are_tracked_independently():
    from src.explanations import explain
    repo = Repository([PackageVersion("app", Version.parse(v)) for v in ("1", "2")])
    requests = list(map(Requirement.parse, ["app ==1", "app ==1", "app ==2"]))
    core = explain(KnowledgeBase(repo), iter(requests))
    assert_minimal(core)
    assert len(core) == 3
    assert [a.label for a in core].count("request: app ==1") == 1


def test_unavailable_package_is_explained_by_the_request_alone():
    from src.explanations import explain
    core = explain(KnowledgeBase(Repository([])), [Requirement.parse("ghost")])
    assert_minimal(core)
    assert [a.label for a in core] == ["request: ghost"]


def test_satisfiable_requests_have_no_conflict():
    from src.explanations import explain
    repo = Repository([PackageVersion("app", Version.parse("1"))])
    assert explain(KnowledgeBase(repo), [Requirement.parse("app")]) is None
    assert explain(KnowledgeBase(Repository([])), []) is None


def test_unknown_is_not_misreported_as_a_conflict(monkeypatch):
    from src.explanations import explain
    monkeypatch.setattr(z3.Solver, "check", lambda self: z3.unknown)
    monkeypatch.setattr(z3.Solver, "reason_unknown", lambda self: "test timeout")
    with pytest.raises(RuntimeError, match="test timeout"):
        explain(KnowledgeBase(Repository([])), [])


def test_recorded_required_explanations_are_genuinely_minimal():
    root = Path(__file__).resolve().parents[1]
    document = json.loads((root / "results/six-point-examples.json").read_text(encoding="utf-8"))
    assert {row["repository"] for row in document["conflicts"]} == {
        "examples/repo_example.json", "data/repo_100.json"}
    for row in document["conflicts"]:
        kb = KnowledgeBase(load_repository(root / row["repository"]))
        requests = load_requests(root / row["request_file"])
        by_label = {a.label: a for a in [*kb.axioms, *(kb.request_axiom(r) for r in requests)]}
        core = [by_label[a["label"]] for a in row["core"]]
        assert_minimal(core)
