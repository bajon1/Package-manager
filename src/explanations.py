import z3


def check(solver):
    status = solver.check()
    if status == z3.unknown:
        raise RuntimeError(f"Solver returned unknown: {solver.reason_unknown()}")
    return status


def minimal_core(axioms):
    """Return a subset-minimal conflict, or None when all axioms are satisfiable."""
    axioms = list(axioms)
    solver = z3.Solver()
    markers = [z3.FreshBool("core") for _ in axioms]
    for marker, axiom in zip(markers, axioms):
        solver.assert_and_track(axiom.formula, marker)
    if check(solver) == z3.sat:
        return None
    selected = {marker.get_id() for marker in solver.unsat_core()}
    core = [a for marker, a in zip(markers, axioms) if marker.get_id() in selected]
    index = 0
    while index < len(core):
        trial = core[:index] + core[index + 1:]
        solver = z3.Solver()
        solver.add([axiom.formula for axiom in trial])
        if check(solver) == z3.unsat:
            core = trial
        else:
            index += 1
    return core


def explain(kb, requests):
    return minimal_core([*kb.axioms, *(kb.request_axiom(r) for r in requests)])
