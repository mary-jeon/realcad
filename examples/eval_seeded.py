"""심은 오류 검출율 — 정답 계약에 일부러 결함을 심고 커널 검증이 잡아내는지 센다. (Meta API 불필요, 수 초)

실행: PYTHONPATH=src .venv/bin/python examples/eval_seeded.py
출력: 검출 매트릭스(결함 종류 × 정답 계약) + 총 검출율 + 오탐(정답이 실패로 판정)율. out/eval/seeded_<ts>.json 저장.
"""
from __future__ import annotations
import copy, json, time, sys
from pathlib import Path
from realcad.contract.schema import DesignContract as D
from realcad.pipeline import build_and_verify

ROOT = Path(__file__).resolve().parents[1]

# 정답 계약 10개 — 전부 통과해야 하는 설계
GOLD = {
    "bracket_1/4": {"kind": "plate", "plate": {"length": 80, "width": 40, "thickness": 5}, "fastener": "1/4-20", "fit": "normal",
                    "holes": [{"x": -25, "y": 0}, {"x": 25, "y": 0}]},
    "bracket_wall": {"kind": "plate", "plate": {"length": 80, "width": 50, "thickness": 6}, "fastener": "1/4-20", "fit": "normal",
                     "wall": {"x": 36, "height": 25, "thickness": 5}, "holes": [{"x": -25, "y": 0}, {"x": 5, "y": 0}]},
    "plate_m6_4h": {"kind": "plate", "plate": {"length": 100, "width": 100, "thickness": 6}, "fastener": "M6", "fit": "normal",
                    "holes": [{"x": -35, "y": -35}, {"x": 35, "y": -35}, {"x": -35, "y": 35}, {"x": 35, "y": 35}]},
    "plate_#8_3h": {"kind": "plate", "plate": {"length": 90, "width": 30, "thickness": 4}, "fastener": "#8-32", "fit": "close",
                    "holes": [{"x": -30, "y": 0}, {"x": 0, "y": 0}, {"x": 30, "y": 0}]},
    "tapped_m4_pla": {"kind": "plate", "plate": {"length": 60, "width": 40, "thickness": 10}, "fastener": "M4", "hole_type": "tapped",
                      "material": "pla", "holes": [{"x": -18, "y": 0}, {"x": 18, "y": 0}]},
    "tapped_3/8_alu": {"kind": "plate", "plate": {"length": 100, "width": 60, "thickness": 16}, "fastener": "3/8-16", "hole_type": "tapped",
                       "material": "aluminum", "holes": [{"x": -30, "y": 0}, {"x": 30, "y": 0}]},
    "plate_m3_loose": {"kind": "plate", "plate": {"length": 50, "width": 30, "thickness": 3}, "fastener": "M3", "fit": "loose",
                       "holes": [{"x": -18, "y": 0}, {"x": 18, "y": 0}]},
    "plate_1/2": {"kind": "plate", "plate": {"length": 160, "width": 80, "thickness": 12}, "fastener": "1/2-13", "fit": "normal",
                  "holes": [{"x": -50, "y": 0}, {"x": 50, "y": 0}]},
    "plate_unf": {"kind": "plate", "plate": {"length": 80, "width": 40, "thickness": 5}, "fastener": "1/4-28", "fit": "normal",
                  "holes": [{"x": -25, "y": 0}, {"x": 25, "y": 0}]},
    "plate_m8_2h": {"kind": "plate", "plate": {"length": 120, "width": 50, "thickness": 8}, "fastener": "M8", "fit": "normal",
                    "holes": [{"x": -40, "y": 0}, {"x": 40, "y": 0}]},
    "cbore_m5": {"kind": "plate", "plate": {"length": 100, "width": 50, "thickness": 10}, "fastener": "M5", "fit": "normal",
                 "hole_style": "counterbore", "holes": [{"x": -35, "y": 0}, {"x": 35, "y": 0}]},
    "insert_m3": {"kind": "plate", "plate": {"length": 60, "width": 40, "thickness": 9}, "fastener": "M3", "hole_type": "insert",
                  "holes": [{"x": -20, "y": 0}, {"x": 20, "y": 0}]},
}


def _nominal(spec):
    from realcad.fasteners.standards import resolve
    return resolve(spec)[0].nominal_dia_mm


# 결함 변형 — (이름, 적용 함수, 기대 검출 코드)
def m_small_hole(c):      # 구멍을 규격보다 작게 (LLM이 '대충' 뚫은 경우)
    if c.get("hole_type") in ("tapped", "insert"): return None
    c["hole_dia"] = round(_nominal(c["fastener"]) * 0.98, 2); return "H2"

def m_edge(c):            # 첫 구멍을 모서리 쪽으로 밀어 연단거리 침범
    L = c["plate"]["length"]; c["holes"][0]["x"] = -(L / 2 - 0.9 * _nominal(c["fastener"])); return "H4"

def m_wall_hit(c):        # 벽을 첫 구멍 옆에 세우되 머리 맞모 반경 안으로 1mm 파고들게 → 머리 간섭
    from realcad.fasteners.standards import resolve
    ac = resolve(c["fastener"])[0].head_across_corners_mm
    c["wall"] = {"x": c["holes"][0]["x"] + ac / 2 + 2.0 - 1.0, "height": 20, "thickness": 4}; return "H1"

def m_bolts_touch(c):     # 두 구멍을 머리가 겹치게 붙임
    d = _nominal(c["fastener"]); c["holes"] = [{"x": -0.6 * d, "y": 0}, {"x": 0.6 * d, "y": 0}]; return "H1"

def m_unknown_fastener(c):  # 보유하지 않은 규격
    c["fastener"] = "M20" if c["fastener"].startswith("M") else "#12-24"; return "F0"

def m_thin_tapped(c):     # 탭 구멍인데 판이 체결깊이보다 얇음
    c["hole_type"] = "tapped"; c["material"] = "pla"; c["plate"]["thickness"] = round(0.9 * _nominal(c["fastener"]), 2); return "H3"

def m_thin_insert(c):     # 인서트 구멍인데 판이 인서트 길이보다 얇음
    c["hole_type"] = "insert"; c.pop("hole_style", None)
    c["plate"]["thickness"] = 4.0; return "I1"

def m_tool_access(c):     # 벽을 머리는 안 닿지만 소켓이 안 들어가는 거리에
    from realcad.fasteners.standards import resolve
    f = resolve(c["fastener"])[0]; od = f.socket_od_mm or f.head_across_corners_mm + 3
    c["wall"] = {"x": c["holes"][0]["x"] + f.head_across_corners_mm / 2 + 2.0 + 0.3, "height": 25, "thickness": 4}
    return "H5"

MUTATIONS = [("thin-insert(I1)", m_thin_insert), ("tool-access(H5)", m_tool_access), ("hole<D(H2)", m_small_hole), ("edge(H4)", m_edge), ("wall-hit(H1)", m_wall_hit),
             ("bolts-touch(H1)", m_bolts_touch), ("unknown-fastener(F0)", m_unknown_fastener), ("thin-tapped(H3)", m_thin_tapped)]


def main():
    t0 = time.time(); res = {"gold": {}, "matrix": {}, "false_pass": [], "false_fail": []}
    for name, g in GOLD.items():
        _, _, _, _, summ = build_and_verify(D.from_dict(copy.deepcopy(g)))
        res["gold"][name] = summ["passed"]
        if not summ["passed"]:
            res["false_fail"].append((name, summ["hard_fail"]))
    total = hit = 0
    for mname, fn in MUTATIONS:
        row = {}
        for gname, g in GOLD.items():
            c = copy.deepcopy(g); expect = fn(c)
            if expect is None:
                row[gname] = "-"; continue
            try:
                _, _, _, findings, summ = build_and_verify(D.from_dict(c))
                caught = expect in summ["hard_fail"]
            except Exception as e:
                caught = False; summ = {"hard_fail": [f"EXC {type(e).__name__}"]}
            total += 1; hit += caught
            row[gname] = "✅" if caught else f"❌({','.join(summ['hard_fail']) or 'pass'})"
            if not caught:
                res["false_pass"].append((mname, gname, summ["hard_fail"]))
        res["matrix"][mname] = row
    res["detection_rate"] = round(100 * hit / total, 1) if total else None
    res["n"] = total; res["sec"] = round(time.time() - t0, 1)
    # 출력
    names = list(GOLD)
    print("정답 계약 통과:", sum(res["gold"].values()), "/", len(GOLD), ("오탐 " + str(res["false_fail"]) if res["false_fail"] else ""))
    print("\n결함 \\ 정답계약 | " + " | ".join(n[:10] for n in names))
    for m, row in res["matrix"].items():
        print(f"{m:22s}| " + " | ".join(f"{row[n]:10s}" for n in names))
    print(f"\n검출율 {hit}/{total} = {res['detection_rate']}%  ({res['sec']}s)")
    if res["false_pass"]:
        print("미검출:", res["false_pass"])
    out = ROOT / "out" / "eval"; out.mkdir(parents=True, exist_ok=True)
    p = out / f"seeded_{time.strftime('%Y%m%d_%H%M%S')}.json"; p.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print("saved:", p)


if __name__ == "__main__":
    main()
