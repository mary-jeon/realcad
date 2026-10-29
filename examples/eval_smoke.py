"""실전 평가 — 프롬프트 묶음을 실제 Meta 파이프라인에 넣어 통과율·반복횟수·시간·토큰을 기록한다.

실행: PYTHONPATH=src .venv/bin/python examples/eval_smoke.py [--set basic|wide]
결과: out/eval/eval_<timestamp>.jsonl + 요약 표 stdout. (Meta API 크레딧 사용)
"""
from __future__ import annotations
import json, sys, time, traceback
from pathlib import Path
from realcad.agent import codegen, sandbox
from realcad.agent.planner import plan
from realcad.agent.loop import run as loop_run

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "eval"; OUT.mkdir(parents=True, exist_ok=True)

BASIC = [
    ("code", "a coffee mug with a handle, 350 ml"),
    ("code", "휴대폰 거치대, 폰 두께 9mm, 각도 60도"),
    ("code", "M3 볼트 4개로 벽에 거는 라즈베리파이 4 케이스 (포트 구멍 포함)"),
    ("code", "a spur gear, 24 teeth, module 2, 8 mm bore, 10 mm thick"),
    ("code", "에어팟 프로 케이스 홀더, 책상 모서리에 끼우는 클립형 (책상 두께 25mm)"),
    ("code", "a wall-mount bracket with two 1/4-20 bolt holes, 80x40x5 mm, with a 30 mm lip"),
    ("code", "펜 6자루 꽂는 육각 연필통"),
    ("code", "건담 피규어 180mm"),
    ("param", "a wall-mount bracket with two 1/4-20 bolt holes"),
    ("param", "pencil holder, 80mm diameter, 100mm tall, 3 compartments"),
    ("param", "case for raspberry pi 5"),
    ("param", "24 tooth spur gear module 1.5 bore 6"),
]
WIDE = BASIC + [
    ("code", "USB-C 케이블 정리 클립 5구"),
    ("code", "a hex nut M8 and a matching bolt, separate pieces"),
    ("code", "도어 스토퍼 쐐기, 고무패드 홈 포함"),
    ("code", "a 100x100 VESA monitor arm adapter plate, M4 holes"),
    ("code", "a chibi cat figure"),
    ("code", "벽걸이 열쇠 걸이, 고리 4개, 나사 2개"),
    ("code", "a snap-fit box with lid, 60x40x30 inner"),
    ("code", "a watering can 1.5L"),
]

def main():
    which = "wide" if "--set" in sys.argv and sys.argv[sys.argv.index("--set")+1] == "wide" else "basic"
    cases = WIDE if which == "wide" else BASIC
    ts = time.strftime("%Y%m%d_%H%M%S")
    log = OUT / f"eval_{ts}.jsonl"
    rows = []
    for i, (mode, prompt) in enumerate(cases):
        t0 = time.time(); rec = {"i": i, "mode": mode, "prompt": prompt}
        try:
            if mode == "code":
                r = codegen.design_code(prompt, OUT / f"{ts}_{i}.stl", OUT / f"{ts}_{i}.step", max_iters=3)
                rec.update(ok=r["ok"], iters=r.get("iters"), fixed=r.get("fixed"),
                           error=(r.get("error") or "")[:200], info=r.get("info"),
                           code_lines=len((r.get("code") or "").splitlines()),
                           banned_hit=("금지된" in (r.get("error") or "")))
            else:
                c, usage, raw = plan(prompt)
                rec.update(kind=c.kind, usage=usage)
                if c.kind == "retrieve":
                    rec.update(ok=False, error="planner→retrieve")
                else:
                    lr = loop_run(c, max_iters=3, verbose=False)
                    rec.update(ok=lr["summary"]["passed"], iters=lr["iters"], fixed=lr["fixed"],
                               hard_fail=lr["summary"].get("hard_fail"))
        except Exception as e:
            rec.update(ok=False, error=f"EXC {type(e).__name__}: {e}"[:300])
        rec["sec"] = round(time.time() - t0, 1)
        rows.append(rec); log.open("a").write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"[{i:02d}] {mode:5s} {'PASS' if rec.get('ok') else 'FAIL':4s} {rec['sec']:6.1f}s it={rec.get('iters')} {prompt[:40]} {('— '+rec.get('error','')[:80]) if not rec.get('ok') else ''}", flush=True)
    n = len(rows); p = sum(1 for r in rows if r.get("ok"))
    print(f"\n== {which}: {p}/{n} 통과 ({100*p/n:.0f}%), 평균 {sum(r['sec'] for r in rows)/n:.0f}s, "
          f"첫 시도 통과 {sum(1 for r in rows if r.get('ok') and not r.get('fixed'))}, 자동수정 후 통과 {sum(1 for r in rows if r.get('ok') and r.get('fixed'))}")
    print("log:", log)
    update_readme(rows, which)


def update_readme(rows, which):
    """README 의 EVAL_TABLE 마커 사이에 최신 결과 표를 써 넣는다."""
    rd = ROOT / "README.md"
    if not rd.exists():
        return
    n = len(rows); p = sum(1 for r in rows if r.get("ok"))
    first = sum(1 for r in rows if r.get("ok") and not r.get("fixed"))
    lines = [f"Set `{which}` · {time.strftime('%Y-%m-%d')} · **{p}/{n} passed** ({first} on the first attempt, "
             f"{p - first} after auto-repair) · mean {sum(r['sec'] for r in rows) / n:.0f} s per design", "",
             "| # | path | result | tries | s | prompt |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['i']} | {r['mode']} | {'✅' if r.get('ok') else '❌'} | {1 + (r.get('iters') or 0)} | {r['sec']:.0f} | {r['prompt']} |")
    txt = rd.read_text(encoding="utf-8")
    a, b = txt.find("<!-- EVAL_TABLE_START -->"), txt.find("<!-- EVAL_TABLE_END -->")
    if a >= 0 and b > a:
        txt = txt[:a + len("<!-- EVAL_TABLE_START -->")] + "\n" + "\n".join(lines) + "\n" + txt[b:]
        rd.write_text(txt, encoding="utf-8")
        print("README eval table updated")


if __name__ == "__main__":
    main()
