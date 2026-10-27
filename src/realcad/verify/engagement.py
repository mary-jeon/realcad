"""H3 체결 깊이(thread engagement) 측정 — 맥>공모전 샘플 기반.

두 가지:
- engagement_overlap: 볼트 축 영역 ∩ 탭 구멍 영역의 z-방향 길이 (PoC, 안정적)
- engagement_raycast: 볼트 축선을 탭된 바디에 raycast 해 내부 길이 (프로덕션, 빠름)
"""
from __future__ import annotations
from build123d import Part

EPS = 1e-6


def engagement_overlap(bolt_shank: Part, threaded_region: Part) -> float:
    """볼트 축(shank)과 '탭된 나사 영역' 솔리드의 교차 높이(mm).
    threaded_region = 피치경 지름 × 탭 깊이의 원기둥(나사가 무는 영역)."""
    try:
        inter = bolt_shank & threaded_region
    except Exception:
        return 0.0
    if inter is None or inter.volume < EPS:
        return 0.0
    return float(inter.bounding_box().size.Z)


def engagement_raycast(tapped_part: Part, axis_point, axis_dir) -> float:
    """볼트 축선을 tapped_part 에 raycast. enter/exit 쌍 길이 합(mm). Boolean 없이 빠름.
    축선에 와셔·너트 등 다른 바디가 걸리지 않게 tapped_part 는 '탭된 바디 하나'만 넣는다.
    (맥>공모전 option B)"""
    from OCP.gp import gp_Pnt, gp_Dir, gp_Lin
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    shape = tapped_part.wrapped if hasattr(tapped_part, "wrapped") else tapped_part
    inter = IntCurvesFace_ShapeIntersector()
    inter.Load(shape, 1e-7)
    line = gp_Lin(gp_Pnt(*axis_point), gp_Dir(*axis_dir))
    inter.Perform(line, -1e9, 1e9)
    if not inter.IsDone() or inter.NbPnt() == 0:
        return 0.0
    params = sorted(inter.WParameter(i) for i in range(1, inter.NbPnt() + 1))
    if len(params) % 2 != 0:          # 경계 접함 → 포기
        return 0.0
    return sum(params[i + 1] - params[i] for i in range(0, len(params), 2))
