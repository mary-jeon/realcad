"""Mate assembly: place parts by how they touch, not by typed coordinates.

Three mate types, the ones a CAD program's assembly starts with:
  coincident  two flat faces touch (normals opposite; "aligned": true makes them flush, normals the same way)
  distance    two flat faces face each other with a gap ("value" mm)
  concentric  two round features (hole, pin, boss) share one axis ("flip": true turns the part around on that axis)

Features are read from the B-rep: flat faces (P1, P2, ... largest first), holes (H1, ...) and pins or bosses
(B1, ...) where coaxial cylinder faces of one radius are merged into one feature.

The first part (or the one marked "fixed"; only one may be) stays where it is. Every other part is placed from the
mates that connect it to parts already placed, the part that comes out most constrained first, one part at a time
(a closed loop that only works when several parts move together is not solved; its mates are reported with their
error instead). Repeated mates are counted once. Rotation first (face normals and axes), then translation by least squares,
moving the part as little as possible in the directions the mates leave free. Each mate is then measured again
on the placed parts, so a mate that cannot be met (hole patterns that do not line up) is reported with its error
in mm instead of being silently ignored.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np

TOL_MM = 0.02           # a mate counts as met when its measured error is below this
TOL_DEG = 0.05


# ── features ──────────────────────────────────────────────────────────
def _v(x) -> np.ndarray:
    return np.array([float(x.X), float(x.Y), float(x.Z)])


def features(shape) -> dict:
    """B-rep -> {"planes": [...], "axes": [...], "bbox": [[min], [max]]}. Units mm, part coordinates."""
    from build123d import GeomType
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    planes, cyls = [], []
    for f in shape.faces():
        try:
            gt = f.geom_type
            if gt == GeomType.PLANE:
                c = _v(f.center())
                n = _v(f.normal_at(f.center()))
                bb = f.bounding_box()
                planes.append({"normal": n / (np.linalg.norm(n) or 1), "point": c, "area": float(f.area),
                               "box": [[bb.min.X, bb.min.Y, bb.min.Z], [bb.max.X, bb.max.Y, bb.max.Z]]})
            elif gt == GeomType.CYLINDER:
                cy = BRepAdaptor_Surface(f.wrapped).Cylinder()
                ax = cy.Axis()
                d = np.array([ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()])
                q = np.array([ax.Location().X(), ax.Location().Y(), ax.Location().Z()])
                pt = f.position_at(0.5, 0.5)
                n = _v(f.normal_at(pt))
                rad = _v(pt) - q
                rad = rad - d * float(rad @ d)
                kind = "hole" if float(n @ rad) < 0 else "boss"
                ts = [float((_v(vv) - q) @ d) for vv in f.vertices()] or [0.0]
                cyls.append({"dir": d, "point": q, "r": float(cy.Radius()), "kind": kind, "t": (min(ts), max(ts))})
        except Exception:
            continue
    # merge coaxial cylinder faces of the same radius and kind (a hole split by a seam or by a counterbore step)
    axes = []
    for c in cyls:
        for a in axes:
            if a["kind"] != c["kind"] or abs(a["r"] - c["r"]) > 0.01 or abs(abs(a["dir"] @ c["dir"]) - 1) > 1e-4:
                continue
            w = c["point"] - a["point"]
            if np.linalg.norm(w - a["dir"] * (w @ a["dir"])) > 0.01:
                continue
            s = float(np.sign(a["dir"] @ c["dir"]) or 1)
            off = float(w @ a["dir"])
            lo, hi = sorted((off + s * c["t"][0], off + s * c["t"][1]))
            a["t"] = (min(a["t"][0], lo), max(a["t"][1], hi))
            break
        else:
            axes.append(dict(c))
    for a in axes:                      # anchor the axis point at the middle of the feature
        mid = (a["t"][0] + a["t"][1]) / 2
        a["point"] = a["point"] + a["dir"] * mid
        a["length"] = a["t"][1] - a["t"][0]
        a.pop("t", None)
    planes.sort(key=lambda p: -p["area"])
    for i, p in enumerate(planes, 1):
        p["id"] = f"P{i}"
    holes = sorted([a for a in axes if a["kind"] == "hole"], key=lambda a: (round(a["point"][0], 2), round(a["point"][1], 2), round(a["point"][2], 2)))
    bosses = sorted([a for a in axes if a["kind"] == "boss"], key=lambda a: (round(a["point"][0], 2), round(a["point"][1], 2), round(a["point"][2], 2)))
    for i, a in enumerate(holes, 1):
        a["id"] = f"H{i}"
    for i, a in enumerate(bosses, 1):
        a["id"] = f"B{i}"
    bb = shape.bounding_box()
    return {"planes": planes, "axes": holes + bosses,
            "bbox": [[bb.min.X, bb.min.Y, bb.min.Z], [bb.max.X, bb.max.Y, bb.max.Z]]}


def _dir_name(n) -> str:
    for name, v in (("+X", (1, 0, 0)), ("-X", (-1, 0, 0)), ("+Y", (0, 1, 0)), ("-Y", (0, -1, 0)), ("+Z", (0, 0, 1)), ("-Z", (0, 0, -1))):
        if float(np.dot(n, v)) > 0.999:
            return name
    return "[" + ", ".join(f"{x:.3f}" for x in n) + "]"


def _r(x, k=2):
    return [round(float(t), k) for t in x]


def feature_table(feats: dict, max_planes: int = 40, max_axes: int = 60, min_area: float = 1.0) -> dict:
    """JSON-friendly summary for people and for the model that writes mates."""
    pl = [p for p in feats["planes"] if p["area"] >= min_area][:max_planes]
    return {
        "bbox_mm": {"min": _r(feats["bbox"][0]), "max": _r(feats["bbox"][1])},
        "planes": [{"id": p["id"], "normal": _dir_name(p["normal"]), "center": _r(p["point"]), "area_mm2": round(p["area"], 1),
                    "x": _r([p["box"][0][0], p["box"][1][0]]), "y": _r([p["box"][0][1], p["box"][1][1]]),
                    "z": _r([p["box"][0][2], p["box"][1][2]])} for p in pl],
        "axes": [{"id": a["id"], "kind": a["kind"], "dia": round(2 * a["r"], 3), "axis": _dir_name(a["dir"]),
                  "center": _r(a["point"]), "length": round(a["length"], 2)} for a in feats["axes"][:max_axes]],
    }


# ── selectors ────────────────────────────────────────────────────────
_DIRS = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0), "-Y": (0, -1, 0), "+Z": (0, 0, 1), "-Z": (0, 0, -1),
         "TOP": (0, 0, 1), "BOTTOM": (0, 0, -1), "FRONT": (0, -1, 0), "BACK": (0, 1, 0), "RIGHT": (1, 0, 0), "LEFT": (-1, 0, 0)}


class MateError(ValueError):
    pass


def _pick(feats: dict, sel, part: str):
    """Selector -> ("plane"|"axis", feature). sel: "P3" | "H2" | "B1" | {"face": "top"|"+Z", "near": [x,y,z]}
    | {"hole": [x,y,z] or [x,y], "dia": d} | {"boss": [...]}"""
    if isinstance(sel, str):
        sid = sel.strip().upper()
        for p in feats["planes"]:
            if p["id"] == sid:
                return "plane", p
        for a in feats["axes"]:
            if a["id"] == sid:
                return "axis", a
        if sid in _DIRS:
            sel = {"face": sid}
        else:
            raise MateError(f"{part}: '{sel}' 라는 면이나 구멍이 없어요")
    if not isinstance(sel, dict):
        raise MateError(f"{part}: 고르는 방법을 알 수 없어요: {sel!r}")
    if "face" in sel:
        d = _DIRS.get(str(sel["face"]).upper())
        if d is None:
            raise MateError(f"{part}: 면 방향 '{sel['face']}' 을 모르겠어요 (+X, -Z, top, bottom ...)")
        d = np.array(d, float)
        cands = [p for p in feats["planes"] if float(p["normal"] @ d) > 0.999]
        if not cands:
            raise MateError(f"{part}: {sel['face']} 쪽을 보는 평면이 없어요")
        if sel.get("near") is not None:
            q = np.array(sel["near"], float)
            def dist(p):
                lo, hi = np.array(p["box"][0]), np.array(p["box"][1])
                return float(np.linalg.norm(np.clip(q, lo, hi) - q))
            return "plane", min(cands, key=lambda p: (round(dist(p), 3), -p["area"]))
        top = max(float(p["point"] @ d) for p in cands)              # outermost face that way, largest if tied
        return "plane", max([p for p in cands if float(p["point"] @ d) > top - 1e-3], key=lambda p: p["area"])
    for key in ("hole", "boss", "axis"):
        if key in sel:
            cands = [a for a in feats["axes"] if key == "axis" or a["kind"] == key]
            if sel.get("dia") is not None:
                cands = [a for a in cands if abs(2 * a["r"] - float(sel["dia"])) <= max(0.05, 0.05 * float(sel["dia"]))]
            if not cands:
                raise MateError(f"{part}: 조건에 맞는 {'구멍' if key == 'hole' else '원통'}이 없어요 ({sel})")
            q = np.array(list(sel[key]) + [None] * (3 - len(sel[key])), dtype=object) if sel[key] is not None else None
            if q is None:
                return "axis", cands[0]
            def dist(a):
                qq = np.array([float(q[i]) if q[i] is not None else float(a["point"][i]) for i in range(3)])
                w = qq - a["point"]
                return float(np.linalg.norm(w - a["dir"] * (w @ a["dir"])))
            return "axis", min(cands, key=dist)
    raise MateError(f"{part}: 고르는 방법을 알 수 없어요: {sel!r}")


def _split(ref):
    """'case:H3' -> ('case', 'H3'); {"part": "case", ...} -> ('case', {...})."""
    if isinstance(ref, str):
        if ":" not in ref:
            raise MateError(f"'{ref}' 는 '부품이름:면' 꼴이어야 해요 (예: case:H3)")
        a, b = ref.split(":", 1)
        return a.strip(), b.strip()
    if isinstance(ref, dict) and "part" in ref:
        return str(ref["part"]), {k: v for k, v in ref.items() if k != "part"}
    raise MateError(f"짝 지정이 이상해요: {ref!r}")


# ── rigid transforms ─────────────────────────────────────────────────
def _rot_between(u, w) -> np.ndarray:
    u = u / np.linalg.norm(u); w = w / np.linalg.norm(w)
    c = float(np.clip(u @ w, -1, 1))
    k = np.cross(u, w)
    s = float(np.linalg.norm(k))
    if s < 1e-12:
        if c > 0:
            return np.eye(3)
        perp = np.cross(u, [1, 0, 0]) if abs(u[0]) < 0.9 else np.cross(u, [0, 1, 0])
        return _rot_axis(perp / np.linalg.norm(perp), math.pi)
    return _rot_axis(k / s, math.atan2(s, c))


def _rot_axis(k, ang) -> np.ndarray:
    k = np.asarray(k, float); k = k / np.linalg.norm(k)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * (K @ K)


def _angle_about(axis, a, b) -> float:
    """Signed angle about axis that turns a onto b (both projected onto the plane normal to axis)."""
    axis = axis / np.linalg.norm(axis)
    a = a - axis * (a @ axis); b = b - axis * (b @ axis)
    if np.linalg.norm(a) < 1e-9 or np.linalg.norm(b) < 1e-9:
        return 0.0
    return math.atan2(float(np.cross(a, b) @ axis), float(a @ b))


@dataclass
class Placement:
    R: np.ndarray = field(default_factory=lambda: np.eye(3))
    t: np.ndarray = field(default_factory=lambda: np.zeros(3))

    def point(self, p):
        return self.R @ np.asarray(p, float) + self.t

    def vec(self, v):
        return self.R @ np.asarray(v, float)

    def matrix(self) -> list[list[float]]:
        return [list(map(float, self.R[i])) + [float(self.t[i])] for i in range(3)]


def _world(kind: str, feat: dict, P: Placement) -> dict:
    if kind == "plane":
        return {"n": P.vec(feat["normal"]), "p": P.point(feat["point"])}
    return {"d": P.vec(feat["dir"]), "q": P.point(feat["point"])}


def _measure(m: dict, A: dict, B: dict) -> tuple[float, float]:
    """(position error mm, angle error deg) of one mate on placed features A (from 'a') and B (from 'b')."""
    t = m["type"]
    if t in ("coincident", "distance"):
        want = -1.0 if not m.get("aligned") else 1.0
        ang = math.degrees(math.acos(float(np.clip((A["n"] @ B["n"]) * want, -1, 1))))
        gap = float(m.get("value") or 0.0) if t == "distance" else 0.0
        pos = abs(float(A["n"] @ (B["p"] - A["p"])) - gap)
        return pos, ang
    ang = math.degrees(math.acos(float(np.clip(abs(A["d"] @ B["d"]), -1, 1))))
    w = B["q"] - A["q"]
    pos = float(np.linalg.norm(w - A["d"] * (w @ A["d"])))
    return pos, ang


def _solve_one(cons: list[dict], center: np.ndarray) -> tuple[Placement, dict]:
    """Place one moving part from constraints [{kind, tgt (world), mov (local feature), mate}] -> (placement, dof report)."""
    pairs, axes = [], []
    for c in cons:
        m = c["mate"]
        if c["kind"] == "plane":
            want = c["tgt"]["n"] if m.get("aligned") else -c["tgt"]["n"]
            pairs.append(("plane", np.asarray(c["mov"]["normal"], float), want))
        else:
            axes.append(c)
    # rotation: first direction pair, then a second non-parallel one fixes the spin
    R = np.eye(3)
    dirs = list(pairs)
    for c in axes:
        dirs.append(("axis", np.asarray(c["mov"]["dir"], float), c["tgt"]["d"], c))
    if dirs:
        u0, w0 = dirs[0][1], dirs[0][2]
        if dirs[0][0] == "axis":
            c0 = dirs[0][3]
            s = -1.0 if c0["mate"].get("flip") else 1.0
            w0 = w0 * (s if float(u0 @ w0) >= 0 else -s)
        R = _rot_between(u0, w0)
        w0 = w0 / np.linalg.norm(w0)
        spin_fixed = False
        for item in dirs[1:]:
            u, w = R @ item[1], item[2]
            if np.linalg.norm(np.cross(u, w0)) < 1e-6 and np.linalg.norm(np.cross(w, w0)) < 1e-6:
                continue                                          # parallel to the first direction: says nothing about spin
            if item[0] == "axis":
                w = w if float(u @ w) >= 0 else -w
            R = _rot_axis(w0, _angle_about(w0, u, w)) @ R
            spin_fixed = True
            break
        if not spin_fixed:
            par = [c for c in axes if np.linalg.norm(np.cross(R @ np.asarray(c["mov"]["dir"], float), w0)) < 1e-6]
            # two parallel axes that are really apart (a hole pattern) fix the spin; the same axis twice does not
            best, sep = None, 1e-3
            for i in range(len(par)):
                for j in range(i + 1, len(par)):
                    w = par[j]["tgt"]["q"] - par[i]["tgt"]["q"]
                    off = float(np.linalg.norm(w - w0 * (w @ w0)))
                    if off > sep:
                        best, sep = (par[i], par[j]), off
            if best:
                a, b = best
                u = R @ (np.asarray(b["mov"]["point"]) - np.asarray(a["mov"]["point"]))
                w = b["tgt"]["q"] - a["tgt"]["q"]
                R = _rot_axis(w0, _angle_about(w0, u, w)) @ R
                spin_fixed = True
        rot_free = 0 if spin_fixed else 1
    else:
        rot_free = 3
    # translation: x' = R (x - center) + center + t, least squares, smallest t where unconstrained
    rows, rhs = [], []
    for c in cons:
        m = c["mate"]
        if c["kind"] == "plane":
            n = c["tgt"]["n"]
            pm = R @ (np.asarray(c["mov"]["point"]) - center) + center
            gap = float(m.get("value") or 0.0) if m["type"] == "distance" else 0.0
            sign = 1.0 if (not m.get("aligned") or c["tgt_is_a"]) else -1.0     # the gap lies in front of face a
            rows.append(n); rhs.append(float(n @ (c["tgt"]["p"] - pm)) + sign * gap)
        else:
            d = c["tgt"]["d"] / np.linalg.norm(c["tgt"]["d"])
            Pm = np.eye(3) - np.outer(d, d)
            qm = R @ (np.asarray(c["mov"]["point"]) - center) + center
            for i in range(3):
                rows.append(Pm[i]); rhs.append(float(Pm[i] @ (c["tgt"]["q"] - qm)))
    if rows:
        A = np.array(rows); b = np.array(rhs)
        t, *_ = np.linalg.lstsq(A, b, rcond=None)
        rank = int(np.linalg.matrix_rank(A, tol=1e-6))
    else:
        t, rank = np.zeros(3), 0
    P = Placement(R=R, t=(center - R @ center) + t)
    return P, {"move_free": 3 - rank, "turn_free": rot_free}


@dataclass
class MatePart:
    name: str
    solid: object
    no: int = 0
    spec: str = ""
    qty: int = 1
    material: str = ""
    fixed: bool = False
    feats: dict | None = None
    placement: Placement = field(default_factory=Placement)
    dof: dict = field(default_factory=dict)


def _norm_mate(m: dict) -> dict:
    t = str(m.get("type", "")).lower().strip()
    t = {"coincide": "coincident", "touch": "coincident", "일치": "coincident", "동심": "concentric",
         "coaxial": "concentric", "거리": "distance", "offset": "distance"}.get(t, t)
    if t not in ("coincident", "distance", "concentric"):
        raise MateError(f"메이트 종류 '{m.get('type')}' 는 지원하지 않아요 (coincident, distance, concentric)")
    out = dict(m); out["type"] = t
    if t == "distance":
        try:
            out["value"] = float(m.get("value"))
        except Exception:
            raise MateError("distance 메이트에는 value(mm)가 있어야 해요")
        if not math.isfinite(out["value"]) or abs(out["value"]) > 10000:
            raise MateError("distance 값은 -10000 ~ 10000 mm 안의 숫자여야 해요")
    return out


def solve(parts: list[MatePart], mates: list[dict]) -> dict:
    """Place parts in their list order. Returns {"parts", "mates": [measured], "unplaced": [...]}; parts get .placement."""
    by = {p.name: p for p in parts}
    if len(by) != len(parts):
        raise MateError("부품 이름이 겹쳐요. 이름을 서로 다르게 지어 주세요")
    for p in parts:
        if p.feats is None:
            p.feats = features(p.solid)
    ms = []
    for i, m in enumerate(mates, 1):
        m = _norm_mate(m)
        pa, sa = _split(m["a"]); pb, sb = _split(m["b"])
        for pn in (pa, pb):
            if pn not in by:
                raise MateError(f"메이트 {i}: '{pn}' 부품이 없어요 (있는 부품: {', '.join(by)})")
        if pa == pb:
            raise MateError(f"메이트 {i}: 한 부품 안에서 짝을 지을 수 없어요")
        ka, fa = _pick(by[pa].feats, sa, pa)
        kb, fb = _pick(by[pb].feats, sb, pb)
        if m["type"] == "concentric" and not (ka == kb == "axis"):
            raise MateError(f"메이트 {i}: concentric 은 구멍이나 원통끼리만 돼요")
        if m["type"] != "concentric" and not (ka == kb == "plane"):
            raise MateError(f"메이트 {i}: {m['type']} 는 평면끼리만 돼요")
        key = (m["type"], *sorted([(pa, fa["id"]), (pb, fb["id"])]), m.get("value"), bool(m.get("aligned")), bool(m.get("flip")))
        dup = any(e["key"] == key for e in ms)
        ms.append({"i": i, "mate": m, "a": (pa, ka, fa), "b": (pb, kb, fb), "key": key, "dup": dup})
    fixed = [p for p in parts if p.fixed]
    if len(fixed) > 1:
        raise MateError("고정 부품은 하나만 둘 수 있어요: " + ", ".join(p.name for p in fixed))
    ground = fixed[0] if fixed else parts[0]
    placed = {ground.name}
    ground.dof = {"move_free": 0, "turn_free": 0, "fixed": True}
    order = [p.name for p in parts]

    def cons_for(name, against):
        cons = []
        for e in ms:
            if e["dup"]:
                continue                                          # the same mate twice adds nothing
            for me, other, tgt_is_a in ((e["b"], e["a"], True), (e["a"], e["b"], False)):
                if me[0] == name and other[0] in against:
                    tgt = _world(other[1], other[2], by[other[0]].placement)
                    cons.append({"kind": me[1], "mov": me[2], "tgt": tgt, "mate": e["mate"], "tgt_is_a": tgt_is_a})
        return cons

    def center_of(p):
        bb = p.feats["bbox"]
        return (np.array(bb[0]) + np.array(bb[1])) / 2

    # place the part that ends up most constrained first, so a part that hangs on two others waits for both
    while True:
        best = None
        for name in order:
            if name in placed:
                continue
            cons = cons_for(name, placed)
            if not cons:
                continue
            P, dof = _solve_one(cons, center_of(by[name]))
            free = dof["move_free"] + dof["turn_free"]
            if best is None or free < best[0]:
                best = (free, name, P, dof)
        if best is None:
            break
        _, name, P, dof = best
        by[name].placement, by[name].dof = P, dof
        placed.add(name)
    measured = []
    for e in ms:
        pa, ka, fa = e["a"]; pb, kb, fb = e["b"]
        A = _world(ka, fa, by[pa].placement); B = _world(kb, fb, by[pb].placement)
        pos, ang = _measure(e["mate"], A, B)
        ok = pa in placed and pb in placed and pos <= TOL_MM and ang <= TOL_DEG
        measured.append({"no": e["i"], "type": e["mate"]["type"], "a": f"{pa}:{fa['id']}", "b": f"{pb}:{fb['id']}",
                         **({"duplicate": True} if e["dup"] else {}),
                         **({"value": e["mate"]["value"]} if e["mate"]["type"] == "distance" else {}),
                         "error_mm": round(pos, 4), "error_deg": round(ang, 4), "ok": ok})
    return {"mates": measured, "unplaced": [n for n in order if n not in placed]}


def placed_shape(p: MatePart):
    """The part's solid moved to its placement."""
    from build123d import Location
    from OCP.gp import gp_Trsf
    M = p.placement.matrix()
    tr = gp_Trsf()
    tr.SetValues(M[0][0], M[0][1], M[0][2], M[0][3], M[1][0], M[1][1], M[1][2], M[1][3], M[2][0], M[2][1], M[2][2], M[2][3])
    s = p.solid.moved(Location(tr))
    try:
        s.label = p.name
    except Exception:
        pass
    return s


def dof_text(d: dict) -> str:
    if not d:
        return "메이트 없음 / not mated"
    if d.get("fixed"):
        return "고정 / fixed"
    mv, tn = d.get("move_free", 0), d.get("turn_free", 0)
    if not mv and not tn:
        return "완전 구속 / fully defined"
    bits = []
    if mv:
        bits.append(f"이동 {mv}방향")
    if tn:
        bits.append(f"회전 {tn}방향")
    return "덜 구속 / under defined: " + ", ".join(bits) + " 자유"


def safe_name(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", str(s)).strip("_")[:40] or "part"
