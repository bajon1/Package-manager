import json
import re
import sys
from pathlib import Path

from .model import PackageVersion, Repository, Requirement, State, Version, normalize_name, parse_alternative
from .validator import validate_state



def validate_object(value, path, allowed=None, required=()):
    if not isinstance(value, tuple):
        raise ValueError(f"{path or '$'}: expected a JSON object")
    result = {}
    for key, item in value:
        if path.endswith((".packages", ".versions")):
            location = f"{path}[{key!r}]"
        else:
            location = f"{path}.{key}" if path else key
        if key in result:
            raise ValueError(f"{location}: duplicate key")
        if allowed is not None and key not in allowed:
            raise ValueError(f"{location}: unknown field")
        result[key] = item
    for key in required:
        if key not in result:
            location = f"{path}.{key}" if path else key
            raise ValueError(f"{location}: missing required field")
    return result


def parse_dependencies(value, path, package, alternatives):
    if not isinstance(value, list):
        raise ValueError(f"{path}: expected a list of strings")
    result = []
    for index, text in enumerate(value):
        location = f"{path}[{index}]"
        if not isinstance(text, str):
            raise ValueError(f"{location}: expected a string")
        try:
            requirements = parse_alternative(text) if alternatives else (Requirement.parse(text),)
        except ValueError as error:
            raise ValueError(f"{location}: {error}") from error
        if any(requirement.package == package for requirement in requirements):
            raise ValueError(f"{location}: a package cannot require or conflict with itself")
        result.append(requirements if alternatives else requirements[0])
    return tuple(result)


def reject_json_constant(value):
    raise ValueError(f"$: invalid JSON constant {value}")


def load_repository(path):
    path = Path(path)
    try:
        with path.open(encoding="utf-8") as file:
            document = json.load(file, object_pairs_hook=tuple, parse_constant=reject_json_constant)
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: invalid JSON, line {error.lineno}, column {error.colno}: {error.msg}") from error
    except (OSError, ValueError) as error:
        raise ValueError(f"{path}: {error}") from error

    root_path = f"{path}: $"
    root = validate_object(document, root_path, allowed={"packages", "meta"}, required=("packages",))
    packages = validate_object(root["packages"], f"{root_path}.packages")
    names = set()
    package_versions = []
    for name, data in packages.items():
        path = f"{root_path}.packages[{name!r}]"
        if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
            raise ValueError(f"{path}: invalid package name")
        package = normalize_name(name)
        if package in names:
            raise ValueError(f"{path}: duplicate package {package!r}")
        names.add(package)
        data = validate_object(data, path, allowed={"versions"}, required=("versions",))
        versions = validate_object(data["versions"], f"{path}.versions")
        if not versions:
            raise ValueError(f"{path}.versions: a package must have at least one version")
        seen_versions = set()
        for version_text, details in versions.items():
            location = f"{path}.versions[{version_text!r}]"
            try:
                version = Version.parse(version_text)
            except ValueError as error:
                raise ValueError(f"{location}: {error}") from error
            if version in seen_versions:
                raise ValueError(f"{location}: duplicate version")
            seen_versions.add(version)
            details = validate_object(details, location, allowed={"requires", "conflicts"})
            requires = parse_dependencies(details.get("requires", []), f"{location}.requires", package, True)
            conflicts = parse_dependencies(details.get("conflicts", []), f"{location}.conflicts", package, False)
            package_versions.append(PackageVersion(package, version, requires, conflicts))
    repository = Repository(package_versions)
    for message in repository.warnings():
        print(f"Warning: {message}", file=sys.stderr)
    return repository


def load_requests():
    pass


def load_state(path, repository=None):
    path = Path(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ValueError(f"{path}: {error}") from error

    state = State()
    for line_number, line in enumerate(lines, start=1):
        text = line.split("#", 1)[0].strip()
        if not text:
            continue
        try:
            fields = text.split()
            if len(fields) not in (2, 3) or (len(fields) == 3 and fields[2] != "manual"):
                raise ValueError("expected NAME VERSION or NAME VERSION manual")
            name, version_text = fields[:2]
            if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
                raise ValueError(f"invalid package name: {name!r}")
            package = normalize_name(name)
            version = Version.parse(version_text)
            if package in state.installed:
                raise ValueError(f"duplicate package: {package!r}")
            state.install(package, version, manual=len(fields) == 3)
        except ValueError as error:
            raise ValueError(f"{path}: line {line_number}: {error}") from error

    if repository is not None:
        errors = validate_state(repository, state)
        if errors:
            raise ValueError(f"{path}: invalid state:\n" + "\n".join(errors))
    return state


def save_state(state, path):
    path = Path(path)
    text = "".join(
        f"{package} {version}{' manual' if package in state.manual else ''}\n"
        for package, version in sorted(state.installed.items())
    )
    try:
        path.write_text(text, encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ValueError(f"{path}: {error}") from error
