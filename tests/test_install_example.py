from pathlib import Path

import pytest

from src.knowledge_base import KnowledgeBase
from src.model import Requirement, State, Version
from src.parser import load_repository, load_requests, load_state, save_state
from src.solver import install
from src.validator import validate_state


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
V = Version.parse


def test_install_app_2_example_from_instruction(tmp_path):
    repo = load_repository(EXAMPLES / "repo_example.json")
    before = load_state(EXAMPLES / "state_example.txt", repo)
    request_path = tmp_path / "requests.txt"
    request_path.write_text("app==2.0\n", encoding="utf-8")
    requests = load_requests(request_path)

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


@pytest.mark.parametrize("texts,expected", [
    (["app"], {"app": "2.0", "lib": "2.0", "util": "2.0"}),
    (["tool"], {"tool": "1.1", "lib": "1.0", "json-slow": "1.0"}),
    (["app", "tool"], {"app": "1.0", "tool": "1.1", "lib": "1.0", "json-slow": "1.0"}),
    (["app", "legacy"], {"app": "1.0", "legacy": "1.0", "lib": "1.0"}),
    (["app ==2.0", "tool"], None),
])
def test_all_empty_state_examples_from_instruction(texts, expected):
    repo = load_repository(EXAMPLES / "repo_example.json")
    requests = list(map(Requirement.parse, texts))
    result = install(KnowledgeBase(repo), requests)
    if expected is None:
        assert result is None
    else:
        assert result.state.installed == {p: V(v) for p, v in expected.items()}
        assert validate_state(repo, result.state, requests) == []
