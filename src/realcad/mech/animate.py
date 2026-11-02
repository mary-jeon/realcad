"""Motion frames for the viewer: one input value (crank angle, cam angle, jaw opening) drives every moving part.

The mechanism's own motion function (the one the A7 motion check steps through) is called at each value. For each
moving part the move from its assembled solid to the solid at that value is measured on the B-rep vertices
(least squares, so a compressed spring is followed as well as a turning link), and sent as a 3x4 matrix. The numbers
shown next to the slider (how far a part moved, how far it turned) are measured from the same solids, so the
picture and the numbers cannot disagree.
"""
from __future__ import annotations

import math

import numpy as np

FULL_TURN = ("eccentric_slider", "gear_pump")      # mechanisms that run round and round
MAX_RESIDUAL_MM = 0.05


def _verts(shape) -> np.ndarray:
    return np.array([(v.X, v.Y, v.Z) for v in shape.vertices()], float)


def _fit(ref: np.ndarray, tgt: np.ndarray):
    """Affine map ref -> tgt by least squares -> (3x4 row-major matrix, max residual mm) or None."""
    if len(ref) != len(tgt) or len(ref) < 4:
        return None
    X = np.hstack([ref, np.ones((len(ref), 1))])
    M, *_ = np.linalg.lstsq(X, tgt, rcond=None)                # (4, 3)
    res = float(np.abs(X @ M - tgt).max())
    A = np.zeros((3, 4))
    A[:, :3] = M[:3].T
    A[:, 3] = M[3]
    return A, res


def _loc_move(ref_shape, s):
    """Fast, exact path: the moved solid is the same B-rep with another placement -> its 3x4 move, else None."""
    try:
        if not s.wrapped.IsPartner(ref_shape.wrapped):
            return None
        T = s.wrapped.Location().Transformation().Multiplied(ref_shape.wrapped.Location().Transformation().Inverted())
        return np.array([[T.Value(r, c) for c in range(1, 5)] for r in range(1, 4)], float)
    except Exception:
        return None


def _full_rank(pts: np.ndarray) -> bool:
    if len(pts) < 4:
        return False
    sv = np.linalg.svd(pts - pts.mean(axis=0), compute_uv=False)
    return bool(sv[-1] > 1e-3 * max(sv[0], 1e-9))


def _turn(A: np.ndarray) -> tuple[float, np.ndarray]:
    """(angle deg 0..180, unit axis) of the rotation part of A."""
    R = A[:, :3]
    try:
        u, _s, vt = np.linalg.svd(R)                             # nearest rotation (a spring also stretches)
        R = u @ vt
    except Exception:
        return 0.0, np.zeros(3)
    c = (np.trace(R) - 1.0) / 2.0
    ang = math.degrees(math.acos(max(-1.0, min(1.0, c))))
    ax = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    nrm = np.linalg.norm(ax)
    if nrm < 1e-9:                                               # 0 or 180 deg: take the axis from R + I
        w, v = np.linalg.eigh((R + R.T) / 2.0)
        ax = v[:, -1]
    else:
        ax = ax / nrm
    return ang, ax


def motion_frames(asm, n: int | None = None) -> dict | None:
    """-> {"label", "unit", "values", "parts": {name: [[12 floats] per frame]}, "centers": {name: [x, y, z]},
    "readout": [{name: {move_mm, turn_deg}}], "skipped": [names]} or None when the assembly does not move.
    The viewer blends between frames by turning about each part's centre, so a few frames still play smoothly."""
    if getattr(asm, "motion", None) is None:
        return None
    L = asm.layout or {}
    steps = [float(x) for x in (L.get("motion_steps") or (0, 45, 90, 135, 180, 225, 270, 315))]
    preset = L.get("preset")
    import time
    t0 = time.time()
    first = asm.motion(steps[0])
    slow = time.time() - t0 > 0.15                               # big gears: fewer frames, the viewer blends between
    if preset in FULL_TURN:
        lo, hi, n = 0.0, 360.0, n or (13 if slow else 37)
    else:
        lo, hi, n = min(steps), max(steps), n or (11 if slow else 21)
    values = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    unit = "mm" if preset == "vise" else "deg"
    names = list(first.keys())
    ref = {}
    for name in names:
        p = asm.by_name(name)
        if p is not None:
            bb = p.solid.bounding_box()
            ref[name] = {"solid": p.solid, "c": np.array([bb.center().X, bb.center().Y, bb.center().Z]), "v": None}
    parts = {name: [] for name in ref}
    readout, skipped = [], set()
    for v in values:
        mv = asm.motion(float(v))
        row = {}
        for name, r in ref.items():
            s = mv.get(name)
            if s is None or name in skipped:
                skipped.add(name)
                continue
            A = _loc_move(r["solid"], s)
            if A is None:                                        # rebuilt at this value (a spring): fit on the vertices
                if r["v"] is None:
                    r["v"] = _verts(r["solid"])
                tv = _verts(s)
                fit = _fit(r["v"], tv) if _full_rank(r["v"]) else None
                if fit is None and len(tv) == len(r["v"]) and len(tv):   # too few corners to fit a turn: try a slide
                    t = tv.mean(axis=0) - r["v"].mean(axis=0)
                    A0 = np.hstack([np.eye(3), t[:, None]])
                    fit = (A0, float(np.abs(r["v"] + t - tv).max()))
                if fit is None or fit[1] > MAX_RESIDUAL_MM:
                    skipped.add(name)
                    continue
                A = fit[0]
            parts[name].append([round(float(x), 6) for x in A.ravel()])
            c1 = A[:, :3] @ r["c"] + A[:, 3]                     # where the part's centre went
            ang, ax = _turn(A)
            if r.get("ax") is None and ang > 1.0:
                r["ax"] = ax                                     # sign of the turn follows the first axis seen
            sgn = 1.0 if r.get("ax") is None or float(ax @ r["ax"]) >= 0 else -1.0
            a = sgn * ang
            prev = r.get("prev")
            if prev is not None:                                 # unwrap, so a full turn reads 0 to 360
                while a - prev > 180:
                    a -= 360
                while a - prev < -180:
                    a += 360
            r["prev"] = a
            d = c1 - r["c"]
            if r.get("dir") is None and np.linalg.norm(d) > 0.05:
                r["dir"] = d / np.linalg.norm(d)                 # the way it first moved counts as +
            pos = float(d @ r["dir"]) if r.get("dir") is not None else 0.0
            row[name] = {"move_mm": round(float(np.linalg.norm(d)), 2), "pos_mm": round(pos, 2), "turn_deg": round(abs(a), 1)}
        readout.append(row)
    for name in skipped:                                         # a part that could not be followed stays still
        parts.pop(name, None)
        for row in readout:
            row.pop(name, None)
    if not parts:
        return None
    centers = {name: [round(float(x), 4) for x in ref[name]["c"]] for name in parts}
    return {"label": L.get("motion_label") or ("각도" if unit == "deg" else "이동"), "unit": unit, "centers": centers,
            "values": [round(v, 3) for v in values], "parts": parts, "readout": readout, "skipped": sorted(skipped)}
