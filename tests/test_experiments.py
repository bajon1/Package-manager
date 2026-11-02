import json
import hashlib
from pathlib import Path

import pytest

from src.model import State, Version
from src.validator import validate_state
from src.parser import load_repository, load_requests


@pytest.fixture
def experiment_data(tmp_path):
    (tmp_path / "repo_2.json").write_text(json.dumps({
        "meta": {"group": 16},
        "packages": {
            "app": {"versions": {"1": {"requires": ["lib"]}, "2": {"requires": ["lib"]}}},
            "lib": {"versions": {"1": {}, "2": {}}},
        },
    }), encoding="utf-8")
    (tmp_path / "requests_2.txt").write_text("# test\napp ==1\n", encoding="utf-8")
    return tmp_path


def test_experiment_records_counts_solution_and_verification(experiment_data):
    from src.experiments import run_case
    result = run_case(experiment_data, 2, group=16)

    assert result["size"] == 2
    assert result["group"] == 16
    assert result["versions"] == 4
    assert result["axioms"] == 4
    assert result["requests"] == ["app ==1"]
    assert result["status"] == "sat"
    assert result["package_count"] == 2
    assert result["obsolescence"] == 1
    assert result["validation_errors"] == []
    assert result["state"] == {"app": "1", "lib": "2"}
    repo = load_repository(experiment_data / "repo_2.json")
    state = State({p: Version.parse(v) for p, v in result["state"].items()}, set(result["manual"]))
    assert validate_state(repo, state, load_requests(experiment_data / "requests_2.txt")) == []
    assert result["build_seconds"] >= 0
    assert result["solve_seconds"] >= 0
    assert len(result["repository_sha256"]) == len(result["requests_sha256"]) == 64


def test_experiment_records_unsatisfiable_outcome(experiment_data):
    from src.experiments import run_case
    (experiment_data / "requests_2.txt").write_text("app ==9\n", encoding="utf-8")
    result = run_case(experiment_data, 2, group=16)
    assert result["status"] == "unsat"
    assert result["package_count"] is None
    assert result["obsolescence"] is None
    assert result["state"] is None
    assert result["validation_errors"] is None


def test_experiment_rejects_data_from_other_group(experiment_data):
    from src.experiments import run_case
    with pytest.raises(ValueError, match="group"):
        run_case(experiment_data, 2, group=7)


def test_experiment_command_writes_reproducible_results(experiment_data, capsys):
    from src.experiments import main
    output = experiment_data / "results.json"
    assert main(["--data", str(experiment_data), "--group", "16", "--sizes", "2", "--output", str(output)]) == 0
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["group"] == 16
    assert document["results"][0]["status"] == "sat"
    assert document["results"][0]["validation_errors"] == []
    assert "2" in capsys.readouterr().out


def test_recorded_group_results_match_inputs_and_valid_states():
    root = Path(__file__).resolve().parents[1]
    document = json.loads((root / "results" / "group16.json").read_text(encoding="utf-8"))
    assert document["group"] == 16
    assert [row["size"] for row in document["results"]] == [10, 30, 100, 300, 1000]
    for row in document["results"]:
        repo_path = root / "data" / row["repository_file"]
        request_path = root / "data" / row["requests_file"]
        assert hashlib.sha256(repo_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == row["repository_sha256"]
        assert hashlib.sha256(request_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == row["requests_sha256"]
        assert row["build_seconds"] >= 0
        assert row["solve_seconds"] >= 0
        repo = load_repository(repo_path)
        requests = load_requests(request_path)
        assert len(repo.package_names()) == row["size"]
        assert row["requests"] == list(map(str, requests))
        if row["status"] == "sat":
            state = State({p: Version.parse(v) for p, v in row["state"].items()}, set(row["manual"]))
            assert validate_state(repo, state, requests) == row["validation_errors"] == []
            assert len(state.installed) == row["package_count"]
            assert sum(repo.obsolescence(p, v) for p, v in state.installed.items()) == row["obsolescence"]
        else:
            assert row["status"] == "unsat"
            from src.knowledge_base import KnowledgeBase
            import z3
            kb = KnowledgeBase(repo)
            solver = z3.Solver()
            solver.add([axiom.formula for axiom in kb.axioms])
            solver.add([kb.request_axiom(r).formula for r in requests])
            assert solver.check() == z3.unsat
            assert row["state"] is None
