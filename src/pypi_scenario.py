"""Run the required pandas/requests/boto3/aiobotocore scenario from section 8.3."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

import z3

from .changes import format_changes
from .explanations import check, explain
from .knowledge_base import KnowledgeBase
from .model import State
from .parser import load_repository
from .solver import install, remove, update
from .updates import analyze_update
from .validator import validate_state


def run_scenario(repository, kb=None):
    if repository.environment is None:
        raise ValueError("The scenario requires a PyPI repository with a target environment.")
    for package in ("pandas", "requests", "boto3", "aiobotocore", "botocore"):
        if not repository.versions(package):
            raise ValueError(f"The scenario requires compatible versions of {package}.")
    kb = kb if kb is not None else KnowledgeBase(repository)
    oldest = lambda package: repository.versions(package)[-1].version
    operations = [
        ("install", [f"pandas=={oldest('pandas')}", f"requests=={oldest('requests')}"]),
        ("install", ["boto3"]),
        ("install", ["aiobotocore"]),
        ("update", {"requests"}),
        ("update", None),
        ("remove", {"botocore"}),
    ]
    state, rows = State(), []
    for index, (kind, payload) in enumerate(operations, start=1):
        started = perf_counter()
        analysis = None
        if kind == "install":
            requests = [repository.parse_requirement(text) for text in payload]
            solution = install(kb, requests, state)
        elif kind == "update":
            requests = []
            analysis = analyze_update(kb, payload, state)
            solution = update(kb, payload, state)
        else:
            requests = []
            solution = remove(kb, payload, state)
        seconds = perf_counter() - started
        if solution is None:
            raise ValueError(f"Required scenario step {index} ({kind}) has no solution; no successful scenario is recorded.")
        after = solution.state
        errors = validate_state(repository, after, requests)
        if errors:
            raise ValueError("Invalid PyPI scenario state:\n" + "\n".join(errors))
        rows.append({
            "step": index, "operation": kind,
            "requests": list(payload) if kind == "install" else None,
            "packages": sorted(payload) if kind != "install" and payload is not None else None,
            "changes": format_changes(state, after),
            "state": {p: str(v) for p, v in sorted(after.installed.items())},
            "manual": sorted(after.manual), "package_count": len(after.installed),
            "seconds": seconds, "validation_errors": errors,
            "pareto": [{p: str(v) for p, v in sorted(row.state.installed.items())} for row in analysis.frontier]
                      if analysis is not None else [],
        })
        state = after

    texts = [f"boto3=={repository.versions('boto3')[0].version}", f"botocore=={oldest('botocore')}"]
    requests = [repository.parse_requirement(text) for text in texts]
    started = perf_counter()
    core = explain(kb, requests)
    seconds = perf_counter() - started
    if core is not None:
        for omit in [None, *range(len(core))]:
            solver = z3.Solver()
            solver.add([a.formula for i, a in enumerate(core) if i != omit])
            if check(solver) != (z3.unsat if omit is None else z3.sat):
                raise ValueError("The final explanation failed subset-minimality verification.")
    return {
        "target_environment": repository.environment,
        "timing_scope": "Operation calls include solving, result validation and, for updates, newest-version/Pareto analysis.",
        "operations": rows,
        "conflict": {"requests": texts, "status": "unsat" if core is not None else "sat",
                     "core": [{"kind": a.kind, "label": a.label} for a in core] if core is not None else [],
                     "subset_minimal_verified": True if core is not None else None, "seconds": seconds},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        started = perf_counter()
        repository = load_repository(args.repo, pypi=True)
        kb = KnowledgeBase(repository)
        load_seconds = perf_counter() - started
        document = run_scenario(repository, kb)
        document.update({"load_seconds": load_seconds, "versions": len(kb.x), "axioms": len(kb.axioms),
                         "repository_file": args.repo.name,
                         "repository_sha256": hashlib.sha256(args.repo.read_bytes().replace(b"\r\n", b"\n")).hexdigest()})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        print(f"Repository loading and knowledge base: {load_seconds:.6f}s")
        for row in document["operations"]:
            print(f"{row['step']} {row['operation']}: {row['package_count']} packages, "
                  f"{len(row['changes'])} changes, {row['seconds']:.6f}s; verified")
        print(f"Final explanation: {document['conflict']['status']}")
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
