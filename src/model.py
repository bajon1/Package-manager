from dataclasses import dataclass, field
import re

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
            if version_parts[i] == 0 and i>0:
                version_parts.pop(i)
            else:
                break

        return cls(tuple(version_parts), version_str)

    def __str__(self):
        return self.version_str

class Constraint:
    pass

class Requirement:
    pass

print(Version.parse("0").version)
print(Version.parse("1.10.0"))
print(Version.parse("1.10") > Version.parse("1.9"))
print(Version.parse("1.0") == Version.parse("1.0.0"))
print(Version.parse("-1"))