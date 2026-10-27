"""판정 루프 데모: 일부러 불량 설계를 넣고 메타가 고쳐 통과시키는지 본다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from realcad.contract.schema import DesignContract, Plate, Wall, Hole
from realcad.agent.loop import run
from realcad.export import exporters as ex

# 불량: 볼트를 벽(x 27~33)에 겹치고 모서리(x=±40)에 붙임
bad = DesignContract(plate=Plate(80, 50, 6), wall=Wall(30, 25, 6),
                     fastener="1/4-20", fit="normal",
                     holes=[Hole(34, 0), Hole(36, 10)])

print("시작(불량 설계): 볼트를 벽·모서리에 붙임\n")
r = run(bad, max_iters=3)

print("\n최종 검증:")
for fd in r["findings"]:
    print("  " + str(fd))
print(f"\n결과: {'통과 ✅' if r['summary']['passed'] else '실패 ❌'}"
      f" | 반복 {r['iters']}회 | 메타가 고침={r['fixed']}")
c = r["contract"]
print(f"최종 구멍 {[(round(h.x,1), round(h.y,1)) for h in c.holes]}, 벽 x={c.wall.x if c.wall else None}")

if r["summary"]["passed"]:
    out = Path(__file__).resolve().parents[1] / "out"
    ex.to_step(r["part"], out / "loop_fixed.step")
    ex.to_stl(r["part"], out / "loop_fixed.stl")
    print("내보냄: loop_fixed.step / loop_fixed.stl")
