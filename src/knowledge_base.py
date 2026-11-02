from dataclasses import dataclass
import z3

from model import *

@dataclass(frozen=True)
class Axiom:
    text_id: str
    label: str
    formula: z3.BoolRef


class KnowledgeBase:
    def __init__(self, repo):
        self.repo = repo
        self.x = {}
        self.obs = {}

        for package in repo.package_names():
            for index, pv in enumerate(repo.versions(package)):
                key = (package, pv.version)
                self.x[key] = z3.Bool(str(pv))
                self.obs[key] = index

        for package in repo.package_names():
            self._add_at_most_one(package)
            for pv in repo.versions(package):
                self._add_requires(pv)
                self._add_conflicts(pv)

        def var(self, pv):
            return self.x[(pv.package, pv.version)]

        def vars_of(self, package):
            return [self.var(pv) for pv in self.repo.versions(package)]

        def inst(self, package):
            lits = self.vars_of(package)
            return z3.Or(lits) if lits else z3.BoolVal(False)

        def candidates(self, requirement):
            return [self.var(pv) for pv in self.repo.matching(requirement)]

        def _add(self, kind, label, formula):
            self.axioms.append(Axiom(kind, label, formula))

        def _add_at_most_one(self, package):
            lits = self.vars_of(package)
            if len(lits) > 1:
                self._add("A1", f"at most one version of package {package}",
                          z3.AtMost(*lits, 1))

        def _add_requires(self, pv):
            for alternative in pv.requires:
                lits = [lit for requirement in alternative
                        for lit in self.candidates(requirement)]

                consequence = z3.Or(lits) if lits else z3.BoolVal(False)
                self._add("A2", f"{pv} requires {alternative_to_str(alternative)}",
                          z3.Implies(self.var(pv), consequence))

        def _add_conflicts(self, pv):
            for requirement in pv.conflicts:
                lits = self.candidates(requirement)
                if lits:
                    self._add("A3", f"{pv} conflicts with {requirement}",
                              z3.Implies(self.var(pv), z3.And([z3.Not(l) for l in lits])))

        def request_axiom(self, requirement):
            lits = self.candidates(requirement)
            formula = z3.Or(lits) if lits else z3.BoolVal(False)
            return Axiom("REQUEST", f"request: {requirement}", formula)

        def describe(self):
            return "\n".join(f"[{a.kind}] {a.label}:  {a.formula}" for a in self.axioms)
