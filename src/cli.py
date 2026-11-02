import argparse
import sys
from pathlib import Path

from .changes import format_changes
from .explanations import explain
from .knowledge_base import KnowledgeBase
from .model import State
from .parser import load_package_names, load_repository, load_requests, load_state, save_state
from .solver import install, remove


def main(argv=None):
    parser = argparse.ArgumentParser(description="Manage packages and their dependencies.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("install", "remove", "explain"):
        command = commands.add_parser(name, help=f"{name.capitalize()} packages from a text file.")
        command.add_argument("requests", type=Path, help="Request file; package names only for removal.")
        command.add_argument("--repo", type=Path, required=True, help="Repository JSON file.")
        if name != "explain":
            command.add_argument("--state", type=Path, required=name == "remove",
                                 help="Initial state; updated unless --output is given.")
            command.add_argument("--output", type=Path, help="Save the resulting state to this file.")
        if name == "remove":
            command.add_argument("--autoremove", action="store_true", help="Minimize remaining package count.")
    args = parser.parse_args(argv)

    try:
        repository = load_repository(args.repo)
        kb = KnowledgeBase(repository)
        if args.command == "explain":
            core = explain(kb, load_requests(args.requests))
            if core is None:
                print("Requests are satisfiable; no conflict.")
                return 0
            print("Subset-minimal conflict:")
            for axiom in core:
                print(f"[{axiom.kind}] {axiom.label}")
            return 1
        before = load_state(args.state, repository) if args.state is not None else State()
        if args.command == "remove":
            solution = remove(kb, load_package_names(args.requests), before, autoremove=args.autoremove)
        else:
            solution = install(kb, load_requests(args.requests), state=before)
        if solution is None:
            print("No solution: installation requests cannot be satisfied.")
            return 1
        output = args.output if args.output is not None else args.state
        if output is not None:
            save_state(solution.state, output)
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 3

    print("Change plan:")
    print("\n".join(format_changes(before, solution.state)) or "No changes.")
    print("Installed state:")
    for package, version in sorted(solution.state.installed.items()):
        marker = " manual" if package in solution.state.manual else ""
        print(f"{package} {version}{marker}")
    return 0
