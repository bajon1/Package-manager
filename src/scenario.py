"""Run the seeded random package-operation scenario from section 6.4."""

import argparse
import hashlib
import json
from pathlib import Path
import random
import sys
from time import perf_counter

from .changes import format_changes
from .knowledge_base import KnowledgeBase
from .model import Requirement, State
from .parser import load_repository
from .solver import install, remove
from .validator import validate_state


def generate_operations(package_names, seed=2026, steps=12):
    if steps < 10:
        raise ValueError("The scenario requires at least 10 operations.")
    names = sorted(package_names)
    if not names:
        raise ValueError("The scenario requires a nonempty repository.")
    rng = random.Random(seed)
    kinds = ["install", "remove", "autoremove"] * (steps // 3) + ["install"] * (steps % 3)
    kinds.remove("install")
    rng.shuffle(kinds)
    planned = set()
    operations = []
    for kind in ["install", *kinds]:
        candidates = sorted(planned) if kind != "install" and planned else names
        package = rng.choice(candidates)
        operation = {"operation": "install" if kind == "install" else "remove", "package": package}
        if kind == "install":
            planned.add(package)
        else:
            operation["autoremove"] = kind == "autoremove"
            planned.discard(package)
        operations.append(operation)
    return operations


def run_scenario(repository, operations):
    kb = KnowledgeBase(repository)
    state = State()
    rows = []
    for index, operation in enumerate(operations, start=1):
        requests = [Requirement.parse(operation["package"])]
        started = perf_counter()
        if operation["operation"] == "install":
            solution = install(kb, requests, state)
        elif operation["operation"] == "remove":
            solution = remove(kb, {operation["package"]}, state, operation.get("autoremove", False))
        else:
            raise ValueError(f"Unknown scenario operation: {operation['operation']}")
        seconds = perf_counter() - started
        after = solution.state if solution is not None else state
        required = requests if solution is not None and operation["operation"] == "install" else ()
        errors = validate_state(repository, after, required)
        if errors:
            raise ValueError("Invalid intermediate state:\n" + "\n".join(errors))
        changes = format_changes(state, after)
        rows.append({
            "step": index, **operation, "status": "sat" if solution is not None else "unsat",
            "changes": changes, "change_count": len(changes),
            "package_count": len(after.installed), "manual_count": len(after.manual),
            "seconds": seconds, "validation_errors": errors,
            "state": {p: str(v) for p, v in sorted(after.installed.items())},
            "manual": sorted(after.manual),
        })
        state = after
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("data/repo_200.json"))
    parser.add_argument("--group", type=int, default=16)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--steps", type=int, default=12)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        metadata = json.loads(args.repo.read_text(encoding="utf-8")).get("meta", {})
        if metadata.get("group") != args.group:
            raise ValueError(f"{args.repo}: expected group {args.group}")
        repository = load_repository(args.repo)
        operations = generate_operations(repository.package_names(), args.seed, args.steps)
        rows = run_scenario(repository, operations)
        document = {
            "group": args.group, "seed": args.seed, "repository_file": args.repo.name,
            "repository_sha256": hashlib.sha256(args.repo.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
            "timing_scope": "Each solver operation includes model extraction and mandatory result validation.",
            "results": rows,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        print(f"Seed: {args.seed}; group: {args.group}")
        print("step operation package autoremove status changes packages manual seconds verified")
        for row in rows:
            print(f"{row['step']} {row['operation']} {row['package']} {row.get('autoremove', False)} "
                  f"{row['status']} {row['change_count']} {row['package_count']} {row['manual_count']} "
                  f"{row['seconds']:.6f} yes")
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
