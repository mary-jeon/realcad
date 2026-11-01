"""Feature-style sketch -> extrude (boss) / cut.

Turns a closed shape (rectangle, circle, closed polyline) drawn on a chosen plane (front, top, right, or a flat
face of the part) into a few lines of build123d code appended to the current part code. Because it stays as
code, edit, undo and save work as usual.

- A loop inside a loop is a hole (even depth = solid, odd depth = hole); merging the result is always on
- End conditions: blind (given depth), mid (symmetric), through (cut only)
- Cuts go into the face (against the normal) by default, bosses outward (along the normal); reverse flips it
"""
from __future__ import annotations

import math
import re

MAX_LOOPS = 60
MAX_PTS = 400


def _f(x) -> float:
    v = float(x)
    if not math.isfinite(v):
        raise ValueError("숫자가 아니에요")
    return round(v, 4)


def _v3(v) -> tuple:
    return tuple(_f(c) for c in v[:3])


def _norm(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(round(c / n, 6) for c in v)


def loops_code(loops: list[dict]) -> list[str]:
    """Screen loops -> list of build123d 2D shape expressions in the plane's coordinate system."""
    out = []
    for lp in loops[:MAX_LOOPS]:
        t = lp.get("type")
        if t == "rect":
            w, h = abs(_f(lp["w"])), abs(_f(lp["h"]))
            if w < 0.05 or h < 0.05:
                continue
            out.append(f"Pos({_f(lp['cx'])}, {_f(lp['cy'])}) * Rectangle({w}, {h})")
        elif t == "circle":
            r = abs(_f(lp["r"]))
            if r < 0.025:
                continue
            out.append(f"Pos({_f(lp['cx'])}, {_f(lp['cy'])}) * Circle({r})")
        elif t == "slot":
            x1, y1, x2, y2, w = (_f(lp[k]) for k in ("x1", "y1", "x2", "y2", "w"))
            w = abs(w)
            if w < 0.05:
                continue
            L = math.hypot(x2 - x1, y2 - y1)
            cx, cy = round((x1 + x2) / 2, 4), round((y1 + y2) / 2, 4)
            if L < 1e-3:
                out.append(f"Pos({cx}, {cy}) * Circle({w / 2:g})")
            else:
                ang = round(math.degrees(math.atan2(y2 - y1, x2 - x1)), 4)
                out.append(f"Pos({cx}, {cy}) * Rot(0, 0, {ang}) * SlotCenterToCenter({round(L, 4)}, {w:g})")
        elif t == "path":                      # closed loop mixing lines and arcs (an arc is 3 points: start, through, end)
            parts = []
            for sg in (lp.get("segs") or [])[:MAX_PTS]:
                a = (_f(sg["a"][0]), _f(sg["a"][1])); b = (_f(sg["b"][0]), _f(sg["b"][1]))
                if sg.get("t") == "arc":
                    m = (_f(sg["m"][0]), _f(sg["m"][1]))
                    parts.append(f"Edge.make_three_point_arc(Vector{a}, Vector{m}, Vector{b})")
                elif math.dist(a, b) > 1e-6:
                    parts.append(f"Edge.make_line(Vector{a}, Vector{b})")
            if len(parts) >= 2:
                out.append("Face(Wire([" + ", ".join(parts) + "]))")
        elif t == "poly":
            pts = [(_f(p[0]), _f(p[1])) for p in (lp.get("pts") or [])[:MAX_PTS]]
            if len(pts) >= 2 and math.dist(pts[0], pts[-1]) < 1e-6:
                pts = pts[:-1]
            if len(pts) < 3:
                continue
            out.append("Polygon(" + ", ".join(f"({x}, {y})" for x, y in pts) + ", align=None)")
    return out


def block(plane: dict, loops: list[dict], op: str, depth: float, end: str, reverse: bool,
          var: str, first: bool) -> str:
    shapes = loops_code(loops)
    if not shapes:
        raise ValueError("닫힌 모양이 없어요. 사각형, 원, 또는 시작점으로 돌아와 닫은 선을 그려 주세요.")
    o, x, n = _v3(plane["origin"]), _norm(_v3(plane["x_dir"])), _norm(_v3(plane["normal"]))
    if abs(sum(a * b for a, b in zip(x, n))) > 1e-3:
        raise ValueError("스케치 평면의 방향이 이상해요(가로축과 법선이 직각이 아님)")
    op = "cut" if op == "cut" else "boss"
    end = end if end in ("blind", "mid", "through") else "blind"
    if end == "through" and op != "cut":
        end = "blind"
    d = max(0.05, min(abs(_f(depth or 0)), 5000.0))
    word = {"boss": "돌출", "cut": "잘라내기"}[op]
    endw = {"blind": f"{d:g} mm", "mid": f"양쪽 대칭 {d:g} mm", "through": "전체 관통"}[end]
    L = []
    L.append(f"# ---- 스케치 + {word} (RealCAD sketch, {endw}{', 반대 방향' if reverse else ''}) ----")
    L.append(f"_skp = Plane(origin={o}, x_dir={x}, z_dir={n})")
    L.append("_skf = [" + ", ".join(f"_skp * ({sh})" for sh in shapes) + "]")
    L.append("_skprof = None")
    L.append("for _i in sorted(range(len(_skf)), key=lambda i: -_skf[i].area):   # 큰 것부터, 안에 든 고리는 구멍")
    L.append("    _fa = _skf[_i]")
    L.append("    _dep = sum(1 for _j in range(len(_skf)) if _j != _i and _skf[_j].area > _fa.area and _skf[_j].is_inside(_fa.center()))")
    L.append("    if _skprof is None:")
    L.append("        _skprof = _fa")
    L.append("    elif _dep % 2 == 0:")
    L.append("        _skprof = _skprof + _fa")
    L.append("    else:")
    L.append("        _skprof = _skprof - _fa")
    sign = -1 if reverse else 1
    if op == "cut":
        sign = -sign                          # cut default = into the face
    if end == "mid":
        L.append(f"_skt = extrude(_skprof, amount={d / 2:g}, both=True)")
    elif end == "through":
        L.append(f"_skL = max({var}.bounding_box().diagonal * 2, 10)")
        L.append("_skt = extrude(_skprof, amount=_skL, both=True)")
    else:
        L.append(f"_skt = extrude(_skprof, amount={d:g}, dir=_skp.z_dir * {sign})")
    if first:
        L.append(f"{var} = _skt")
    elif op == "cut":
        L.append(f"{var} = {var} - _skt")
    else:
        L.append(f"{var} = {var} + _skt")
    return "\n".join(L)


def apply(code: str | None, req: dict, base_step_name: str | None = None) -> str:
    """New code with the sketch feature added to the current code (or a new part, or the starting shape BASE if none)."""
    from . import faceops
    if not code:
        if base_step_name:
            head = f"from build123d import *\n# RealCAD-BASE: {base_step_name}\npart = BASE\n"
            return head + block(req["plane"], req["loops"], req.get("op"), req.get("depth"), req.get("end"),
                                bool(req.get("reverse")), "part", first=False) + "\n"
        if req.get("op") == "cut":
            raise ValueError("잘라낼 부품이 아직 없어요. 먼저 돌출로 만들어 주세요.")
        return "from build123d import *\n" + block(req["plane"], req["loops"], "boss", req.get("depth"), req.get("end"),
                                                    bool(req.get("reverse")), "part", first=True) + "\n"
    tr = faceops._trailing_round(code)
    if tr:                                      # insert before a trailing fillet/chamfer so the new edges are rounded too
        k, var = tr
        src = code.splitlines()
        blk = block(req["plane"], req["loops"], req.get("op"), req.get("depth"), req.get("end"),
                    bool(req.get("reverse")), var, first=False)
        return "\n".join(src[:k] + [blk] + src[k:]) + "\n"
    var = "part" if re.search(r"^\s*part\s*=", code, re.M) else "result"
    return code.rstrip() + "\n\n" + block(req["plane"], req["loops"], req.get("op"), req.get("depth"), req.get("end"),
                                          bool(req.get("reverse")), var, first=False) + "\n"
