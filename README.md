# Package-manager

Package-manager is a dependency solver and environment simulator for package
repositories, written in Python for the *Projekt 2 – manager pakietów*
assignment. It encodes versions, dependencies, alternatives, and conflicts as a
propositional knowledge base, answers manager queries with the Z3 optimizer,
and checks every result with an independent validator.

## Overview

- A repository contains packages, each with one or more versions.
- Every version may require packages or alternatives and may conflict with
  other packages.
- An environment contains at most one version of each package. Manually
  installed packages are distinguished from automatic dependencies.
- Queries are optimized lexicographically: the result is best by the first
  criterion, then the second, and so on.
- The project covers the 4-, 6-, and 8-point tiers: installation, environment
  state, removal, explanations, updates, and PyPI data.

## Features

- Strict repository loading and validation with line and document-path errors.
- Propositional knowledge base with at-most-one, dependency, and conflict axioms.
- Install, remove/autoremove, update, and explain commands.
- Subset-minimal unsat cores and Pareto frontiers for update conflicts.
- PyPI repositories using PEP 440/508 versions, specifiers, markers, and
  `requires_python`.
- Solver-independent validation of every returned state.
- Reproducible experiments, a seeded random scenario, and recorded results.

## Requirements

- Python 3.13 or newer
- [uv](https://docs.astral.sh/uv/) for the commands below

`z3-solver` and `packaging` are installed from `pyproject.toml`.

## Installation

Install the project and development dependencies:

```sh
uv sync --dev
```

Run the CLI through the installed entry point or the repository script:

```sh
uv run package-manager --help
uv run python manager.py --help
```

A plain pip installation also works:

```sh
pip install -e .
pip install pytest
```

## Project structure

```text
src/
  model.py            packages, versions, requirements, repositories, states
  parser.py           repository, request, state, and name-file loaders
  validator.py        solver-independent state validation
  knowledge_base.py   Z3 variables and A1/A2/A3 axioms
  solver.py           install, remove, and update optimization
  explanations.py     subset-minimal unsat cores
  updates.py          newest reachable versions and Pareto frontier
  pypi.py             PEP 440/508 repository import
  cli.py              command-line interface
  experiments.py      4.5 experiment runner
  scenario.py         6.4 seeded random scenario
  pypi_scenario.py    8.3 PyPI scenario
tests/                parser, model, solver, CLI, PyPI, and result tests
examples/             instructor-provided example inputs and walkthroughs
data/                 group-16 repositories and request files
results/              recorded experiment and example outputs
docs/projekt2.pdf     local assignment specification (not tracked)
```

## Input files

### Repository

A repository is a JSON object under `packages`. Each package has `versions`;
a version may define `requires` and `conflicts`.

```json
{
  "packages": {
    "app": {"versions": {"2.0": {"requires": ["lib >=2.0", "util"]}}},
    "lib": {"versions": {"1.0": {}, "2.0": {}}},
    "util": {"versions": {"1.0": {}, "2.0": {}}},
    "legacy": {"versions": {"1.0": {"conflicts": ["util >=2.0"]}}}
  }
}
```

- Names are case-insensitive; `-`, `_`, and `.` are equivalent.
- Versions are dot-separated integers, so `1.10 > 1.9` and `1.0 == 1.0.0`.
- A requirement is a package name with zero or more `==`, `!=`, `<`, `<=`,
  `>`, `>=` constraints.
- A `requires` entry may be an alternative such as `json-fast | json-slow`.
- Invalid files raise `ValueError` with the filename and error location.
  Requirements without a matching version produce a warning.

### State

One package per line; the optional `manual` marker records user requests.

```text
tool 1.1 manual
lib 1.0
```

### Requests

One requirement per line. Blank lines and `#` comments are ignored.

```text
app==2.0
tool
```

Removal and selected-update files contain one package name per line.

### PyPI data

Repositories with `requires_dist` and `requires_python` are imported using
`packaging`. Versions incompatible with `meta.environment` are skipped, markers
are evaluated in that target environment, and extras are ignored. The original
`pypi_data.json` is not supplied, so 8.3 results are covered only by synthetic
test fixtures.

## CLI

| Command | Arguments | Purpose |
| --- | --- | --- |
| `install` | `REQUESTS --repo REPO [--state STATE] [--output OUT]` | Install requests into an empty or existing state. |
| `remove` | `NAMES --repo REPO --state STATE [--output OUT] [--autoremove]` | Remove packages and repair dependents. |
| `update` | `[NAMES] --repo REPO --state STATE [--output OUT]` | Update selected or all installed packages. |
| `explain` | `REQUESTS --repo REPO` | Print a minimal conflict for unsatisfiable requests. |

Example:

```sh
uv run package-manager install examples/requests_example.txt \
  --repo examples/repo_example.json \
  --state examples/state_example.txt \
  --output result.txt
```

`--output` defaults to `--state`, so the input state is updated when no separate
output is given. Use `--output` to preserve the original file.

Exit codes: `0` success, `1` unsatisfiable or conflict found, `2` input error,
`3` solver unknown.

## Optimization criteria

Criteria are applied lexicographically; the first is most important.
Obsolescence is the position of a version in the package's newest-first list,
so `0` means newest.

| Query | Criteria |
| --- | --- |
| Install into empty state | requested obsolescence; package count; other obsolescence |
| Install into existing state | removed packages; version changes; new requested obsolescence; new packages; other new obsolescence |
| Remove | removed manual packages outside the request; version changes; new packages; removed packages (`--autoremove` uses installed count) |
| Update | updated-package obsolescence; removed packages; changes outside the update set; new packages; total obsolescence |

## Explanations and updates

`explain` prints a subset-minimal unsat core: the reported axioms and requests
are together unsatisfiable, and removing any one of them makes the rest
satisfiable. It is minimal, not necessarily the smallest possible core.

`update` reports the newest individually reachable version of each selected
package. If they cannot coexist, it prints the conflict core and all
non-dominated Pareto alternatives for the conflicting packages.

## Examples and results

Walkthroughs for the supplied example files are in `examples/`:

- `installation.txt` – install into empty/existing environments (4.3, 6.1)
- `operations.txt` – removal, explanations, and the random scenario (6.2–6.4)
- `updates-pypi.txt` – updates, Pareto conflicts, and PyPI data (8.1–8.3)

Recorded outputs:

- `results/group16.json` – 4.5 solutions and timings for N = 10, 30, 100, 300, 1000
- `results/six-point-examples.json` – original removal and explanation results
- `results/random-group16.json` – seeded 12-operation scenario on `repo_200.json`
- `results/eight-point-examples.json` – original update and Pareto results

## Assignment mapping

| Task | Implementation |
| --- | --- |
| 4.1 Repository model and validation | `src/model.py`, `src/parser.py` |
| 4.2 Knowledge base | `src/knowledge_base.py` |
| 4.3 / 6.1 Installation | `src/solver.py` |
| 4.4 State verification | `src/validator.py` |
| 4.5 Repository experiment | `src/experiments.py`, `results/group16.json` |
| 6.2 Removal and autoremove | `src/solver.py` |
| 6.3 Conflict explanation | `src/explanations.py` |
| 6.4 Random scenario | `src/scenario.py`, `results/random-group16.json` |
| 8.1 Update | `src/updates.py` |
| 8.2 Pareto analysis | `src/updates.py` |
| 8.3 PyPI data | `src/pypi.py`, `src/pypi_scenario.py` |

## Reproducing experiments

The repository contains group-16 data. Run from the project root:

```sh
uv run python -m src.experiments --data data --group 16 \
  --output results/group16.json

uv run python -m src.scenario --repo data/repo_200.json --group 16 \
  --seed 2026 --steps 12 --output results/random-group16.json

uv run python -m src.pypi_scenario --repo PATH_TO/pypi_data.json \
  --output results/pypi-scenario.json
```

The first command runs the 4.5 installation experiment for every repository
size. The second starts from an empty environment and runs a reproducible mix
of install, remove, and autoremove operations. The third requires the original
PyPI dataset, which is not included.

## Tests

```sh
uv run pytest
```

The suite covers parsing errors, knowledge-base semantics, all lexicographic
objectives, CLI behavior, explanations, PyPI import, and replay of recorded
results. Small repositories are also compared against exhaustive search.

## Notes

- `data/` and `results/` contain group 16; the assignment requires reporting
  the group number.
- `docs/projekt2.pdf` is the local Polish specification and is excluded by
  `.gitignore`.
- Solver ties and timings may differ across Z3 versions and machines; the
  scenario's random operations are fixed by its seed.
