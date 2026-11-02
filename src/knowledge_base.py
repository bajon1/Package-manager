from dataclasses import dataclass
import z3

@dataclass(frozen=True)
class Axiom:
    text_id: str
    label : str
    formula: z3.BoolRef


class KnowledgeBase:
    def __init__(self, repo):
        self.repo = repo
        self.x = {}
        self.status = {}

        for package in repo.package_names():
            for index, pv in enumerate(repo.versions(package)):
                key = (package, pv.version)
                self.x[key] = z3.Bool(str(pv))
                self.status[key] = index

