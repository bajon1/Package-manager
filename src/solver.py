from dataclasses import dataclass, field

import z3

from src.knowledge_base import Axiom, KnowledgeBase
from src.model import State
from src.validator import validate_state


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
    status = opt.check()
    if status == z3.unsat:
        return None
    if status != z3.sat:
        raise RuntimeError(f"Solver returned unknown: {opt.reason_unknown()}")
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


def state_change_terms(kb, state):
    removed_terms, changed_terms = [], []
    for package, version in state.installed.items():
        installed = kb.inst(package)
        removed_terms.append((1, z3.Not(installed)))
        changed_terms.append((1, z3.And(installed, z3.Not(kb.x[(package, version)]))))
    return removed_terms, changed_terms


def existing_install_objectives(kb, requested, state):
    removed_terms, changed_terms = state_change_terms(kb, state)

    requested_terms, new_terms, other_terms = [], [], []
    for (package, version), lit in kb.x.items():
        if package in state.installed:
            continue
        new_terms.append((1, lit))
        weight = kb.obs[(package, version)]
        if weight:
            target = requested_terms if package in requested else other_terms
            target.append((weight, lit))
    return [Objective("removed packages", removed_terms),
            Objective("version changes", changed_terms),
            Objective("new requested package obsolescence", requested_terms),
            Objective("new packages", new_terms),
            Objective("other new package obsolescence", other_terms)]


def install(kb: KnowledgeBase, requests, state=None):
    requests = list(requests)
    state = state if state is not None else State()
    errors = validate_state(kb.repo, state)
    if errors:
        raise ValueError("Invalid initial state:\n" + "\n".join(errors))
    requested = {r.package for r in requests}
    hard = [kb.request_axiom(r) for r in requests]
    objectives = (existing_install_objectives(kb, requested, state) if state.installed
                  else install_objectives(kb, requested))
    solution = solve_lex(kb, hard, objectives)
    if solution is not None:
        solution.state.manual = (state.manual & solution.state.installed.keys()) | requested
        errors = validate_state(kb.repo, solution.state, requests)
        if errors:
            raise ValueError("Invalid solver result:\n" + "\n".join(errors))
    return solution


def removal_objectives(kb, packages, state, autoremove=False):
    removed_terms, changed_terms = state_change_terms(kb, state)
    manual_terms = [(1, z3.Not(kb.inst(p))) for p in sorted(state.manual - packages)]
    new_terms = [(1, lit) for (p, _), lit in kb.x.items() if p not in state.installed]
    last_terms = [(1, lit) for lit in kb.x.values()] if autoremove else removed_terms
    return [Objective("removed manual packages outside request", manual_terms),
            Objective("version changes", changed_terms),
            Objective("new packages", new_terms),
            Objective("installed packages" if autoremove else "removed packages", last_terms)]


def remove(kb: KnowledgeBase, packages, state, autoremove=False):
    packages = set(packages)
    errors = validate_state(kb.repo, state)
    if errors:
        raise ValueError("Invalid initial state:\n" + "\n".join(errors))
    hard = [Axiom("REMOVE", f"remove: {p}", z3.Not(kb.inst(p))) for p in sorted(packages)]
    solution = solve_lex(kb, hard, removal_objectives(kb, packages, state, autoremove))
    if solution is not None:
        solution.state.manual = state.manual & solution.state.installed.keys()
        errors = validate_state(kb.repo, solution.state)
        errors.extend(f"Removed package remains installed: {p}"
                      for p in sorted(packages & solution.state.installed.keys()))
        if errors:
            raise ValueError("Invalid solver result:\n" + "\n".join(errors))
    return solution
