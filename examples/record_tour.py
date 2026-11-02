"""Film the viewer's tour frame by frame (60 fps by default) and join the frames into an mp4.

The tour in web/acad.html is a pure function of time (RCTour.at(t)): the camera goes round, the mechanism runs on
its one input value with the measured numbers beside it, and the parts open and close. Here each frame is set
exactly and screenshotted, so the film is smooth even on a slow machine.

    PYTHONPATH=src .venv/bin/python examples/record_tour.py --preset eccentric_slider --out tour.mp4
    PYTHONPATH=src .venv/bin/python examples/record_tour.py --result web/gen/xxxx.json --fps 30

--preset builds one of the assembly presets here (no model call) and needs the RealCAD server serving this repo's
web folder (default http://127.0.0.1:8750). --result takes a saved response JSON under web/gen.
Needs: pip install playwright && python -m playwright install chromium-headless-shell, and ffmpeg.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_preset(name: str) -> str:
    """Build an assembly preset like the web app does and save its response under web/gen -> gen/<file>.json."""
    from realcad.web import app as A
    from realcad.contract.schema import DesignContract as D
    d = A._respond(A.run(D.from_dict({"kind": "assembly", "assembly": {"preset": name}}), max_iters=0))
    if d.get("error"):
        sys.exit(f"preset failed: {d['error']}")
    out = A.GEN / f"tour_{name}.json"
    out.write_text(json.dumps(d, ensure_ascii=False, default=str), encoding="utf-8")
    return f"gen/{out.name}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--preset", help="eccentric_slider, cam_clamp, vise, gear_pump, drill_jig")
    src.add_argument("--result", help="a saved response JSON under web/gen (path or gen/name.json)")
    ap.add_argument("--url", default="http://127.0.0.1:8750", help="RealCAD server serving this repo's web folder")
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--seconds", type=float, default=None, help="default: the whole tour (20 s)")
    ap.add_argument("--size", default="1280x800")
    ap.add_argument("--clean", action="store_true", help="hide the side panels, keep the model and the motion bar")
    ap.add_argument("--out", default="tour.mp4")
    a = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is needed to join the frames (brew install ffmpeg)")
    from playwright.sync_api import sync_playwright

    rel = build_preset(a.preset) if a.preset else ("gen/" + Path(a.result).name)
    w, h = (int(x) for x in a.size.lower().split("x"))
    out = Path(a.out).resolve()
    with tempfile.TemporaryDirectory() as td, sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": w, "height": h})
        page.goto(f"{a.url}/acad.html?tour=off", wait_until="load")      # the live idle tour must not run while filming
        page.evaluate("() => { try { sessionStorage.clear(); } catch (e) {} }")
        page.evaluate("""async (rel) => {
            const d = await (await fetch(rel + '?' + Date.now())).json();
            if (d.measured) renderMateResult(d, logline('sys', '')); else renderResult(d, logline('sys', ''));
        }""", rel)
        page.wait_for_function("() => { const b = document.getElementById('motionBar'); return b && b.style.display === 'flex'; }",
                               timeout=120_000)
        if a.clean:
            page.evaluate("() => { for (const id of ['side', 'results', 'objtools']) { const e = document.getElementById(id); if (e) e.style.display = 'none'; } window.dispatchEvent(new Event('resize')); }")
        page.wait_for_timeout(1500)
        page.evaluate("() => { RCTour.idle(false); RCTour.reset(); }")
        total = a.seconds or page.evaluate("() => RCTour.duration")
        n = int(round(total * a.fps))
        for k in range(n):
            page.evaluate("""(t) => new Promise(res => { RCTour.at(t); requestAnimationFrame(() => requestAnimationFrame(res)); })""",
                          k / a.fps)
            page.screenshot(path=f"{td}/{k:05d}.png")
            if k % a.fps == 0:
                print(f"  {k // a.fps:>3d} s / {total:g} s", flush=True)
        browser.close()
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(a.fps), "-i", f"{td}/%05d.png",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(out)], check=True)
    print(f"wrote {out} ({n} frames, {a.fps} fps)")


if __name__ == "__main__":
    main()
