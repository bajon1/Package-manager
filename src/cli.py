import argparse
import sys
from pathlib import Path

from .changes import format_changes
from .knowledge_base import KnowledgeBase
from .model import State
from .parser import load_repository, load_requests, load_state, save_state
from .solver import install


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install packages and their dependencies.")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("install", help="Install requests from a text file.")
    command.add_argument("requests", type=Path, help="File containing installation requests.")
    command.add_argument("--repo", type=Path, required=True, help="Repository JSON file.")
    command.add_argument("--state", type=Path, help="Initial state; updated unless --output is given.")
    command.add_argument("--output", type=Path, help="Save the resulting state to this file.")
    args = parser.parse_args(argv)

    try:
        repository = load_repository(args.repo)
        requests = load_requests(args.requests)
        before = load_state(args.state, repository) if args.state is not None else State()
        solution = install(KnowledgeBase(repository), requests, state=before)
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
