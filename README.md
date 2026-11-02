# Package-manager

Package-manager is a Python project for modeling packages, their versions, dependencies, and conflicts. It loads JSON repositories and validates their structure, reporting errors and requirements without matching versions.

## Tests

Install the development dependencies and run the tests from the project directory:

```sh
uv sync --dev
uv run pytest
```

Tests are located in the `tests/` directory, in `test_*.py` files.

## Loading a repository

```python
from src.parser import load_repository

repository = load_repository("data/repo_10.json")
print(repository.package_names())
```

An invalid file raises a `ValueError` with the filename and error location.
Warnings about requirements without matching versions are written to standard error.

## Loading installation requests

```python
from src.parser import load_requests

requests = load_requests("data/requests_10.txt")
print([str(requirement) for requirement in requests])
```

Each line contains a package name with optional version constraints, such as
`app >=1, <2`. Blank lines and comments starting with `#` are ignored, including
comments after a request. Invalid requests raise `ValueError` with the filename
and original line number; unreadable files report the filename and cause.

## Validating an installed state

`validate_state(repository, state, requests=())` checks installed versions,
dependencies, conflicts, and optional requests without a solver. It returns all
violations, or an empty list for a valid state.

```python
from src.validator import validate_state

for error in validate_state(repository, state):
    print(error)
```
