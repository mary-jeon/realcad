"""Measured printability (DfAM): wall thickness, overhang, print orientation recommendation.

Tessellates the build123d solid to STL, then uses trimesh raycasting to measure the real thinnest
wall and its location, and compares support area and height for each of the 6 axis directions to
pick the one needing the least. A step up from M1 (compares a given wall number) and M3 (overhang
ratio): measures directly from the shape instead of taking numbers.

Best-effort against kernel failures or a missing ray engine: anything that cannot be measured is
None, no exception is raised.
"""
from __future__ import annotations
import math
import tempfile
from pathlib import Path


def _to_trimesh(part):
    """build123d solid -> trimesh (tessellation with an explicit tolerance)."""
    import trimesh
    from build123d import export_stl
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "m.stl"
        export_stl(part, str(p), tolerance=0.05, angular_tolerance=0.3)
        m = trimesh.load(str(p))
    return m


def _raycast_one(m, samples: int, seed: int):
    """(thickness array, point coordinate array) for one body. (empty, empty) if sampling or rays fail."""
    import numpy as np
    import trimesh
    import warnings
    if not hasattr(m, "faces") or len(m.faces) == 0:
        return np.empty(0), np.empty((0, 3))
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")
        try:
            pts, fid = trimesh.sample.sample_surface_even(m, samples, seed=seed)
        except TypeError:
            pts, fid = trimesh.sample.sample_surface(m, samples)
        if len(pts) == 0:
            return np.empty(0), np.empty((0, 3))
        n = m.face_normals[fid]
        eps = max(m.scale * 1e-4, 1e-4)
        origins = pts - n * eps                       # start just inside the surface
        locs, ray_idx, _ = m.ray.intersects_location(origins, -n, multiple_hits=False)
    if len(locs) == 0:
        return np.empty(0), np.empty((0, 3))
    # intersects_location: locs[i] is the hit for ray ray_idx[i]. Thickness = origin to hit.
    th = np.linalg.norm(locs - origins[ray_idx], axis=1)
    good = th > max(m.scale * 1e-4, 1e-4) * 2
    return th[good], locs[good]


def _wall_from_mesh(m, samples: int = 1500, seed: int = 0) -> dict | None:
    """Raycast thickness field. Assemblies (multiple bodies) are measured per body so rays do not
    cross gaps between parts and mistake a neighbor for a wall."""
    try:
        import numpy as np
        if not hasattr(m, "faces") or len(m.faces) == 0:
            return None
        bodies = m.split(only_watertight=False)
        if len(bodies) > 8:
            return None                               # assembly, multi-shell: per-part wall thickness is meaningless (orientation only)
        if len(bodies) <= 1:
            bodies = [m]
        ths, locs = [], []
        budget = max(samples // max(len(bodies), 1), 300)
        for i, b in enumerate(bodies):
            t, l = _raycast_one(b, budget, seed + i)
            if len(t):
                ths.append(t); locs.append(l)
        if not ths:
            return None
        th = np.concatenate(ths); loc = np.concatenate(locs)
        k = int(np.argmin(th))
        return {
            "min_mm": round(float(th.min()), 3),
            "p05_mm": round(float(np.percentile(th, 5)), 3),
            "median_mm": round(float(np.median(th)), 3),
            "samples_valid": int(len(th)),
            "bodies": len(bodies),
            "thinnest": {"xyz": [round(float(v), 2) for v in loc[k]], "mm": round(float(th[k]), 3)},
        }
    except Exception:
        return None


def wall_thickness(part, samples: int = 1500, seed: int = 0) -> dict | None:
    """Raycast thickness field. Shoot inward (-normal) from surface points and measure the distance to the opposite wall.

    The min can drop near 0 at edges, so p05_mm is taken as the real minimum wall.
    Returns {min_mm, p05_mm, median_mm, samples_valid, thinnest:{xyz, mm}} or None.
    """
    try:
        return _wall_from_mesh(_to_trimesh(part), samples=samples, seed=seed)
    except Exception:
        return None


def _overhang_area(m, angle_limit: float) -> tuple[float, float]:
    """(downward-facing area in mm^2 shallower than angle_limit from horizontal, % of total area).

    Excludes the bottom contact face. A measure of the area needing support.
    """
    import numpy as np
    n = m.face_normals
    zc = m.triangles_center[:, 2]
    zmin = m.vertices[:, 2].min()
    down = n[:, 2] < -math.cos(math.radians(90 - angle_limit))   # tilted downward by angle_limit or more
    down &= zc > zmin + 0.5                                       # exclude the bottom contact face
    area = float(m.area_faces[down].sum())
    return area, (100.0 * area / max(float(m.area), 1e-9))


def _orient_from_mesh(m, angle_limit: float = 45.0) -> dict | None:
    try:
        import numpy as np
        import trimesh
        if not hasattr(m, "faces") or len(m.faces) == 0:
            return None
        rot = {
            "그대로 / as-is": np.eye(4),
            "뒤집기 / flip": trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]),
            "X +90": trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]),
            "X -90": trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]),
            "Y +90": trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]),
            "Y -90": trimesh.transformations.rotation_matrix(-math.pi / 2, [0, 1, 0]),
        }
        cands = []
        for name, T in rot.items():
            mm = m.copy(); mm.apply_transform(T)
            area, pct = _overhang_area(mm, angle_limit)
            cands.append({"orientation": name,
                          "support_area_mm2": round(area, 1),
                          "support_pct": round(pct, 1),
                          "height_mm": round(float(mm.extents[2]), 1)})
        # If the support difference is small (within 2% of surface area or 25 mm^2), the lower one wins: less tipping risk and print time.
        # e.g. do not stand a split plate up to print 150 mm tall just for a few mm^2 of pin hole ceiling.
        lo = min(c["support_area_mm2"] for c in cands)
        tol = max(0.02 * float(m.area), 25.0)
        near = [c for c in cands if c["support_area_mm2"] <= lo + tol]
        best = min(near, key=lambda c: (c["height_mm"], c["support_area_mm2"]))
        return {"angle_limit_deg": angle_limit, "best": best["orientation"], "candidates": cands}
    except Exception:
        return None


def orientation_advice(part, angle_limit: float = 45.0) -> dict | None:
    """Measure support area and print height for each of the 6 axis directions and recommend the one with the least support."""
    try:
        return _orient_from_mesh(_to_trimesh(part), angle_limit=angle_limit)
    except Exception:
        return None


def measure(part, *, samples: int = 1500, angle_limit: float = 45.0) -> dict:
    """Wall thickness + orientation recommendation together. One tessellation measures both. Each item is None on failure."""
    try:
        m = _to_trimesh(part)
    except Exception:
        return {"wall": None, "orientation": None}
    return {"wall": _wall_from_mesh(m, samples=samples),
            "orientation": _orient_from_mesh(m, angle_limit=angle_limit)}
