from pathlib import Path

from src.model import State, Version
from src.parser import load_state


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_update_all_command_uses_original_state(tmp_path, capsys):
    from src.cli import main
    output = tmp_path / "result.txt"
    assert main(["update", "--repo", str(EXAMPLES / "repo_example.json"),
                 "--state", str(EXAMPLES / "state_example.txt"), "--output", str(output)]) == 0
    state = load_state(output)
    assert str(state.installed["lib"]) == "1.5"
    assert str(state.installed["util"]) == "2.0"
    assert state.manual == {"app", "tool"}
    assert "Upgrade lib" in capsys.readouterr().out


def test_update_selected_packages_are_read_from_optional_file(tmp_path):
    from src.cli import main
    target = tmp_path / "update.txt"
    target.write_text("lib\n", encoding="utf-8")
    output = tmp_path / "result.txt"
    assert main(["update", str(target), "--repo", str(EXAMPLES / "repo_example.json"),
                 "--state", str(EXAMPLES / "state_example.txt"), "--output", str(output)]) == 0
    assert str(load_state(output).installed["lib"]) == "1.5"


def test_update_uninstalled_target_does_not_overwrite_state(tmp_path, capsys):
    from src.cli import main
    target = tmp_path / "update.txt"
    target.write_text("missing\n", encoding="utf-8")
    state = tmp_path / "state.txt"
    state.write_bytes((EXAMPLES / "state_example.txt").read_bytes())
    original = state.read_bytes()
    assert main(["update", str(target), "--repo", str(EXAMPLES / "repo_example.json"),
                 "--state", str(state)]) == 2
    assert state.read_bytes() == original
    assert "not installed" in capsys.readouterr().err
