import json

import pytest

from src.parser import load_repository
from src.model import State
from src.validator import validate_state


@pytest.fixture
def scenario_repository(tmp_path):
    packages = {
        "pandas": {"1": ["numpy>=1"], "2": ["numpy>=2"]},
        "numpy": {"1": [], "2": []},
        "requests": {"1": ["urllib3<2"], "2": ["urllib3>=2"]},
        "urllib3": {"1": [], "2": []},
        "boto3": {"1": ["botocore==1"], "2": ["botocore==2"]},
        "aiobotocore": {"1": ["botocore==1"]},
        "botocore": {"1": [], "2": []},
    }
    path = tmp_path / "pypi_data.json"
    path.write_text(json.dumps({"meta": {"environment": {"python_version": "3.11"}},
        "packages": {p: {"versions": {v: {"requires_dist": deps} for v, deps in versions.items()}}
                     for p, versions in packages.items()}}), encoding="utf-8")
    return path


def test_required_pypi_scenario_runs_and_verifies_every_operation(scenario_repository):
    from src.pypi_scenario import run_scenario
    repo = load_repository(scenario_repository)
    document = run_scenario(repo)
    rows = document["operations"]
    assert [row["operation"] for row in rows] == ["install", "install", "install", "update", "update", "remove"]
    assert rows[0]["state"]["pandas"] == rows[0]["state"]["requests"] == "1"
    assert rows[1]["state"]["boto3"] == "2"
    assert rows[2]["state"]["boto3"] == "1"
    assert rows[3]["state"]["requests"] == "2"
    assert rows[4]["state"]["pandas"] == "2"
    assert "botocore" not in rows[5]["state"]
    assert document["conflict"]["subset_minimal_verified"] is True
    assert document["conflict"]["core"]
    for row in rows:
        state = State({p: repo.parse_version(v) for p, v in row["state"].items()}, set(row["manual"]))
        assert validate_state(repo, state) == row["validation_errors"] == []
        assert row["seconds"] >= 0


def test_pypi_scenario_command_records_loading_time_and_input(scenario_repository, tmp_path):
    from src.pypi_scenario import main
    output = tmp_path / "result.json"
    assert main(["--repo", str(scenario_repository), "--output", str(output)]) == 0
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["load_seconds"] >= 0
    assert len(document["repository_sha256"]) == 64
    assert len(document["operations"]) == 6
    assert document["target_environment"]["python_version"] == "3.11"


def test_pypi_scenario_missing_dataset_is_reported_without_fake_results(tmp_path, capsys):
    from src.pypi_scenario import main
    output = tmp_path / "result.json"
    assert main(["--repo", str(tmp_path / "missing.json"), "--output", str(output)]) == 2
    assert "missing.json" in capsys.readouterr().err
    assert not output.exists()
