import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.model import State, Version
from src.parser import load_state


ROOT = Path(__file__).resolve().parents[1]
V = Version.parse


def test_change_plan_covers_all_operations():
    from src.changes import format_changes
    before = State({"up": V("1"), "down": V("2"), "gone": V("1"), "same": V("1")})
    after = State({"up": V("2"), "down": V("1"), "new": V("1"), "same": V("1")})

    assert format_changes(before, after) == [
        "Downgrade down: 2 -> 1", "Remove gone==1", "Install new==1", "Upgrade up: 1 -> 2",
    ]
    assert format_changes(before, before) == []


@pytest.fixture
def inputs(tmp_path):
    repo = tmp_path / "repo.json"
    repo.write_text(json.dumps({"packages": {
        "app": {"versions": {"1": {"requires": ["lib"]}, "2": {"requires": ["lib >=2"]}}},
        "lib": {"versions": {"1": {}, "2": {}}},
        "tool": {"versions": {"1": {"conflicts": ["app >=2"]}}},
    }}), encoding="utf-8")
    requests = tmp_path / "requests.txt"
    requests.write_text("app ==2\n", encoding="utf-8")
    state = tmp_path / "state.txt"
    state.write_text("app 1 manual\nlib 1\ntool 1 manual\n", encoding="utf-8")
    output = tmp_path / "result.txt"
    return repo, requests, state, output


def test_cli_existing_state_prints_plan_and_saves_result(inputs, capsys):
    from src.cli import main
    repo, requests, state, output = inputs
    original = state.read_bytes()

    assert main(["install", str(requests), "--repo", str(repo), "--state", str(state),
                 "--output", str(output)]) == 0

    assert state.read_bytes() == original
    assert load_state(output) == State({"app": V("2"), "lib": V("2")}, {"app"})
    captured = capsys.readouterr()
    assert "Upgrade app: 1 -> 2" in captured.out
    assert "Upgrade lib: 1 -> 2" in captured.out
    assert "Remove tool==1" in captured.out
    assert "app 2 manual" in captured.out
    assert captured.err == ""


def test_cli_updates_input_state_when_no_separate_output_is_given(inputs, capsys):
    from src.cli import main
    repo, requests, state, _ = inputs
    assert main(["install", str(requests), "--repo", str(repo), "--state", str(state)]) == 0
    assert load_state(state) == State({"app": V("2"), "lib": V("2")}, {"app"})


def test_cli_empty_environment_via_real_entry_point(inputs):
    repo, requests, _, output = inputs
    result = subprocess.run([
        sys.executable, str(ROOT / "manager.py"), "install", str(requests),
        "--repo", str(repo), "--output", str(output),
    ], cwd=ROOT, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert "Install app==2" in result.stdout
    assert load_state(output) == State({"app": V("2"), "lib": V("2")}, {"app"})


def test_cli_unsatisfiable_request_preserves_files(inputs, capsys):
    from src.cli import main
    repo, requests, state, output = inputs
    requests.write_text("app ==9\n", encoding="utf-8")
    original = state.read_bytes()
    output.write_text("keep this output\n", encoding="utf-8")

    assert main(["install", str(requests), "--repo", str(repo), "--state", str(state),
                 "--output", str(output)]) == 1
    assert state.read_bytes() == original
    assert output.read_text(encoding="utf-8") == "keep this output\n"
    assert "No solution" in capsys.readouterr().out


def test_cli_no_changes_is_explicit(inputs, capsys):
    from src.cli import main
    repo, requests, state, _ = inputs
    requests.write_text("app\n", encoding="utf-8")
    assert main(["install", str(requests), "--repo", str(repo), "--state", str(state)]) == 0
    assert "No changes" in capsys.readouterr().out


@pytest.mark.parametrize("bad_input", ["requests", "state", "repo"])
def test_cli_input_error_does_not_overwrite_output(inputs, capsys, bad_input):
    from src.cli import main
    repo, requests, state, output = inputs
    path = {"requests": requests, "state": state, "repo": repo}[bad_input]
    path.write_text("not valid input\n", encoding="utf-8")
    output.write_text("unchanged\n", encoding="utf-8")
    assert main(["install", str(requests), "--repo", str(repo), "--state", str(state),
                 "--output", str(output)]) == 2
    assert str(path) in capsys.readouterr().err
    assert output.read_text(encoding="utf-8") == "unchanged\n"


def test_cli_reports_all_state_violations(inputs, capsys):
    from src.cli import main
    repo, requests, state, _ = inputs
    state.write_text("app 1\nghost 1\n", encoding="utf-8")
    original = state.read_bytes()
    assert main(["install", str(requests), "--repo", str(repo), "--state", str(state)]) == 2
    message = capsys.readouterr().err
    assert "unsatisfied requirement 'lib'" in message
    assert "ghost==1" in message
    assert state.read_bytes() == original


def test_cli_missing_request_file(inputs, capsys):
    from src.cli import main
    repo, requests, _, _ = inputs
    requests.unlink()
    assert main(["install", str(requests), "--repo", str(repo)]) == 2
    assert str(requests) in capsys.readouterr().err


def test_cli_write_failure_is_reported(inputs, capsys):
    from src.cli import main
    repo, requests, _, output = inputs
    assert main(["install", str(requests), "--repo", str(repo), "--output", str(output / "missing")]) == 2
    assert str(output / "missing") in capsys.readouterr().err


def test_cli_unknown_is_distinct_from_unsatisfiable(inputs, capsys, monkeypatch):
    from src import cli
    def unknown(*args, **kwargs):
        raise RuntimeError("Solver returned unknown: timeout")
    monkeypatch.setattr(cli, "install", unknown)
    repo, requests, state, output = inputs
    original = state.read_bytes()
    assert cli.main(["install", str(requests), "--repo", str(repo), "--state", str(state),
                     "--output", str(output)]) == 3
    captured = capsys.readouterr()
    assert "unknown" in captured.err
    assert "No solution" not in captured.out
    assert state.read_bytes() == original
    assert not output.exists()
