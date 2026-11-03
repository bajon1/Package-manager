from dataclasses import dataclass, field

import z3

from .explanations import check, minimal_core
from .knowledge_base import Axiom
from .solver import solve_lex, update_constraints, update_objectives, verify_update


@dataclass
class UpdateAnalysis:
    newest: dict
    conflict: list | None = None
    conflicting_packages: tuple = ()
    frontier: list = field(default_factory=list)


def pareto_frontier(kb, packages, state, conflicting_packages):
    packages, hard = update_constraints(kb, packages, state)
    opt = z3.Optimize()
    opt.set(priority="pareto")
    opt.add([a.formula for a in [*kb.axioms, *hard]])
    for package in conflicting_packages:
        terms = [z3.If(kb.var(pv), kb.obs[(package, pv.version)], 0) for pv in kb.repo.versions(package)]
        opt.minimize(z3.Sum(terms) if terms else z3.IntVal(0))
    frontier, seen = [], set()
    while True:
        status = opt.check()
        if status == z3.unsat:
            break
        if status != z3.sat:
            raise RuntimeError(f"Solver returned unknown: {opt.reason_unknown()}")
        model = opt.model()
        versions = {package: next(pv.version for pv in kb.repo.versions(package)
                                  if z3.is_true(model.eval(kb.var(pv), model_completion=True)))
                    for package in conflicting_packages}
        point = tuple(kb.obs[(p, versions[p])] for p in conflicting_packages)
        if point in seen:
            continue
        seen.add(point)
        fixed = [Axiom("PARETO", f"Pareto choice: {p}=={v}", kb.x[(p, v)]) for p, v in versions.items()]
        solution = solve_lex(kb, [*hard, *fixed], update_objectives(kb, packages, state))
        if solution is None:
            raise RuntimeError("A Pareto point unexpectedly became unsatisfiable.")
        frontier.append(verify_update(kb, solution, packages, state))
    return sorted(frontier, key=lambda row: tuple(kb.obs[(p, row.state.installed[p])] for p in conflicting_packages))


def analyze_update(kb, packages, state):
    packages, hard = update_constraints(kb, packages, state)
    solver = z3.Solver()
    solver.add([a.formula for a in [*kb.axioms, *hard]])
    newest = {}
    for package in sorted(packages):
        for pv in kb.repo.versions(package):
            solver.push()
            solver.add(kb.var(pv))
            status = check(solver)
            solver.pop()
            if status == z3.sat:
                newest[package] = pv.version
                break
        if package not in newest:
            raise ValueError(f"No reachable version of installed package: {package}")

    targets = {p: Axiom("NEWEST", f"newest reachable: {p}=={v}", kb.x[(p, v)]) for p, v in newest.items()}
    core = minimal_core([*kb.axioms, *hard, *targets.values()])
    if core is None:
        return UpdateAnalysis(newest)
    # One minimal core may omit other independent conflicts; include every update target.
    frontier = pareto_frontier(kb, packages, state, tuple(sorted(packages)))
    conflicting = tuple(p for p in sorted(packages)
                        if any(row.state.installed[p] != newest[p] for row in frontier))
    return UpdateAnalysis(newest, core, conflicting, frontier)
