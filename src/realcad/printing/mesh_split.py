"""임포트 메시(STL/OBJ/3MF 등) 대형 모델을 프린터 빌드볼륨에 맞춰 3D 그리드로 분할한다.

split.py(OCC 솔리드·단일축)와 달리 여기서는:
- trimesh 메시를 직접 받아 X·Y·Z 어느 축이든 넘치는 만큼 n등분(그리드)한다.
- 각 내부 절단면의 단면 중심(항상 살 안쪽)에 정렬핀(다월) 구멍을 내서 조립되게 한다.
- 조각 각각이 빌드볼륨에 들어가는지, watertight 인지, 부피가 보존되는지 검증한다.

필요 패키지: trimesh, shapely, rtree, manifold3d(불리언).
"""
from __future__ import annotations
import math
import numpy as np
import trimesh


def _clip(mesh, axis, lo, hi):
    """axis 방향으로 [lo,hi] 슬래브만 남긴다(양쪽 면 캡)."""
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
    """절단면(axis=pos)에서 핀을 박을 3D 좌표들. 단면 폴리곤의 대표점(항상 내부)."""
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
        rp = poly.representative_point()        # 폴리곤 내부 보장
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
    """대형 메시를 빌드볼륨 그리드로 분할.

    return dict(fits, n(축별), pieces:[Trimesh], pins:[Trimesh], size, over, findings...)
    """
    m = mesh.copy()
    if target_max:
        m.apply_scale(target_max / float(max(m.extents)))
    m.apply_translation(-m.bounds[0])          # 양수 좌표
    size = tuple(float(x) for x in m.extents)

    n = [max(1, math.ceil(size[a] / build[a])) for a in range(3)]
    if n == [1, 1, 1]:
        return {"fits": True, "n": n, "pieces": [m], "pins": [], "size": size,
                "cuts": {}, "orig_volume": float(m.volume)}

    mn = m.bounds[0]
    edges = [[mn[a] + (size[a] / n[a]) * k for k in range(n[a] + 1)] for a in range(3)]

    # 1) 다월 구멍: 분할 전 전체 메시에서 빼두면 각 조각이 반쪽씩 가진다
    pins = []
    pin_len = max(dowel_dia * 4.0, 24.0)
    drilled = m
    if dowels and manifold_ok():
        for a in range(3):
            for k in range(1, n[a]):                    # 내부 절단면만
                for site in _dowel_sites(m, a, edges[a][k]):
                    hole = _pin_cyl(a, site, dowel_dia + 2 * clearance, pin_len)
                    try:
                        drilled = drilled.difference(hole)
                    except Exception:
                        continue
                    pin = _pin_cyl(a, site, dowel_dia, pin_len - 1.0)   # 끼울 핀(여유만큼 얇게)
                    pins.append(pin)

    # 2) 그리드 절단
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
    """조각 검증: 전부 빌드볼륨에 들어가나 / watertight / 부피 보존."""
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
