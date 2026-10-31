import json
import re
import sys
from pathlib import Path

from .model import PackageVersion, Repository, Requirement, Version, normalize_name, parse_alternative



def validate_object(value, path, allowed=None, required=()):
    if not isinstance(value, tuple):
        raise ValueError(f"{path or '$'}: oczekiwano obiektu JSON")
    result = {}
    for key, item in value:
        if path.endswith((".packages", ".versions")):
            location = f"{path}[{key!r}]"
        else:
            location = f"{path}.{key}" if path else key
        if key in result:
            raise ValueError(f"{location}: powtórzony klucz")
        if allowed is not None and key not in allowed:
            raise ValueError(f"{location}: nieznane pole")
        result[key] = item
    for key in required:
        if key not in result:
            location = f"{path}.{key}" if path else key
            raise ValueError(f"{location}: brak wymaganego pola")
    return result


def parse_dependencies(value, path, package, alternatives):
    if not isinstance(value, list):
        raise ValueError(f"{path}: oczekiwano listy napisów")
    result = []
    for index, text in enumerate(value):
        location = f"{path}[{index}]"
        if not isinstance(text, str):
            raise ValueError(f"{location}: oczekiwano napisu")
        try:
            requirements = parse_alternative(text) if alternatives else (Requirement.parse(text),)
        except ValueError as error:
            raise ValueError(f"{location}: {error}") from error
        if any(requirement.package == package for requirement in requirements):
            raise ValueError(f"{location}: pakiet nie może wymagać siebie ani konfliktować ze sobą")
        result.append(requirements if alternatives else requirements[0])
    return tuple(result)


def reject_json_constant(value):
    raise ValueError(f"$: niedozwolona stała JSON {value}")


def load_repository(path):
    path = Path(path)
    try:
        with path.open(encoding="utf-8") as file:
            document = json.load(file, object_pairs_hook=tuple, parse_constant=reject_json_constant)
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: niepoprawny JSON, linia {error.lineno}, kolumna {error.colno}: {error.msg}") from error
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
            raise ValueError(f"{path}: niepoprawna nazwa pakietu")
        package = normalize_name(name)
        if package in names:
            raise ValueError(f"{path}: powtórzony pakiet {package!r}")
        names.add(package)
        data = validate_object(data, path, allowed={"versions"}, required=("versions",))
        versions = validate_object(data["versions"], f"{path}.versions")
        if not versions:
            raise ValueError(f"{path}.versions: pakiet musi mieć co najmniej jedną wersję")
        seen_versions = set()
        for version_text, details in versions.items():
            location = f"{path}.versions[{version_text!r}]"
            try:
                version = Version.parse(version_text)
            except ValueError as error:
                raise ValueError(f"{location}: {error}") from error
            if version in seen_versions:
                raise ValueError(f"{location}: powtórzona wersja")
            seen_versions.add(version)
            details = validate_object(details, location, allowed={"requires", "conflicts"})
            requires = parse_dependencies(details.get("requires", []), f"{location}.requires", package, True)
            conflicts = parse_dependencies(details.get("conflicts", []), f"{location}.conflicts", package, False)
            package_versions.append(PackageVersion(package, version, requires, conflicts))
    repository = Repository(package_versions)
    for message in repository.warnings():
        print(f"Ostrzeżenie: {message}", file=sys.stderr)
    return repository


def load_requests():
    pass


def load_state():
    pass
