from dataclasses import dataclass
from functools import partial
import re

from packaging.requirements import Requirement as PepRequirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version as PepVersion

from .model import PackageVersion, Repository, normalize_name
from .parser import validate_object


@dataclass(frozen=True)
class PypiRequirement:
    package: str
    specifier: SpecifierSet

    def matches(self, version):
        return self.specifier.contains(str(version), prereleases=True)

    def __str__(self):
        return f"{self.package}{self.specifier}"


def parse_requirement(text, environment):
    requirement = PepRequirement(text)
    if requirement.marker is not None:
        marker_source = text.split(";", 1)[1]
        unquoted = re.sub(r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*' ''', "", marker_source, flags=re.X)
        fields = set(re.findall(r"\b[A-Za-z_][A-Za-z_0-9]*\b", unquoted)) - {"and", "or", "in", "not"}
        missing = fields - environment.keys() - {"extra"}
        if missing:
            raise ValueError("target environment does not define: " + ", ".join(sorted(missing)))
        if not requirement.marker.evaluate({**environment, "extra": ""}):
            return None
    if requirement.url is not None:
        raise ValueError("URL requirements cannot be resolved from version-only repository data")
    return PypiRequirement(normalize_name(requirement.name), requirement.specifier)


def parse_repository(packages, metadata, root_path):
    metadata = validate_object(metadata, f"{root_path}.meta", required=("environment",))
    environment = validate_object(metadata["environment"], f"{root_path}.meta.environment")
    if not all(isinstance(value, str) for value in environment.values()):
        raise ValueError(f"{root_path}.meta.environment: expected string values")
    python_version = environment.get("python_full_version") or environment.get("python_version")
    if not python_version:
        raise ValueError(f"{root_path}.meta.environment: Python version is required")
    try:
        target_python = PepVersion(python_version)
    except ValueError as error:
        raise ValueError(f"{root_path}.meta.environment: {error}") from error
    environment.setdefault("python_full_version", python_version)
    environment.setdefault("python_version", ".".join(python_version.split(".")[:2]))
    parser = partial(parse_requirement, environment=environment)
    names, package_versions = set(), []
    for name, data in packages.items():
        location = f"{root_path}.packages[{name!r}]"
        if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
            raise ValueError(f"{location}: invalid package name")
        package = normalize_name(name)
        if package in names:
            raise ValueError(f"{location}: duplicate package {package!r}")
        names.add(package)
        data = validate_object(data, location, allowed={"versions"}, required=("versions",))
        versions = validate_object(data["versions"], f"{location}.versions")
        if not versions:
            raise ValueError(f"{location}.versions: a package needs at least one source version")
        seen = set()
        for text, details in versions.items():
            version_path = f"{location}.versions[{text!r}]"
            try:
                version = PepVersion(text)
                if version in seen:
                    raise ValueError("duplicate equivalent version")
                seen.add(version)
                details = validate_object(details, version_path, allowed={"requires_dist", "requires_python"})
                python_specifier = details.get("requires_python")
                if python_specifier is not None and not isinstance(python_specifier, str):
                    raise ValueError("requires_python: expected a string or null")
                compatible = SpecifierSet(python_specifier or "").contains(target_python, prereleases=True)
                requirements = details.get("requires_dist")
                if requirements is None:
                    requirements = []
                if not isinstance(requirements, list):
                    raise ValueError("requires_dist: expected a list or null")
                if not compatible:
                    continue
                parsed = []
                for index, requirement in enumerate(requirements):
                    try:
                        if not isinstance(requirement, str):
                            raise ValueError("expected a requirement string")
                        result = parser(requirement)
                        if result is not None:
                            if result.package == package:
                                raise ValueError("a package cannot require itself")
                            parsed.append((result,))
                    except ValueError as error:
                        raise ValueError(f"requires_dist[{index}]: {error}") from error
                package_versions.append(PackageVersion(package, version, tuple(parsed)))
            except ValueError as error:
                raise ValueError(f"{version_path}: {error}") from error
    return Repository(package_versions, parse_version=PepVersion, parse_requirement=parser, environment=environment)
