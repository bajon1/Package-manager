from pathlib import Path

import pytest

from src.model import State, Version
from src.parser import load_state


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.mark.parametrize("package,autoremove,expected", [
    ("lib", False, {"json-slow": "1.0"}),
    ("tool", True, {"app": "1.0", "lib": "1.0"}),
])
def test_remove_command_uses_files_and_prints_changes(tmp_path, capsys, package, autoremove, expected):
    from src.cli import main
    target = tmp_path / "remove.txt"
    target.write_text(package + "\n", encoding="utf-8")
    output = tmp_path / "state.txt"
    args = ["remove", str(target), "--repo", str(EXAMPLES / "repo_example.json"),
            "--state", str(EXAMPLES / "state_example.txt"), "--output", str(output)]
    if autoremove:
        args.append("--autoremove")
    assert main(args) == 0
    assert load_state(output).installed == {p: Version.parse(v) for p, v in expected.items()}
    assert f"Remove {package}==" in capsys.readouterr().out


def test_remove_rejects_version_constraints_without_changing_output(tmp_path, capsys):
    from src.cli import main
    target = tmp_path / "remove.txt"
    target.write_text("lib >=2\n", encoding="utf-8")
    output = tmp_path / "state.txt"
    output.write_text("old 1\n", encoding="utf-8")
    assert main(["remove", str(target), "--repo", str(EXAMPLES / "repo_example.json"),
                 "--state", str(EXAMPLES / "state_example.txt"), "--output", str(output)]) == 2
    assert "line 1" in capsys.readouterr().err
    assert output.read_text(encoding="utf-8") == "old 1\n"


def test_explain_command_prints_original_example_conflict(capsys):
    from src.cli import main
    assert main(["explain", str(EXAMPLES / "requests_example.txt"),
                 "--repo", str(EXAMPLES / "repo_example.json")]) == 1
    output = capsys.readouterr().out
    assert "Subset-minimal conflict" in output
    assert "[REQUEST]" in output
    assert "app ==2.0" in output
    assert "tool" in output


def test_explain_satisfiable_requests_is_explicit(tmp_path, capsys):
    from src.cli import main
    requests = tmp_path / "requests.txt"
    requests.write_text("app\n", encoding="utf-8")
    assert main(["explain", str(requests), "--repo", str(EXAMPLES / "repo_example.json")]) == 0
    assert "satisfiable" in capsys.readouterr().out
