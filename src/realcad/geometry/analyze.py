"""가져온 STEP 모델에서 나사구멍(작은 수직 원통)을 자동 감지한다."""
from __future__ import annotations


def detect_mount_holes(part, r_min: float = 1.0, r_max: float = 2.2):
    """part 의 면 중 반지름 r_min~r_max, 축이 z 인 원통(=관통 나사구멍) 중심 (x,y,r) 목록.
    같은 구멍의 중복 면은 (x,y) 반올림으로 합친다."""
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
            if abs(ax.Direction().Z()) < 0.9:      # z축 방향만(수직 관통)
                continue
            loc = ax.Location()
            key = (round(loc.X(), 1), round(loc.Y(), 1))
            seen[key] = (loc.X(), loc.Y(), r)
        except Exception:
            continue
    return list(seen.values())


def measure_hole_dia(part, x: float, y: float, tol: float = 0.5) -> float | None:
    """완성 솔리드에서 (x,y) 위치의 z축 원통면 반지름을 실측해 구멍 지름(mm)을 돌려준다.
    H2 는 '우리가 뚫은 값'이 아니라 이 실측값으로 판정한다. 없으면 None."""
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
