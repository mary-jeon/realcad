"""Auto-detect screw holes (small vertical cylinders) in an imported STEP model."""
from __future__ import annotations


def detect_mount_holes(part, r_min: float = 1.0, r_max: float = 2.2):
    """List of (x,y,r) centers of z-axis cylindrical faces (= through screw holes) on `part` with radius r_min to r_max.
    Duplicate faces of the same hole are merged by rounding (x,y)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    try:
        from build123d import GeomType
        cyl_type = GeomType.CYLINDER
    except Exception:
        cyl_type = None
    seen = {}
    for f in part.faces():
        try:
            if cyl_type is not None and f.geom_type != cyl_type:
                continue
            s = BRepAdaptor_Surface(f.wrapped)
            cyl = s.Cylinder()
            r = cyl.Radius()
            ax = cyl.Axis()
            if not (r_min < r < r_max):
                continue
            if abs(ax.Direction().Z()) < 0.9:      # Z axis only (vertical through holes)
                continue
            loc = ax.Location()
            key = (round(loc.X(), 1), round(loc.Y(), 1))
            seen[key] = (loc.X(), loc.Y(), r)
        except Exception:
            continue
    return list(seen.values())


def measure_hole_dia(part, x: float, y: float, tol: float = 0.5) -> float | None:
    """Measure the radius of the z-axis cylindrical face at (x,y) on the finished solid and return the hole diameter (mm).
    H2 judges by this measurement, not by the value we cut. None if not found."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    try:
        from build123d import GeomType
    except Exception:
        return None
    best = None
    for f in part.faces():
        try:
            if f.geom_type != GeomType.CYLINDER:
                continue
            cyl = BRepAdaptor_Surface(f.wrapped).Cylinder()
            ax = cyl.Axis()
            if abs(ax.Direction().Z()) < 0.9:
                continue
            loc = ax.Location()
            if abs(loc.X() - x) > tol or abs(loc.Y() - y) > tol:
                continue
            d = 2.0 * cyl.Radius()
            best = d if best is None else min(best, d)
        except Exception:
            continue
    return best
