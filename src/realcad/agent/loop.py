"""Generate -> verify -> judge loop. On failure the judge fixes parameters and re-verifies."""
from __future__ import annotations
from ..pipeline import build_and_verify
from .judge import fix


def run(contract, max_iters: int = 3, verbose: bool = True) -> dict:
    c = contract
    part = findings = summ = None
    for it in range(max_iters + 1):
        part, f, dia, findings, summ = build_and_verify(c)
        if verbose:
            tag = "PASS ✅" if summ["passed"] else f"FAIL {summ['hard_fail']}"
            print(f"  [iter {it}] {tag}  holes={[(round(h.x,1), round(h.y,1)) for h in c.holes]}")
        if summ["passed"]:
            return {"contract": c, "part": part, "findings": findings,
                    "summary": summ, "iters": it, "fixed": it > 0}
        if it == max_iters or c.kind != "plate":
            break   # judge auto-fix only applies to plate (bolt layout)
        failed = [fd for fd in findings if fd.severity == "HARD" and not fd.ok]
        c, _usage, _raw = fix(c.to_dict(), failed)
    return {"contract": c, "part": part, "findings": findings,
            "summary": summ, "iters": max_iters, "fixed": False}
