"""Split large imported meshes (STL/OBJ/3MF etc.) into a 3D grid that fits the printer build volume.

Unlike split.py (OCC solids, single axis):
- Takes a trimesh mesh directly and splits any of X, Y, Z into n parts (grid) as needed.
- Puts alignment pin (dowel) holes at the section centroid of each inner cut plane (always inside
  material) so the pieces assemble.
- Verifies each piece fits the build volume, is watertight, and that volume is preserved.

Requires: trimesh, shapely, rtree, manifold3d (booleans).
"""
from __future__ import annotations
import math
import numpy as np
import trimesh


def _clip(mesh, axis, lo, hi):
    """Keep only the [lo,hi] slab along axis (both faces capped)."""
    o = [0.0, 0.0, 0.0]; o[axis] = lo
    n = [0.0, 0.0, 0.0]; n[axis] = 1.0
    out = mesh.slice_plane(o, n, cap=True)
    if out is None or out.is_empty:
        return None
    o2 = [0.0, 0.0, 0.0]; o2[axis] = hi
    n2 = [0.0, 0.0, 0.0]; n2[axis] = -1.0
    out = out.slice_plane(o2, n2, cap=True)
    if out is None or out.is_empty or len(out.faces) == 0:
        return None
    return out


def _dowel_sites(mesh, axis, pos, max_pins=2):
    """3D points for pins on the cut plane (axis=pos): representative points of the section polygons (always inside)."""
    o = [0.0, 0.0, 0.0]; o[axis] = pos
    n = [0.0, 0.0, 0.0]; n[axis] = 1.0
    try:
        sec = mesh.section(plane_origin=o, plane_normal=n)
        if sec is None:
            return []
        planar, to_3d = sec.to_planar()
        polys = sorted(planar.polygons_full, key=lambda p: p.area, reverse=True)
    except Exception:
        return []
    sites = []
    for poly in polys[:max_pins]:
        rp = poly.representative_point()        # guaranteed inside the polygon
        p3 = trimesh.transformations.transform_points([[rp.x, rp.y, 0.0]], to_3d)[0]
        p3[axis] = pos
        sites.append(p3)
    return sites


def _pin_cyl(axis, center, dia, length):
    c = trimesh.creation.cylinder(radius=dia / 2.0, height=length, sections=24)
    if axis == 0:
        c.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    elif axis == 1:
        c.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
    c.apply_translation(center)
    return c


def grid_split(mesh: trimesh.Trimesh, build=(256.0, 256.0, 256.0),
               target_max: float | None = None, dowel_dia: float = 6.0,
               clearance: float = 0.3, dowels: bool = True):
    """Split a large mesh into a build-volume grid.

    return dict(fits, n (per axis), pieces:[Trimesh], pins:[Trimesh], size, over, findings...)
    """
    m = mesh.copy()
    if target_max:
        m.apply_scale(target_max / float(max(m.extents)))
    m.apply_translation(-m.bounds[0])          # positive coordinates
    size = tuple(float(x) for x in m.extents)

    n = [max(1, math.ceil(size[a] / build[a])) for a in range(3)]
    if n == [1, 1, 1]:
        return {"fits": True, "n": n, "pieces": [m], "pins": [], "size": size,
                "cuts": {}, "orig_volume": float(m.volume)}

    mn = m.bounds[0]
    edges = [[mn[a] + (size[a] / n[a]) * k for k in range(n[a] + 1)] for a in range(3)]

    # 1) Dowel holes: subtract from the whole mesh before splitting so each piece gets half
    pins = []
    pin_len = max(dowel_dia * 4.0, 24.0)
    drilled = m
    if dowels and manifold_ok():
        for a in range(3):
            for k in range(1, n[a]):                    # inner cut planes only
                for site in _dowel_sites(m, a, edges[a][k]):
                    hole = _pin_cyl(a, site, dowel_dia + 2 * clearance, pin_len)
                    try:
                        drilled = drilled.difference(hole)
                    except Exception:
                        continue
                    pin = _pin_cyl(a, site, dowel_dia, pin_len - 1.0)   # pin to insert (thinner by the clearance)
                    pins.append(pin)

    # 2) Grid cut
    pieces = []
    for i in range(n[0]):
        for j in range(n[1]):
            for k in range(n[2]):
                p = drilled
                for a, idx in ((0, i), (1, j), (2, k)):
                    if n[a] == 1:
                        continue
                    p = _clip(p, a, edges[a][idx], edges[a][idx + 1])
                    if p is None:
                        break
                if p is not None and len(p.faces) > 0:
                    pieces.append(p)

    return {"fits": False, "n": n, "pieces": pieces, "pins": pins,
            "size": size, "orig_volume": float(m.volume),
            "build": build}


def manifold_ok() -> bool:
    try:
        import manifold3d  # noqa: F401
        return True
    except Exception:
        return False


def verify(result, build=(256.0, 256.0, 256.0)):
    """Verify pieces: all fit the build volume, watertight, volume preserved."""
    pieces = result["pieces"]
    rows = []
    allfit = True
    vol = 0.0
    for idx, p in enumerate(pieces):
        ext = [float(x) for x in p.extents]
        ok = all(ext[a] <= build[a] + 1e-6 for a in range(3))
        allfit = allfit and ok
        vol += float(p.volume)
        rows.append({"i": idx, "size": [round(x, 1) for x in ext],
                     "fits": ok, "watertight": bool(p.is_watertight),
                     "faces": int(len(p.faces))})
    ov = result.get("orig_volume", 0.0)
    return {"pieces": rows, "all_fit": allfit, "n_pieces": len(pieces),
            "volume_orig_cm3": round(ov / 1000, 1),
            "volume_pieces_cm3": round(vol / 1000, 1),
            "volume_err_pct": round(abs(ov - vol) / ov * 100, 3) if ov else None,
            "pins": len(result.get("pins", []))}
