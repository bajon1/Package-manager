from pathlib import Path

import pytest

from src.knowledge_base import KnowledgeBase
from src.model import State, Version
from src.parser import load_repository, load_requests, load_state, save_state
from src.solver import install
from src.validator import validate_state


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
V = Version.parse


def test_install_app_2_example_from_instruction(tmp_path):
    repo = load_repository(EXAMPLES / "repo_example.json")
    before = load_state(EXAMPLES / "state_example.txt", repo)
    requests = load_requests(EXAMPLES / "requests_install_app.txt")

    result = install(KnowledgeBase(repo), requests, state=before)

    assert result.state == State({
        "app": V("2.0"), "lib": V("2.0"), "util": V("2.0"), "json-slow": V("1.0"),
    }, {"app"})
    assert validate_state(repo, result.state, requests) == []
    output = tmp_path / "result.txt"
    save_state(result.state, output)
    assert load_state(output, repo) == result.state


@pytest.mark.parametrize("existing_state", [False, True])
def test_supplied_requests_are_unsatisfiable(existing_state):
    repo = load_repository(EXAMPLES / "repo_example.json")
    before = load_state(EXAMPLES / "state_example.txt", repo) if existing_state else State()
    requests = load_requests(EXAMPLES / "requests_example.txt")

    assert install(KnowledgeBase(repo), requests, state=before) is None
