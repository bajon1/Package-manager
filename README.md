# Packet-manager
Packet manager

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
