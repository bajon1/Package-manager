from dataclasses import dataclass, field

import z3

from src.knowledge_base import KnowledgeBase
from src.model import State


@dataclass
class Objective:
    name: str
    terms: list

    def expr(self):
        return z3.Sum([z3.If(lit, w, 0) for w, lit in self.terms])


@dataclass
class Solution:
    state: State
    values: dict = field(default_factory=dict)


def solve_lex(kb, hard, objectives):
    opt = z3.Optimize()
    opt.set(priority="lex")
    for axiom in kb.axioms:
        opt.add(axiom.formula)
    for axiom in hard:
        opt.add(axiom.formula)
    for objective in objectives:
        if objective.terms:
            opt.minimize(objective.expr())
    if opt.check() != z3.sat:
        return None
    model = opt.model()

    def is_true(lit):
        return z3.is_true(model.eval(lit, model_completion=True))

    state = State()
    for (package, version), lit in kb.x.items():
        if is_true(lit):
            state.install(package, version)
    values = {o.name: sum(w for w, lit in o.terms if is_true(lit)) for o in objectives}
    return Solution(state, values)



def install_objectives(kb, requested):
    requested_terms, count_terms, other_terms = [], [], []
    for (package, version), lit in kb.x.items():
        count_terms.append((1, lit))
        if kb.obs[(package, version)] == 0:
            continue                      # weight 0 does not affect the sum
        target = requested_terms if package in requested else other_terms
        target.append((kb.obs[(package, version)], lit))
    return [Objective("requested package obsolescence", requested_terms),
            Objective("number of packages", count_terms),
            Objective("other package obsolescence", other_terms)]


def install(kb: KnowledgeBase, requests):
    requested = {r.package for r in requests}
    hard = [kb.request_axiom(r) for r in requests]
    solution = solve_lex(kb, hard, install_objectives(kb, requested))
    if solution is not None:
        solution.state.manual = set(requested)
    return solution