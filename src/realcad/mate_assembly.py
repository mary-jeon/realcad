"""Mate assembly pipeline: parts + mates (or an instruction) -> placed assembly, checks, BOM, files.

J1 mates met       : every mate measured again on the placed parts (error <= 0.02 mm, 0.05 deg)
J2 parts defined   : parts with free directions left (slide or spin) are listed (SOFT, a hinge may be on purpose)
J3 parts connected : every part is tied to the fixed part by mates (HARD, a part left where it was is not assembled)
A1 interference    : intersection volume of every pair of placed parts (same check as the presets)
B1, B2             : assembly audit (material and spec present, quantity = solids modelled)
"""
from __future__ import annotations

from pathlib import Path

from .geometry import mates as M
from .verify.checks import Finding

PALETTE = ["#9aa7b2", "#3f8f5a", "#2f4f8f", "#c9b27c", "#c94c4c", "#6fa8dc", "#8a5a44", "#e8a33c", "#5c6670", "#7d9b86"]


class _Named:
    def __init__(self, name, solid):
        self.name, self.solid = name, solid


def _j1(measured: list[dict]) -> Finding:
    bad = [m for m in measured if not m["ok"]]
    ok = not bad
    msg = (f"메이트 {len(measured)}개 모두 맞음 / all mates met (최대 오차 {max([m['error_mm'] for m in measured] or [0]):.3f} mm)" if ok else
           f"맞지 않는 메이트 {len(bad)}개: " + "; ".join(f"{m['no']}번 {m['type']} {m['a']}~{m['b']} 오차 {m['error_mm']} mm, {m['error_deg']}도" for m in bad[:4]))
    return Finding("J1", "HARD", ok, msg, actual=float(max([m["error_mm"] for m in measured] or [0])), required=M.TOL_MM,
                   standard="놓은 뒤 메이트마다 다시 잼: 거리 0.02 mm, 각도 0.05도 이내",
                   suggestion={} if ok else {"option_a": "구멍 간격이 서로 같은 짝을 고르기", "option_b": "겹치게 걸린 메이트 하나 빼기"})


def _j3(parts: list[M.MatePart], unplaced: list[str]) -> Finding:
    ok = not unplaced
    msg = (f"부품 {len(parts)}개 모두 고정 부품과 메이트로 연결됨 / all connected" if ok else
           "고정 부품과 연결되지 않아 제자리에 둔 부품 / not connected: " + ", ".join(unplaced))
    return Finding("J3", "HARD", ok, msg, actual=float(len(unplaced)), required=0.0,
                   standard="고정 부품에서 메이트를 따라가면 모든 부품에 닿아야 함",
                   suggestion={} if ok else {"option_a": "그 부품과 이미 놓인 부품 사이에 메이트 추가"})


def _j2(parts: list[M.MatePart], unplaced: list[str]) -> Finding:
    loose = [f"{p.name}({M.dof_text(p.dof)})" for p in parts if p.dof and not p.dof.get("fixed")
             and (p.dof.get("move_free") or p.dof.get("turn_free"))]
    ok = not loose
    if loose:
        msg = "덜 구속된 부품 / under defined: " + "; ".join(loose[:4])
    else:
        n = len(parts) - len(unplaced)
        msg = f"연결된 부품 {n}개 모두 완전 구속 / fully defined"
    return Finding("J2", "SOFT", ok, msg, actual=float(len(loose)), required=0.0,
                   standard="고정 부품 1개 + 나머지는 메이트로 위치와 방향이 하나로 정해짐",
                   suggestion={} if ok else {"option_a": "남은 방향을 막는 메이트 하나 더 (구멍 하나 더 동심 또는 면 하나 더 일치)"})


def run(parts: list[M.MatePart], mates: list[dict] | None = None, instruction: str | None = None,
        max_tries: int = 2) -> dict:
    """Solve and check. With an instruction and no mates, the Meta model picks the mates (one retry on failure)."""
    from .verify.assembly import a1_interference
    for p in parts:
        if p.feats is None:
            p.feats = M.features(p.solid)
    why, tries, plans = "", 0, []
    if mates is None:
        if not instruction:
            raise M.MateError("메이트나 조립 설명 중 하나는 있어야 해요")
        from .agent import mate_planner
        tables = {p.name: M.feature_table(p.feats, max_planes=80) for p in parts}
        feedback = ""
        while True:
            tries += 1
            mates = []
            try:
                pl = mate_planner.plan(instruction, tables, feedback)
                why, mates = pl["why"], pl["mates"]
                res = M.solve(parts, mates)
                err = None
            except (M.MateError, ValueError) as e:                 # bad JSON or unusable mates get one more try too
                res, err = None, str(e)
            placed = [M.placed_shape(p) for p in parts] if res else None
            a1 = a1_interference([_Named(p.name, s) for p, s in zip(parts, placed)]) if res else None
            plans.append({"mates": mates, "why": why, "error": err})
            bad = err or [m for m in res["mates"] if not m["ok"]] or res["unplaced"] or (not a1.ok)
            if not bad or tries >= max_tries:
                if err:
                    raise M.MateError(err)
                break
            if err:
                feedback = "The solver refused the mates: " + err
            else:
                feedback = "\n".join(
                    [f"mate {m['no']} {m['a']}~{m['b']}: error {m['error_mm']} mm {m['error_deg']} deg" for m in res["mates"] if not m["ok"]] +
                    ([f"parts not tied to the fixed part: {res['unplaced']}"] if res["unplaced"] else []) +
                    ([a1.message] if not a1.ok else []))
            for p in parts:
                p.placement, p.dof = M.Placement(), {}
    else:
        res = M.solve(parts, mates)
        placed = [M.placed_shape(p) for p in parts]
        a1 = a1_interference([_Named(p.name, s) for p, s in zip(parts, placed)])
    from .verify.audit import audit
    placed_parts = [_Named(p.name, s) for p, s in zip(parts, placed)]
    for pp, p in zip(placed_parts, parts):
        pp.no, pp.spec, pp.qty, pp.material = p.no, p.spec, p.qty, p.material
    findings = [_j1(res["mates"]), _j3(parts, res["unplaced"]), _j2(parts, res["unplaced"]), a1] + audit(placed_parts)
    return {"parts": parts, "placed": placed, "placed_parts": placed_parts, "mates": mates, "measured": res["mates"],
            "unplaced": res["unplaced"], "findings": findings, "why": why, "tries": tries, "plans": plans,
            "passed": all(f.ok for f in findings if f.severity == "HARD")}


def write(result: dict, out_dir, tok: str) -> dict:
    """Files for a solved assembly: STEP (all parts, labelled), one STL per part, combined STL, BOM CSV."""
    from build123d import Compound
    from .export import exporters as ex
    from .export import asm_bom
    out_dir = Path(out_dir)
    kids = []
    rows = []
    for i, (p, s) in enumerate(zip(result["parts"], result["placed"])):
        ex.to_stl(s, out_dir / f"{tok}_p{i}.stl")
        rows.append({"no": p.no, "name": p.name, "spec": p.spec, "qty": p.qty, "material": p.material,
                     "color": PALETTE[i % len(PALETTE)], "url": f"gen/{tok}_p{i}.stl", "dof": M.dof_text(p.dof),
                     "placement": p.placement.matrix()})
        try:
            from build123d import Color
            s.color = Color(PALETTE[i % len(PALETTE)])
        except Exception:
            pass
        kids.append(s)
    comp = Compound(children=kids)
    comp.label = "mate_assembly"
    ex.to_step(comp, out_dir / f"{tok}.step")
    ex.to_stl(comp, out_dir / f"{tok}_part.stl")
    bom = asm_bom.build(result["placed_parts"])
    asm_bom.write_csv(bom, out_dir / f"{tok}_bom.csv", "flat")
    return {"parts": rows, "bom": bom["top"], "bom_flat": bom["flat"], "total_mass_g": bom["total_mass_g"],
            "mass_unknown": bom["unknown_material"],
            "downloads": {"STEP": f"gen/{tok}.step", "STL": f"gen/{tok}_part.stl", "BOM": f"gen/{tok}_bom.csv"}}
