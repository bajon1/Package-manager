import operator
import re
from dataclasses import dataclass, field


def normalize_name(name):
    return re.sub(r"[-_.]+", "-", name.lower())


@dataclass(frozen=True, order=True)
class Version:
    version: tuple
    version_str: str = field(compare=False)

    @classmethod
    def parse(cls, version_str):
        if not re.fullmatch(r"[0-9]+(\.[0-9]+)*", version_str):
            raise ValueError(f"Incorrect version: {version_str!r}")

        version_parts = [int(c) for c in version_str.split(".")]

        for i in range(len(version_parts) - 1, -1, -1):
            if version_parts[i] == 0 and i > 0:
                version_parts.pop(i)
            else:
                break

        return cls(tuple(version_parts), version_str)

    def __str__(self):
        return self.version_str


OPS = {"==": operator.eq, "!=": operator.ne, "<": operator.lt,
       "<=": operator.le, ">": operator.gt, ">=": operator.ge}


@dataclass(frozen=True)
class Constraint:
    op: str
    version: Version

    def matches(self, v):
        return OPS[self.op](v, self.version)

    def __str__(self):
        return f"{self.op}{self.version}"


_OP = r"(?:==|!=|<=|>=|<|>)"
_VER = r"[0-9]+(?:\.[0-9]+)*"
_ONE = rf"{_OP}\s*{_VER}"
_NAME_RE = re.compile(r"\s*([A-Za-z0-9._-]+)(.*)", re.S)
_TAIL_RE = re.compile(rf"\s*(?:{_ONE}(?:\s*,?\s*{_ONE})*)?\s*")
_CONSTRAINT_RE = re.compile(rf"({_OP})\s*({_VER})")


@dataclass(frozen=True)
class Requirement:
    package: str
    constraints: tuple = ()

    @classmethod
    def parse(cls, text):
        m = _NAME_RE.fullmatch(text)
        if not m:
            raise ValueError(f"Incorrect requirement (name): {text!r}")
        name, tail = m.groups()

        if not _TAIL_RE.fullmatch(tail):
            raise ValueError(f"Incorrect requirement (constraints): {text!r}")

        constraints = tuple(Constraint(op, Version.parse(ver))
                            for op, ver in _CONSTRAINT_RE.findall(tail))
        return cls(normalize_name(name), constraints)

    def matches(self, v):
        return all(c.matches(v) for c in self.constraints)

    def __str__(self):
        return " ".join([self.package, *map(str, self.constraints)])


def parse_alternative(text):
    return tuple(Requirement.parse(part) for part in text.split("|"))


def alternative_to_str(alternative):
    return " | ".join(map(str, alternative))


@dataclass(frozen=True)
class PackageVersion:
    package: str
    version: Version
    requires: tuple = ()
    conflicts: tuple = ()

    def __str__(self):
        return f"{self.package}=={self.version}"


class Repository:
    def __init__(self, package_versions):
        grouped = {}
        for pv in package_versions:
            grouped.setdefault(pv.package, []).append(pv)
        self._by_package = {
            package: sorted(pvs, key=lambda pv: pv.version, reverse=True)
            for package, pvs in grouped.items()
        }

    def package_names(self):
        return list(self._by_package)

    def versions(self, package):
        return self._by_package.get(package, [])

    def matching(self, requirement):
        return [pv for pv in self.versions(requirement.package)
                if requirement.matches(pv.version)]

    def obsolescence(self, package, version):
        return [pv.version for pv in self.versions(package)].index(version)

    def warnings(self):
        messages = []
        for package in self._by_package:
            for pv in self.versions(package):
                for alternative in pv.requires:
                    for requirement in alternative:
                        if not self.matching(requirement):
                            messages.append(
                                f"{pv}: wymaganie '{requirement}' nie pasuje do żadnej wersji w repozytorium")
        return messages


@dataclass
class State:
    installed: dict = field(default_factory=dict)
    manual: set = field(default_factory=set)

    def install(self, package, version, manual=False):
        self.installed[package] = version
        if manual:
            self.manual.add(package)

    def version_of(self, package):
        return self.installed.get(package)

    def __str__(self):
        parts = [f"{p} {v}" for p, v in sorted(self.installed.items())]
        return ", ".join(parts)
