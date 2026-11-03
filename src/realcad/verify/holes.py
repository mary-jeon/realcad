"""Is every hole usable? Measured on the finished part.

A round hole can pass every solid check and still be useless: a rib built over half its mouth, or a wall across its
axis. For each round hole, rays are fired along its axis from inside it, both ways, at the centre and at eight points
round the rim. A step or the floor of a blind hole stops all eight alike, which is normal. Something stopping only
some of them is sitting across the hole, which fails the part. All of them stopped on both sides means a closed void
with no way in: harmless inside a figure, so that one is only a warning.
"""
from __future__ import annotations

import math

import numpy as np

MIN_DIA, MAX_DIA = 1.5, 30.0     # below: too small to matter on a print; above: a cavity, not a hole
RIM = 0.85                       # how far out the rim rays start, as a share of the radius
MAX_HOLES = 200


def _reach(dia: float) -> float:
    """How far past the end of the hole something counts as being in the way (room for a screw or a tool)."""
    return min(max(3.0 * dia, 6.0), 15.0)


def _round_holes(shape) -> list[dict]:
    """Inward facing round surfaces that close into a full circle -> [{dia, axis, centre, length}]."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    groups: dict = {}
    for f in shape.faces():
        ad = BRepAdaptor_Surface(f.wrapped)
        if ad.GetType() != GeomAbs_Cylinder:
            continue
        cyl = ad.Cylinder()
        r = cyl.Radius()
        if not MIN_DIA <= 2 * r <= MAX_DIA:
            continue
        loc, dr = cyl.Axis().Location(), cyl.Axis().Direction()
        o = np.array([loc.X(), loc.Y(), loc.Z()])
        d = np.array([dr.X(), dr.Y(), dr.Z()])
        big = int(np.argmax(np.abs(d)))
        if d[big] < 0:
            d = -d
        o = o - d * float(o @ d)                                  # the point on the axis nearest the origin
        pts = np.array([(v.X, v.Y, v.Z) for v in f.vertices()], float)
        if len(pts) == 0:
            continue
        ts = pts @ d
        t0, t1 = float(ts.min()), float(ts.max())
        if t1 - t0 < 1e-6:
            continue
        p = f.position_at(0.5, 0.5)
        pv = np.array([p.X, p.Y, p.Z])
        n = f.normal_at(p)
        rad = pv - (o + d * float(pv @ d))
        if float(rad @ np.array([n.X, n.Y, n.Z])) >= 0:           # faces away from its axis: a pin, not a hole
            continue
        key = (tuple(np.round(d, 3)), tuple(np.round(o, 2)), round(r, 2))
        groups.setdefault(key, {"r": r, "o": o, "d": d, "faces": []})["faces"].append(
            (t0, t1, float(f.area) / (r * (t1 - t0))))
    holes = []
    for g in groups.values():
        spans: list = []
        for t0, t1, sweep in sorted(g["faces"]):
            if spans and t0 <= spans[-1][1] + 1e-3:
                spans[-1][1] = max(spans[-1][1], t1)
                spans[-1][2] += sweep
            else:
                spans.append([t0, t1, sweep])
        for t0, t1, sweep in spans:
            if math.degrees(sweep) < 300:                         # part of a slot end or a rounded corner
                continue
            holes.append({"dia": 2 * g["r"], "axis": g["d"], "centre": g["o"] + g["d"] * (t0 + t1) / 2, "length": t1 - t0})
    return holes[:MAX_HOLES]


def _distances(mesh, starts: np.ndarray, way: np.ndarray) -> list[float]:
    """Distance to the first material along `way` from each start point (inf: nothing there)."""
    locs, rays, _ = mesh.ray.intersects_location(starts, np.tile(way, (len(starts), 1)), multiple_hits=True)
    near = [math.inf] * len(starts)
    for p, i in zip(locs, rays):
        near[i] = min(near[i], float((p - starts[i]) @ way))
    return near


def blocked_holes(shape, mesh) -> list[dict]:
    """-> [{dia, at, axis, way, stopped, en, ko}] for holes something is in the way of. shape: B-rep, mesh: trimesh."""
    out = []
    for h in _round_holes(shape):
        r, c, d = h["dia"] / 2, h["centre"], h["axis"]
        u = np.cross(d, [1.0, 0, 0] if abs(d[0]) < 0.9 else [0, 1.0, 0])
        u = u / np.linalg.norm(u)
        v = np.cross(d, u)
        rim = np.array([c + RIM * r * (math.cos(a) * u + math.sin(a) * v) for a in np.arange(8) * math.pi / 4])
        limit = h["length"] / 2 + _reach(h["dia"])
        closed = 0
        at = [round(float(x), 1) for x in c]
        label = f"지름 {h['dia']:.1f} mm 구멍 {tuple(at)}"
        partly = None
        for sign in (1.0, -1.0):
            way = sign * d
            rim_d = _distances(mesh, rim, way)
            centre_d = _distances(mesh, c[None, :], way)[0]
            n = sum(x <= limit for x in rim_d)
            if 0 < n < 8 and partly is None:
                partly = (sign, n)
            if n == 8 and centre_d <= limit:
                closed += 1
        name = lambda s: "".join(("+" if s * x > 0 else "-") + a for x, a in zip(d, "XYZ") if abs(x) > 0.5)
        if partly:
            sign, n = partly
            out.append({"dia": round(h["dia"], 2), "at": at, "stopped": n, "sealed": False,
                        "ko": f"{label}: {name(sign)} 쪽을 다른 부분이 일부 막고 있어요",
                        "en": f"The round hole of diameter {h['dia']:.2f} mm at {tuple(at)} is partly covered on its {name(sign)} side "
                              f"({n} of 8 rays round its rim stop within {_reach(h['dia']):.0f} mm of its end). "
                              f"Move or trim the feature in front of it so the whole hole is clear."})
        elif closed == 2:
            out.append({"dia": round(h["dia"], 2), "at": at, "stopped": 8, "sealed": True,
                        "ko": f"{label}: 양쪽이 다 막혀 있어요",
                        "en": f"The round hole of diameter {h['dia']:.2f} mm at {tuple(at)} is closed off at both ends, so nothing can reach it. "
                              f"Open at least one end."})
    return out


def finding(blocked: list[dict], checked: bool = True) -> dict:
    """The H7 finding, in the same shape as the other code path findings."""
    msg = "막힌 구멍 없음 / no blocked holes" if not blocked else "막힌 구멍 / blocked holes: " + "; ".join(b["ko"] for b in blocked[:4])
    if not checked:
        msg = "구멍을 확인 못함 / holes not measured"
    only_voids = checked and blocked and all(b["sealed"] for b in blocked)
    return {"code": "H7", "severity": "SOFT" if only_voids else "HARD", "ok": checked and not blocked, "message": msg,
            "actual": float(len(blocked)), "required": 0.0, "standard": "구멍이 실제로 뚫려 있는지", "suggestion": {}}


def check_files(step_path, stl_path) -> dict:
    """Measure saved files -> {"finding": dict, "note": English repair note or ""}."""
    try:
        import trimesh
        from build123d import import_step
        blocked = blocked_holes(import_step(str(step_path)), trimesh.load(str(stl_path), force="mesh"))
    except Exception as e:
        print(f"[holes] not measured: {type(e).__name__}: {e}", flush=True)
        return {"finding": finding([], checked=False), "note": ""}
    return {"finding": finding(blocked), "note": "\n".join(b["en"] for b in blocked if not b["sealed"])}
