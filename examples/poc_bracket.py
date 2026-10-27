"""RealCAD 개념 증명: 같은 브래킷을 '불량 배치' vs '수정 배치'로 만들어
커널 검증이 볼트 머리 간섭·공차·연단거리를 실제로 잡는지 보여주고, 통과한 걸 STEP/STL로 뽑는다.

실행: .venv/bin/python examples/poc_bracket.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from realcad.fasteners.standards import get
from realcad.geometry import builder as g
from realcad.verify import checks as v
from realcad.export import exporters as ex

# 판: 80 x 50 x 6 (mm), 윗면 z=0. x:[-40,40], y:[-25,25]
L, W, T = 80.0, 50.0, 6.0
WALL_X, WALL_T, WALL_H = 30.0, 6.0, 25.0   # +x쪽에 선 벽 (x 27..33)
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
    # H2: 홀-볼트 공차 (설계 전체에 한 번)
    findings.append(v.h2_hole_clearance(hole_dia, f, FIT))
    bolts = []
    for i, (x, y) in enumerate(holes, 1):
        bolt = g.place(g.hex_bolt_solid(f, grip_mm=20), x, y)
        bolts.append(bolt)
        findings.append(v.h1_interference(bolt, wall_solid, f"홀{i}↔벽"))
        findings.append(v.h4_edge_distance(edge_distance(x, y), f))
    # 볼트 머리끼리
    for i in range(len(bolts)):
        for j in range(i + 1, len(bolts)):
            findings.append(v.h1_interference(bolts[i], bolts[j], f"홀{i+1}↔홀{j+1}"))
    # S2: 홀 간 거리
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


# 1) 불량 배치: 구멍을 벽·모서리에 붙이고, 볼트 외경 그대로(공차 없음)
naive, naive_res = build_and_verify(
    "불량 배치 (naive)", holes=[(34.0, 0.0)], hole_dia=f.nominal_dia_mm)

# 2) 수정 배치: 벽에서 떨어뜨리고, 규격 clearance hole
fixed, fixed_res = build_and_verify(
    "수정 배치 (fixed)", holes=[(10.0, 12.0), (10.0, -12.0)], hole_dia=hole_dia_fixed)

# 통과한 것만 내보내기
out = Path(__file__).resolve().parents[1] / "out"
out.mkdir(exist_ok=True)
if fixed_res["passed"]:
    sp = ex.to_step(fixed, out / "bracket_fixed.step")
    st = ex.to_stl(fixed, out / "bracket_fixed.stl")
    print(f"\n내보냄: {sp.name} ({sp.stat().st_size} B), {st.name} ({st.stat().st_size} B)")
else:
    print("\n수정 배치가 아직 검증을 통과 못 해 내보내지 않음")
