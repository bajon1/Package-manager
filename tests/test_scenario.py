import json
from pathlib import Path

from src.model import PackageVersion, Repository, Requirement, State, Version, parse_alternative
from src.validator import validate_state


def small_repo():
    return Repository([
        PackageVersion("app", Version.parse("1"), (parse_alternative("lib"),)),
        PackageVersion("lib", Version.parse("1")),
        PackageVersion("other", Version.parse("1")),
    ])


def test_generated_operations_are_seeded_and_cover_both_removal_modes():
    from src.scenario import generate_operations
    names = ["app", "lib", "other"]
    plan = generate_operations(names, seed=2026, steps=12)
    assert plan == generate_operations(list(reversed(names)), seed=2026, steps=12)
    assert plan != generate_operations(names, seed=7, steps=12)
    assert len(plan) == 12
    assert plan[0]["operation"] == "install"
    assert {row.get("autoremove") for row in plan if row["operation"] == "remove"} == {False, True}


def test_every_intermediate_state_is_valid_and_counts_are_recorded():
    from src.scenario import generate_operations, run_scenario
    repo = small_repo()
    operations = generate_operations(repo.package_names(), 2026, 12)
    rows = run_scenario(repo, operations)
    repeated = run_scenario(repo, operations)
    assert len(rows) == 12
    for operation, row, other in zip(operations, rows, repeated):
        state = State({p: Version.parse(v) for p, v in row["state"].items()}, set(row["manual"]))
        assert validate_state(repo, state) == row["validation_errors"] == []
        assert row["package_count"] == len(state.installed)
        assert row["manual_count"] == len(state.manual)
        assert row["change_count"] == len(row["changes"])
        assert row["seconds"] >= 0
        assert {k: v for k, v in row.items() if k != "seconds"} == {
            k: v for k, v in other.items() if k != "seconds"}
        if operation["operation"] == "install" and row["status"] == "sat":
            assert validate_state(repo, state, [Requirement.parse(operation["package"])]) == []
        if operation["operation"] == "remove":
            assert operation["package"] not in state.installed


def test_unsatisfiable_operation_keeps_previous_valid_state():
    from src.scenario import run_scenario
    rows = run_scenario(small_repo(), [
        {"operation": "install", "package": "app"},
        {"operation": "install", "package": "missing"},
    ])
    assert rows[1]["status"] == "unsat"
    assert rows[1]["state"] == rows[0]["state"]
    assert rows[1]["manual"] == rows[0]["manual"]
    assert rows[1]["changes"] == []
    assert rows[1]["validation_errors"] == []


def test_scenario_command_writes_seed_operations_and_results(tmp_path):
    from src.scenario import main
    path = tmp_path / "repo.json"
    path.write_text(json.dumps({"meta": {"group": 16}, "packages": {
        "app": {"versions": {"1": {}}}, "lib": {"versions": {"1": {}}},
    }}), encoding="utf-8")
    output = tmp_path / "scenario.json"
    assert main(["--repo", str(path), "--seed", "2026", "--steps", "12", "--output", str(output)]) == 0
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["seed"] == 2026
    assert len(document["results"]) == 12
    assert all(row["validation_errors"] == [] for row in document["results"])


def test_recorded_group_scenario_has_valid_reproducible_steps():
    from src.parser import load_repository
    from src.scenario import generate_operations
    root = Path(__file__).resolve().parents[1]
    document = json.loads((root / "results/random-group16.json").read_text(encoding="utf-8"))
    repo = load_repository(root / "data/repo_200.json")
    rows = document["results"]
    plan = generate_operations(repo.package_names(), document["seed"], len(rows))
    assert document["group"] == 16
    assert len(rows) >= 10
    assert {row["autoremove"] for row in rows if row["operation"] == "remove" and row["change_count"]} == {False, True}
    for operation, row in zip(plan, rows):
        assert all(row[key] == value for key, value in operation.items())
        state = State({p: Version.parse(v) for p, v in row["state"].items()}, set(row["manual"]))
        requests = [Requirement.parse(row["package"])] if row["operation"] == "install" and row["status"] == "sat" else ()
        assert validate_state(repo, state, requests) == row["validation_errors"] == []
        assert row["package_count"] == len(state.installed)
        assert row["manual_count"] == len(state.manual)
        assert row["change_count"] == len(row["changes"])
        assert row["seconds"] >= 0
        if row["operation"] == "remove" and row["status"] == "sat":
            assert row["package"] not in state.installed
