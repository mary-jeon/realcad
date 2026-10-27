"""엔드투엔드: 프롬프트 → Muse Spark(설계 계약) → 커널 조립·검증 → STEP/STL.
RealCAD의 "두뇌=메타" 증명.

실행: .venv/bin/python examples/meta_run.py "a wall-mount bracket ..."
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from realcad.agent.planner import plan
from realcad.geometry import builder as g
from realcad.verify import checks as v
from realcad.export import exporters as ex

prompt = sys.argv[1] if len(sys.argv) > 1 else (
    "A wall-mount bracket, about 80x50mm, 6mm thick, with a 25mm tall wall along one "
    "edge, and two 1/4-20 bolt holes to screw it to a wall. Keep the bolts clear of the wall."
)

print(f"[프롬프트] {prompt}\n")
print("[1] Muse Spark 에게 설계 계약 요청...")
contract, usage, raw = plan(prompt)
print(f"    모델 응답(계약): {raw.strip()[:400]}")
print(f"    토큰 usage: {usage}\n")

print("[2] 커널로 계약대로 조립(build123d)...")
part, f, dia = g.build_from_contract(contract)
print(f"    볼트 {f.name}, 구멍 Ø{dia:.2f}, 구멍 {len(contract.holes)}개"
      f"{', 벽 있음' if contract.wall else ''}\n")

print("[3] 빡센 검증(커널 실측)...")
L, W, T = contract.plate.length, contract.plate.width, contract.plate.thickness
findings = [v.h2_hole_clearance(dia, f, contract.fit)]
wall_solid = (g.wall(contract.wall.x, W, contract.wall.height, contract.wall.thickness)
              if contract.wall else None)
bolts = []
for i, h in enumerate(contract.holes, 1):
    b = g.place(g.hex_bolt_solid(f, 20), h.x, h.y)
    bolts.append(b)
    if wall_solid is not None:
        findings.append(v.h1_interference(b, wall_solid, f"홀{i}↔벽"))
    ed = min(L / 2 - h.x, L / 2 + h.x, W / 2 - h.y, W / 2 + h.y)
    findings.append(v.h4_edge_distance(ed, f))
for i in range(len(bolts)):
    for j in range(i + 1, len(bolts)):
        findings.append(v.h1_interference(bolts[i], bolts[j], f"홀{i+1}↔홀{j+1}"))

res = v.summarize(findings)
for fd in findings:
    print("    " + str(fd))
print(f"\n    판정: {'통과 ✅' if res['passed'] else 'HARD 실패 ❌ ' + str(res['hard_fail'])}")

out = Path(__file__).resolve().parents[1] / "out"
out.mkdir(exist_ok=True)
if res["passed"]:
    sp = ex.to_step(part, out / "meta_part.step")
    st = ex.to_stl(part, out / "meta_part.stl")
    print(f"\n[4] 내보냄: {sp.name} ({sp.stat().st_size}B), {st.name} ({st.stat().st_size}B)")
else:
    print("\n[4] 검증 실패 → 판정자(메타)에게 파라미터 수정 요청 단계로 (다음 구현)")
