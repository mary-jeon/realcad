"""Chopper-style recursive plane splitting (a practical reduction of Luo et al., SIGGRAPH Asia 2012).

Unlike the grid (mesh_split.grid_split):
- Oversized pieces are cut recursively, one plane at a time (BSP).
- Each step generates candidate cut planes at several positions and picks the one that makes
  progress toward the build volume with the narrowest cross-section (a less visible seam), so
  cuts land at narrow spots like head, neck or waist.
- Dowel pin holes (plus pins) at the section centroid add strength and alignment.

Return structure is compatible with mesh_split (verify() works as is).
"""
from __future__ import annotations
import math
import numpy as np
import trimesh

from .mesh_split import _clip, _dowel_sites, _pin_cyl, manifold_ok


def _section_area(mesh, axis, pos):
    """Cross-section area (mm^2) at the cut plane (axis=pos). Large value if it cannot be computed."""
    o = [0.0, 0.0, 0.0]; o[axis] = pos
    n = [0.0, 0.0, 0.0]; n[axis] = 1.0
    try:
        sec = mesh.section(plane_origin=o, plane_normal=n)
        if sec is None:
            return float("inf")
        planar, _ = sec.to_planar()
        return float(sum(p.area for p in planar.polygons_full)) or float("inf")
    except Exception:
        return float("inf")


def _fits(ext, build):
    return all(ext[a] <= build[a] + 1e-6 for a in range(3))


def _candidates(p, build):
    """Candidate planes (axis, pos) that make progress: cut an oversized axis at build size, or at the center."""
    mn, mx = p.bounds[0], p.bounds[1]
    ext = p.extents
    out = []
    for a in range(3):
        if ext[a] <= build[a]:
            continue
        lo, hi = mn[a], mx[a]
        for pos in (lo + build[a] * 0.98, hi - build[a] * 0.98, (lo + hi) / 2.0):
            if lo + 1.0 < pos < hi - 1.0:
                out.append((a, float(pos)))
    return out


def partition(mesh: trimesh.Trimesh, build=(256.0, 256.0, 256.0),
              target_max: float | None = None, dowel_dia: float = 6.0,
              clearance: float = 0.3, dowels: bool = True, max_parts: int = 64):
    """Chopper-style recursive split. return dict(fits,n_pieces,pieces,pins,size,cuts,orig_volume)."""
    m = mesh.copy()
    if target_max:
        m.apply_scale(target_max / float(max(m.extents)))
    m.apply_translation(-m.bounds[0])
    size = tuple(float(x) for x in m.extents)
    orig_vol = float(m.volume)

    if _fits(m.extents, build):
        return {"fits": True, "n_pieces": 1, "pieces": [m], "pins": [],
                "size": size, "cuts": [], "orig_volume": orig_vol}

    pins = []
    cuts = []
    pin_len = max(dowel_dia * 4.0, 24.0)
    stack = [m]
    parts = []
    use_dowel = dowels and manifold_ok()

    while stack and len(parts) + len(stack) < max_parts:
        p = stack.pop()
        if _fits(p.extents, build):
            parts.append(p)
            continue
        cands = _candidates(p, build)
        if not cands:
            parts.append(p)       # cannot cut further: keep as is (safe)
            continue
        # Pick the plane with the smallest seam (section area): cuts at narrow spots
        best = None
        for a, pos in cands:
            area = _section_area(p, a, pos)
            if not math.isfinite(area):
                continue
            if best is None or area < best[0]:
                best = (area, a, pos)
        if best is None:
            parts.append(p); continue
        _area, a, pos = best

        # Dowel holes/pins (subtracted from p before splitting so each side gets half)
        drilled = p
        if use_dowel:
            for site in _dowel_sites(p, a, pos):
                hole = _pin_cyl(a, site, dowel_dia + 2 * clearance, pin_len)
                try:
                    drilled = drilled.difference(hole)
                except Exception:
                    continue
                pins.append(_pin_cyl(a, site, dowel_dia, pin_len - 1.0))

        A = _clip(drilled, a, p.bounds[0][a], pos)
        B = _clip(drilled, a, pos, p.bounds[1][a])
        cuts.append({"axis": "XYZ"[a], "pos": round(pos, 1), "seam_mm2": round(_area, 0)})
        for part in (A, B):
            if part is not None and len(part.faces) > 0:
                stack.append(part)
    parts.extend(stack)       # include the rest when max_parts is reached

    return {"fits": False, "n_pieces": len(parts), "pieces": parts, "pins": pins,
            "size": size, "cuts": cuts, "orig_volume": orig_vol, "build": build}


# ---------------------------------------------------------------------------
# Semantic split: detach protrusions (tail, limbs, head) at narrow necks first
# ---------------------------------------------------------------------------

def _area_profile(mesh, axis, n=48):
    mn, mx = mesh.bounds[0][axis], mesh.bounds[1][axis]
    xs = np.linspace(mn + (mx - mn) * 0.06, mx - (mx - mn) * 0.06, n)
    return xs, np.array([_section_area(mesh, axis, float(x)) for x in xs])


def _best_neck(mesh, min_frac=0.03, max_frac=0.4, deep=0.28):
    """Narrowest 'neck' (axis, pos, area), or None.
    - a local minimum whose section area is below deep times the axis median
    - cutting there leaves the smaller side between min_frac and max_frac of the total volume (a protrusion)
    """
    vol = float(mesh.volume) or 1.0
    best = None
    for a in range(3):
        xs, ar = _area_profile(mesh, a)
        fin = ar[np.isfinite(ar)]
        if len(fin) < 5:
            continue
        med = float(np.median(fin))
        for i in range(1, len(ar) - 1):
            if not math.isfinite(ar[i]):
                continue
            if ar[i] >= ar[i - 1] or ar[i] > ar[i + 1]:   # local minimum
                continue
            if ar[i] > deep * med:                         # narrow enough?
                continue
            lo = _clip(mesh, a, mesh.bounds[0][a], float(xs[i]))
            if lo is None:
                continue
            frac = float(lo.volume) / vol
            frac = min(frac, 1 - frac)
            if not (min_frac <= frac <= max_frac):
                continue
            if best is None or ar[i] < best[2]:
                best = (a, float(xs[i]), float(ar[i]))
    return best


def smart_partition(mesh: trimesh.Trimesh, build=(256.0, 256.0, 256.0),
                    target_max: float | None = None, dowel_dia: float = 6.0,
                    clearance: float = 0.3, dowels: bool = True, max_necks: int = 8):
    """Stage 1: detach protrusions at narrow necks. Stage 2: size-split the remaining pieces (chopper).
    cuts are tagged kind='neck'|'size'."""
    m = mesh.copy()
    if target_max:
        m.apply_scale(target_max / float(max(m.extents)))
    m.apply_translation(-m.bounds[0])
    size = tuple(float(x) for x in m.extents)
    orig_vol = float(m.volume)

    use_dowel = dowels and manifold_ok()
    pins, cuts = [], []
    pin_len = max(dowel_dia * 4.0, 24.0)

    def drill(p, a, pos):
        nonlocal p_out
        d = p
        if use_dowel:
            for site in _dowel_sites(p, a, pos):
                hole = _pin_cyl(a, site, dowel_dia + 2 * clearance, pin_len)
                try:
                    d = d.difference(hole)
                except Exception:
                    continue
                pins.append(_pin_cyl(a, site, dowel_dia, pin_len - 1.0))
        return d

    # Stage 1: detach protrusions (the smaller side) from the body one at a time. Keep the body (avoid oversplitting).
    body = m
    appendages = []
    for _ in range(max_necks):
        neck = _best_neck(body)
        if neck is None:
            break
        a, pos, area = neck
        p_out = None
        d = drill(body, a, pos)
        A = _clip(d, a, d.bounds[0][a], pos)
        B = _clip(d, a, pos, d.bounds[1][a])
        if A is None or B is None:
            break
        small, large = (A, B) if A.volume <= B.volume else (B, A)
        appendages.append(small)
        body = large
        cuts.append({"kind": "neck", "axis": "XYZ"[a], "pos": round(pos, 1), "seam_mm2": round(area, 0)})
    phase1 = appendages + [body]

    # Stage 2: size-split only pieces that are still too big. If still oversized, force a grid split (safe).
    from .mesh_split import grid_split
    pieces = []
    for p in phase1:
        if _fits(p.extents, build):
            pieces.append(p)
            continue
        sub = partition(p, build=build, dowels=dowels, dowel_dia=dowel_dia, clearance=clearance)
        pins.extend(sub.get("pins", []))
        for c in sub.get("cuts", []):
            c = dict(c); c["kind"] = "size"; cuts.append(c)
        for q in sub["pieces"]:
            if _fits(q.extents, build):
                pieces.append(q)
            else:                                   # still oversized: grid
                g = grid_split(q, build=build, dowels=dowels, dowel_dia=dowel_dia, clearance=clearance)
                pieces.extend(g["pieces"]); pins.extend(g.get("pins", []))

    return {"fits": len(pieces) > 1 and False, "n_pieces": len(pieces), "pieces": pieces,
            "pins": pins, "size": size, "cuts": cuts, "orig_volume": orig_vol, "build": build}
