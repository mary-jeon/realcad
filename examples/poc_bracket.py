"""RealCAD proof of concept: build the same bracket with a 'bad layout' and a 'fixed layout' to show that
kernel verification really catches bolt head interference, clearance and edge distance, then export the passing one to STEP/STL.

Run: .venv/bin/python examples/poc_bracket.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from realcad.fasteners.standards import get
from realcad.geometry import builder as g
from realcad.verify import checks as v
from realcad.export import exporters as ex

# Plate: 80 x 50 x 6 (mm), top face z=0. x:[-40,40], y:[-25,25]
L, W, T = 80.0, 50.0, 6.0
WALL_X, WALL_T, WALL_H = 30.0, 6.0, 25.0   # wall standing on the +x side (x 27..33)
f = get("1/4-20")
FIT = "normal"
hole_dia_fixed = f.clearance(FIT)          # 7.14mm


def edge_distance(x, y):
    return min(L / 2 - x, L / 2 + x, W / 2 - y, W / 2 + y)


def build_and_verify(name, holes, hole_dia):
    """holes: [(x,y), ...]"""
    part = g.plate(L, W, T)
    part = part + g.wall(WALL_X, W, WALL_H, WALL_T)
    for (x, y) in holes:
        part = g.drill(part, x, y, hole_dia, T)

    wall_solid = g.wall(WALL_X, W, WALL_H, WALL_T)
    findings = []
    # H2: hole/bolt clearance (once for the whole design)
    findings.append(v.h2_hole_clearance(hole_dia, f, FIT))
    bolts = []
    for i, (x, y) in enumerate(holes, 1):
        bolt = g.place(g.hex_bolt_solid(f, grip_mm=20), x, y)
        bolts.append(bolt)
        findings.append(v.h1_interference(bolt, wall_solid, f"홀{i}↔벽"))
        findings.append(v.h4_edge_distance(edge_distance(x, y), f))
    # bolt head vs bolt head
    for i in range(len(bolts)):
        for j in range(i + 1, len(bolts)):
            findings.append(v.h1_interference(bolts[i], bolts[j], f"홀{i+1}↔홀{j+1}"))
    # S2: hole spacing
    for i in range(len(holes)):
        for j in range(i + 1, len(holes)):
            d = ((holes[i][0]-holes[j][0])**2 + (holes[i][1]-holes[j][1])**2) ** 0.5
            findings.append(v.s2_hole_spacing(d, f))

    res = v.summarize(findings)
    print(f"\n===== {name} =====")
    print(f"볼트: {f.name}, 구멍 Ø{hole_dia:.2f} ({FIT} fit, 규격 {f.clearance(FIT):.2f})")
    for fd in findings:
        print("  " + str(fd))
    print(f"  판정: {'통과 ✅' if res['passed'] else 'HARD 실패 ❌ ' + str(res['hard_fail'])}"
          + (f" / 경고 {res['soft_warn']}" if res['soft_warn'] else ""))
    return part, res


# 1) Bad layout: holes against the wall and edge, bolt OD as is (no clearance)
naive, naive_res = build_and_verify(
    "불량 배치 (naive)", holes=[(34.0, 0.0)], hole_dia=f.nominal_dia_mm)

# 2) Fixed layout: away from the wall, standard clearance hole
fixed, fixed_res = build_and_verify(
    "수정 배치 (fixed)", holes=[(10.0, 12.0), (10.0, -12.0)], hole_dia=hole_dia_fixed)

# Export only what passed
out = Path(__file__).resolve().parents[1] / "out"
out.mkdir(exist_ok=True)
if fixed_res["passed"]:
    sp = ex.to_step(fixed, out / "bracket_fixed.step")
    st = ex.to_stl(fixed, out / "bracket_fixed.stl")
    print(f"\n내보냄: {sp.name} ({sp.stat().st_size} B), {st.name} ({st.stat().st_size} B)")
else:
    print("\n수정 배치가 아직 검증을 통과 못 해 내보내지 않음")
