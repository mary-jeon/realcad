"""Face push/pull: find the face the user picked on screen in the actual B-rep and extrude or cut exactly that face.

Why separate: previously the picked face was turned into numbers ("normal (0,0,1), center (..)") and the LLM
rewrote the whole code. Results depended on which line the model guessed, so unrelated places changed
and holes disappeared. Here the model (or rules) decides only "how much"; the kernel decides "which face".

Flow: analyze(current STEP, picked faces) -> per face, measure plane position and top height of adjacent walls
      -> plan(instruction) -> {op: push|cut, distance} (rules first, Meta model if ambiguous)
      -> append_code(current code) appends a few build123d lines and runs them in the sandbox (edit and undo still work)
"""
from __future__ import annotations

import json
import re

_TOL = 0.05


def _vec(v):
    from build123d import Vector
    return Vector(float(v[0]), float(v[1]), float(v[2]))


def _match(shape, point, normal):
    """Find the B-rep plane from the clicked point (a real point on the face) and normal."""
    from build123d import GeomType
    p, n = _vec(point), _vec(normal).normalized()
    best = None
    for f in shape.faces():
        if f.geom_type != GeomType.PLANE:
            continue
        if f.normal_at().dot(n) < 0.98:
            continue
        d = f.distance_to(p)
        if best is None or d < best[0]:
            best = (d, f)
    if best is None or best[0] > 1.0:          # more than 1 mm away means the wrong face
        return None
    return best[1]


def _levels_beside(shape, face, n):
    """How far walls adjacent to face (normal perpendicular to face's) rise above it, as a coordinate along the normal."""
    d0 = n.dot(face.center())
    out = []
    for g in shape.faces():
        if g.is_same(face) if hasattr(g, "is_same") else g == face:
            continue
        try:
            gn = g.normal_at()
        except Exception:
            gn = None
        if gn is not None and abs(gn.dot(n)) > 0.15:        # same-direction face, not a wall
            continue
        try:
            if g.distance_to(face) > _TOL:
                continue
        except Exception:
            continue
        top = max(n.dot(v.center() if hasattr(v, "center") else v) for v in g.vertices()) if g.vertices() else d0
        if top > d0 + 0.1:
            out.append(top)
    # If the wall's top edge is filleted or chamfered, the wall face ends below it; use the height of the same-direction plane (wall top face).
    from build123d import GeomType
    caps = sorted({round(n.dot(h.center()), 3) for h in shape.faces()
                   if h.geom_type == GeomType.PLANE and h.normal_at().dot(n) > 0.98})
    snapped = []
    for w in out:
        up = [c for c in caps if w - 1e-3 <= c <= w + 3.0]
        snapped.append(round(min(up) if up else w, 3))
    return sorted(set(snapped))


def _levels_near(shape, face, n, radius: float = 20.0):
    """Heights of same-direction planes near face (within radius mm of its edge) that are higher than face, nearest first."""
    from build123d import GeomType
    d0 = n.dot(face.center())
    out = []
    for h in shape.faces():
        if h.geom_type != GeomType.PLANE or h.normal_at().dot(n) < 0.98:
            continue
        lv = n.dot(h.center())
        if lv <= d0 + 0.1:
            continue
        try:
            gap = h.distance_to(face)
        except Exception:
            continue
        if gap - (lv - d0) <= radius:          # lateral distance excluding the height difference
            out.append((gap, round(lv, 3)))
    out.sort()
    return [lv for _g, lv in out[:3]]


def analyze(step_path: str, faces: list[dict]) -> list[dict]:
    """faces: [{point:[x,y,z], normal:[x,y,z]}] -> per face {ok, level, area, beside:[...], normal}."""
    from build123d import import_step
    shape = import_step(str(step_path))
    res = []
    for fd in faces:
        pt, nm = fd.get("point") or fd.get("center"), fd.get("normal")
        if not pt or not nm:
            res.append({"ok": False, "why": "점, 법선 없음"})
            continue
        f = _match(shape, pt, nm)
        if f is None:
            res.append({"ok": False, "why": "평면이 아니거나 형상에서 못 찾음"})
            continue
        n = f.normal_at()
        try:                                   # outer outline of the originally picked face (so only this region moves even if the face grows later)
            w = f.outer_wire()
            outline = [[round(q.X, 3), round(q.Y, 3), round(q.Z, 3)] for q in (w.position_at(i / 96) for i in range(96))]
        except Exception:
            outline = None
        res.append({"ok": True, "outline": outline, "point": [round(float(x), 4) for x in pt],
                    "normal": [round(n.X, 6), round(n.Y, 6), round(n.Z, 6)],
                    "level": round(n.dot(f.center()), 3), "area": round(f.area, 1),
                    "beside": _levels_beside(shape, f, n), "near": _levels_near(shape, f, n)})
    return res


# ─────────────── instruction -> how much ───────────────
_NUM = r"(\d+(?:\.\d+)?)\s*(?:mm|밀리|미리)?"
_UP = r"(올려|올리|높여|높이|키워|두껍게|두께|돌출|뽑아|늘려|위로|채워|메워|push|raise|extrude|up)"
_DOWN = r"(내려|낮춰|낮게|파|깎|얇게|파내|아래로|cut|lower|down|recess|pocket)"
_BESIDE = r"(옆|주변|인접|둘레|테두리|양옆|벽|턱|림|rim|wall|neighbo|adjacent)"


def plan(instruction: str, info: list[dict]) -> dict:
    """{op:'push'|'cut'|'none', distance:mm, how:str}. If rules cannot decide, ask the Meta model for JSON."""
    t = instruction.strip()
    ok = [i for i in info if i.get("ok")]
    if not ok:
        return {"op": "none", "how": "잡은 면을 형상에서 못 찾음"}
    # In-plane size changes (width, length, halving, etc.) are not push/pull, which moves along the height direction.
    # They must edit design variables so attached ledges and walls follow, so they go to the regular (model) edit.
    if re.search(r"(가로|세로|폭|너비|길이|넓이|면적|크기|사이즈|반으로|절반|반\s*(만|으로|줄|크기|길이)|\d+\s*배|width|length|size|half)", t, re.I) \
            and not re.search(r"(높이|두께|깊이|올려|내려|파\s*줘|파내|돌출|height|thick|depth|raise|lower)", t, re.I):
        return {"op": "none", "how": "면 크기(가로, 세로) 변경은 설계 변수 수정으로"}
    # Holes, fillets, text and the like are not push/pull. Even with a number and "cut" in the text, let the model decide, not the rules.
    if re.search(r"(구멍|홀|hole|필렛|fillet|라운드|둥글|모따기|chamfer|글자|텍스트|text|로고|나사|탭|볼트|bolt)", t, re.I):
        return _plan_llm(t, ok)
    down = re.search(_DOWN, t, re.I) is not None
    up = re.search(_UP, t, re.I) is not None
    m = re.search(_NUM, t)
    # 1) "up to the adjacent wall height" -> flush with the wall top
    if re.search(_BESIDE, t, re.I) and re.search(r"(까지|맞춰|같게|만큼|높이|flush|level|to)", t, re.I) and not m:
        tops = [max(i["beside"]) for i in ok if i["beside"]]
        if tops:
            target = max(tops)
            return {"op": "push", "to_level": target, "how": f"옆 벽 꼭대기({target:g})에 맞춤"}
        near = [min(i["near"]) for i in ok if i.get("near")]
        if near:                                   # no attached wall (e.g. a ledge inside a hole): match the nearest higher face around it
            target = max(near)
            return {"op": "push", "to_level": target, "how": f"주변 면 높이({target:g})에 맞춤"}
        return {"op": "noop", "how": "잡은 면 옆에 더 높은 벽이 없어요. 이미 옆 벽과 같거나 더 높아요"}
    # 2) "up to height 20 / to 20" -> that height (coordinate along the face normal)
    ml = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm|밀리|미리)?\s*(까지|으로|로)(?=\s|$|[^가-힣])", t + " ")
    if ml and (up or down or re.search(r"(높이|위치|level|height)", t, re.I)):
        lv = float(ml.group(1))
        return {"op": "push", "to_level": lv, "how": f"높이 {lv:g} 에 맞춤"}
    # 3) "raise 3mm / cut 2mm" -> that distance
    if m and (up or down):
        d = float(m.group(1))
        if 0 < d <= 500:
            return {"op": "cut" if down and not up else "push", "distance": d,
                    "how": f"{d:g} mm {'파냄' if down and not up else '올림'}"}
    # 4) ambiguous: ask the model
    return _plan_llm(t, ok)


def _plan_llm(t: str, ok: list[dict]) -> dict:
    from .meta_client import chat
    faces = [{"face": k + 1, "plane_level_mm": i["level"], "normal": i["normal"], "area_mm2": i["area"],
              "adjacent_wall_tops_mm": i["beside"]} for k, i in enumerate(ok)]
    msg = ("A user selected planar faces of a CAD part and said (Korean or English):\n"
           f"\"{t}\"\n\nSelected faces (levels are measured along each face normal):\n{json.dumps(faces)}\n\n"
           "Decide a push/pull on exactly these faces. Reply JSON only:\n"
           '{"op":"push"|"cut"|"none"|"ask","distance":<mm, positive>,"to_level":<mm or null>,"how":"<short Korean reason>","question":"<Korean question if op is ask>"}\n'
           "If the request could mean clearly different things (which direction, how much, which faces), do NOT guess: "
           "use op ask with one short Korean question that offers the concrete options with their mm values. "
           "push = grow the faces outward along their normal (raise, thicken, fill up to a wall). "
           "cut = sink them inward (lower, recess). Use to_level when the user wants them flush with something "
           "listed in adjacent_wall_tops_mm. Use op none if the request is not a push/pull of these faces "
           "(for example adding holes, fillets, text).")
    try:
        content, _u = chat([{"role": "user", "content": msg}], json_mode=True, temperature=0.0, max_tokens=3000)
        d = json.loads(re.search(r"\{.*\}", content, re.S).group(0))
    except Exception as e:
        return {"op": "none", "how": f"해석 실패: {type(e).__name__}"}
    op = d.get("op")
    if op == "ask" and d.get("question"):
        return {"op": "ask", "question": str(d["question"])[:300], "how": "되묻기"}
    if op not in ("push", "cut"):
        return {"op": "none", "how": d.get("how") or "밀고 당기기 요청이 아님"}
    out = {"op": op, "how": d.get("how") or ""}
    if d.get("to_level") is not None:
        out["to_level"] = float(d["to_level"])
    elif d.get("distance"):
        out["distance"] = abs(float(d["distance"]))
    else:
        return {"op": "none", "how": "거리를 못 정함"}
    return out


def distances(p: dict, info: list[dict]) -> list[float]:
    """Per-face move along the normal (+ outward, - inward)."""
    ok = [i for i in info if i.get("ok")]
    if "to_level" in p:
        return [round(p["to_level"] - i["level"], 4) for i in ok]
    d = float(p.get("distance", 0))
    return [(-d if p["op"] == "cut" else d)] * len(ok)


def _trailing_round(code: str):
    """Find a trailing fillet/chamfer step (e.g. `try: body = fillet(body.edges()..., 1.0)`).
    Inserting the push/pull before it, as in a CAD history, re-applies the rounding to the whole new shape at once
    and avoids seam grooves or broken radii. Returns (0-based insert line, target variable) or None."""
    import ast
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    def round_assign(st):
        if isinstance(st, ast.Try) and len(st.body) == 1:
            st = st.body[0]
        if (isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name)
                and isinstance(st.value, ast.Call) and isinstance(st.value.func, ast.Name)
                and st.value.func.id in ("fillet", "chamfer")):
            return st.targets[0].id
        return None

    found = None
    for st in reversed(tree.body):
        var = round_assign(st)
        if var:
            found = (st.lineno - 1, var)
            continue
        if isinstance(st, ast.Assign) and isinstance(st.value, ast.Name):      # part = body
            continue
        if isinstance(st, (ast.Pass, ast.Expr)):
            continue
        break
    return found


def append_code(code: str, info: list[dict], dists: list[float], note: str = "", flush: bool = False) -> str:
    """Insert the push/pull into the code: before a trailing fillet/chamfer step if present, else at the end.
    Faces are re-found at run time from the click point and normal (reproducible from code alone)."""
    ok = [i for i in info if i.get("ok")]
    items = [(tuple(i["point"]), tuple(i["normal"]), float(d), float(i.get("area") or 0),
              [tuple(q) for q in (i.get("outline") or [])])
             for i, d in zip(ok, dists) if abs(d) > 1e-3]
    if not items:
        return code
    tr = _trailing_round(code)
    if tr:
        var = tr[1]
    else:
        var = "part" if re.search(r"^\s*part\s*=", code, re.M) else "result"
    lines = [
        f"# ---- 면 밀고 당기기 (RealCAD push/pull{', ' + note if note else ''}"
        + (", 둥근 모서리 단계 앞에 끼움" if tr else "") + ") ----",
        f"_pp_items = {items!r}",
        "_pp_tools = []",
        "_pp_faces = []",
        "for _pt, _nm, _d, _ar, _ol in _pp_items:",
        "    _p, _n = Vector(*_pt), Vector(*_nm)",
        f"    _cand = [f for f in {var}.faces() if f.geom_type == GeomType.PLANE and f.normal_at().dot(_n) > 0.98]",
        "    _f = min(_cand, key=lambda f: f.distance_to(_p))",
        "    _pp_faces.append(_f)",
        "    _dir = _n if _d > 0 else -_n",
        "    _tool = extrude(_f, amount=abs(_d), dir=_dir)",
        "    # 앞 단계(변수)가 바뀌어 그 자리 면이 크게 달라졌을 때만, 처음 잡았던 면 윤곽의 범위(+0.5 상자) 안으로 제한한다.",
        "    # 평소(면이 그대로)엔 제한하지 않는다: 다각형 윤곽이 곡선 경계와 어긋나 얇은 조각이 생기고 필렛이 깨지기 때문.",
        "    if _ol and _ar > 0 and abs(_f.area - _ar) / _ar > 0.15:",
        "        try:",
        "            _lo = [min(q[k] for q in _ol) - 0.5 for k in range(3)]",
        "            _hi = [max(q[k] for q in _ol) + 0.5 for k in range(3)]",
        "            _e = _dir * abs(_d)",
        "            _lo2 = [min(_lo[0], _lo[0] + _e.X), min(_lo[1], _lo[1] + _e.Y), min(_lo[2], _lo[2] + _e.Z)]",
        "            _hi2 = [max(_hi[0], _hi[0] + _e.X), max(_hi[1], _hi[1] + _e.Y), max(_hi[2], _hi[2] + _e.Z)]",
        "            _lim = Pos(*[(a + b) / 2 for a, b in zip(_lo2, _hi2)]) * Box(*[b - a for a, b in zip(_lo2, _hi2)])   # 직선 변만: 필렛이 안 깨진다",
        "            _tool = _tool & _lim",
        "        except Exception:",
        "            pass",
        "    _pp_tools.append((1 if _d > 0 else -1, _tool))",
        "for _s, _t in _pp_tools:",
        f"    {var} = {var} + _t if _s > 0 else {var} - _t",
    ]
    if flush and not tr:
        # If rounding was already applied, a groove remains at the joint. Within 1.5 mm around the raised face,
        # fill to the same height only where everything 1.5 mm below is solid (outer rounded edges and holes are left alone).
        lines += [
            "_pp_base = " + var,
            "for (_pt, _nm, _d, _ar, _ol), _f in zip(_pp_items, _pp_faces):",
            "    if _d <= 0: continue",
            "    _n = Vector(*_nm)",
            "    _a = Vector(1, 0, 0) if abs(_n.X) < 0.9 else Vector(0, 1, 0)",
            "    _b = _n.cross(_a)",
            "    try:",
            "        _cap = extrude(Pos(_n * _d) * offset(_f, amount=1.5), amount=1.5, dir=-_n)",
            "        for _v in (_a * 1.5, _a * -1.5, _b * 1.5, _b * -1.5):",
            "            _cap = _cap & (Pos(_n * 2.0 + _v) * _pp_base)",
            "        " + var + " = " + var + " + _cap",
            "    except Exception:",
            "        pass",
        ]
    if tr:
        src = code.splitlines()
        k = tr[0]
        return "\n".join(src[:k] + lines + src[k:]) + "\n"
    return code.rstrip() + "\n\n" + "\n".join(lines) + "\n"
