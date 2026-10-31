from functools import total_ordering

@total_ordering
class Version:
    def __init__(self, version_str):
        self.version_str = version_str
        version_parts = [int(c) for c in version_str.split(".")]

        for i in range(len(version_parts) - 1, -1, -1):
            if version_parts[i] == 0:
                version_parts.pop(i)
            else:
                break

        self.version = tuple(version_parts)

    def __eq__(self, other):
        return self.version == other.version

    def __lt__(self, other):
        return self.version < other.version

    def __hash__(self):
        return hash(self.version)

    def __str__(self):
        return self.version_str

class Constraint:
    pass

class Requirement:
    pass


print(Version("1.10.0"))
print(Version("1.10") > Version("1.9"))
print(Version("1.0") == Version("1.0.0"))