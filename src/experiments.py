"""Reproduce the empty-environment installation experiments from section 4.5."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

import z3

from .knowledge_base import KnowledgeBase
from .parser import load_repository, load_requests
from .solver import install
from .validator import validate_state


def run_case(directory, size, group):
    directory = Path(directory)
    repository_path = directory / f"repo_{size}.json"
    requests_path = directory / f"requests_{size}.txt"
    metadata = json.loads(repository_path.read_text(encoding="utf-8")).get("meta", {})
    if metadata.get("group") != group:
        raise ValueError(f"{repository_path}: expected group {group}, got {metadata.get('group')}")

    started = perf_counter()
    repository = load_repository(repository_path)
    kb = KnowledgeBase(repository)
    build_seconds = perf_counter() - started
    if len(repository.package_names()) != size:
        raise ValueError(f"{repository_path}: expected {size} packages")
    requests = load_requests(requests_path)

    started = perf_counter()
    solution = install(kb, requests)
    solve_seconds = perf_counter() - started
    state = solution.state if solution is not None else None
    violations = validate_state(repository, state, requests) if state is not None else None
    if violations:
        raise ValueError("Invalid experiment result:\n" + "\n".join(violations))

    return {
        "group": group,
        "size": size,
        "repository_file": repository_path.name,
        "requests_file": requests_path.name,
        "repository_sha256": hashlib.sha256(repository_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "requests_sha256": hashlib.sha256(requests_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "versions": len(kb.x),
        "axioms": len(kb.axioms),
        "requests": list(map(str, requests)),
        "status": "sat" if solution is not None else "unsat",
        "package_count": len(state.installed) if state is not None else None,
        "obsolescence": sum(kb.obs[key] for key in state.installed.items()) if state is not None else None,
        "build_seconds": build_seconds,
        "solve_seconds": solve_seconds,
        "validation_errors": violations,
        "state": {p: str(v) for p, v in sorted(state.installed.items())} if state is not None else None,
        "manual": sorted(state.manual) if state is not None else None,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--group", type=int, default=16)
    parser.add_argument("--sizes", type=int, nargs="+", default=[10, 30, 100, 300, 1000])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    document = {
        "group": args.group,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "z3": z3.get_version_string(),
        "platform": platform.platform(),
        "timing_scope": {
            "build_seconds": "Repository loading, validation and knowledge-base construction.",
            "solve_seconds": "Installation solver invocation, model extraction and mandatory result validation.",
        },
        "results": [],
    }
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        print("N versions axioms status packages obsolescence build_s solve_s verified", flush=True)
        for size in args.sizes:
            print(f"Running N={size}...", file=sys.stderr, flush=True)
            result = run_case(args.data, size, args.group)
            document["results"].append(result)
            args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
            verified = "yes" if result["validation_errors"] == [] else "n/a"
            print(f"{size} {result['versions']} {result['axioms']} {result['status']} "
                  f"{result['package_count']} {result['obsolescence']} "
                  f"{result['build_seconds']:.6f} {result['solve_seconds']:.6f} {verified}", flush=True)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
