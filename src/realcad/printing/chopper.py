"""Chopper식 재귀 평면 분할 (Luo et al., SIGGRAPH Asia 2012 아이디어의 실용 축약판).

격자(mesh_split.grid_split)와 달리:
- 넘치는 조각을 재귀로 '한 평면씩' 자른다(BSP).
- 각 단계에서 후보 절단면을 여러 위치로 생성하고, "빌드볼륨 쪽으로 진행 + 절단 단면이
  가장 좁은(=솔기가 자연스럽고 눈에 덜 띄는) 평면"을 고른다. → 머리/목/허리 같은 잘록한
  곳에서 끊긴다.
- 절단면 단면 중심에 다월 핀 구멍(+핀)으로 강도·정렬 보강.

반환 구조는 mesh_split 과 호환(verify() 그대로 사용).
"""
from __future__ import annotations
import math
import numpy as np
import trimesh

from .mesh_split import _clip, _dowel_sites, _pin_cyl, manifold_ok


def _section_area(mesh, axis, pos):
    """절단면(axis=pos)의 단면 넓이(mm^2). 못 구하면 큰 값."""
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
    """진행 가능한 후보 평면 (axis, pos). 넘치는 축을 build 크기로 당겨 자르거나 중앙."""
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
    """Chopper식 재귀 분할. return dict(fits,n_pieces,pieces,pins,size,cuts,orig_volume)."""
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
            parts.append(p)       # 더 못 자르면 그대로(안전)
            continue
        # 솔기(단면 넓이) 최소 평면 선택 — 잘록한 곳에서 끊김
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

        # 다월 구멍/핀 (분할 전 p 에서 빼서 양쪽이 반반씩)
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
    parts.extend(stack)       # max_parts 도달 시 남은 것 포함

    return {"fits": False, "n_pieces": len(parts), "pieces": parts, "pins": pins,
            "size": size, "cuts": cuts, "orig_volume": orig_vol, "build": build}


# ---------------------------------------------------------------------------
# 의미 기반 분할: 잘록한 목(neck)에서 돌출부(꼬리·팔다리·머리)를 먼저 떼어냄
# ---------------------------------------------------------------------------

def _area_profile(mesh, axis, n=48):
    mn, mx = mesh.bounds[0][axis], mesh.bounds[1][axis]
    xs = np.linspace(mn + (mx - mn) * 0.06, mx - (mx - mn) * 0.06, n)
    return xs, np.array([_section_area(mesh, axis, float(x)) for x in xs])


def _best_neck(mesh, min_frac=0.03, max_frac=0.4, deep=0.28):
    """가장 잘록한 '목' (axis,pos,area). 없으면 None.
    - 단면적이 그 축 중앙값의 deep 배 미만인 국소 최소
    - 그 위치에서 자르면 작은 쪽 부피가 전체의 min_frac~max_frac (=돌출부)
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
            if ar[i] >= ar[i - 1] or ar[i] > ar[i + 1]:   # 국소 최소
                continue
            if ar[i] > deep * med:                         # 충분히 잘록?
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
    """1단계: 잘록한 목에서 돌출부 선분리 → 2단계: 남은 조각 크기분할(chopper).
    cuts 에 kind='neck'|'size' 표기."""
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

    # 1단계: 몸통에서 돌출부(작은 쪽)만 하나씩 떼어낸다. 몸통은 보존(과분할 방지).
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

    # 2단계: 아직 큰 조각만 크기분할. 끝나고도 넘치면 격자로 강제 분할(안전).
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
            else:                                   # 그래도 넘치면 격자
                g = grid_split(q, build=build, dowels=dowels, dowel_dia=dowel_dia, clearance=clearance)
                pieces.extend(g["pieces"]); pins.extend(g.get("pins", []))

    return {"fits": len(pieces) > 1 and False, "n_pieces": len(pieces), "pieces": pieces,
            "pins": pins, "size": size, "cuts": cuts, "orig_volume": orig_vol, "build": build}
