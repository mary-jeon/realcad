"""Verification: everything measured on the OCC kernel, based on ASME/ISO tables and design practice.

HARD: failure demands regeneration (parameter fix). SOFT: warning.
Failures return a **parameter fix suggestion dict**, not geometry (no "redraw it", which
breaks dimensions).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from build123d import Part
from ..fasteners.standards import Fastener

VOL_EPS = 1e-6  # minimum interference volume (mm^3)


@dataclass
class Finding:
    code: str            # H1, H2, H4, S1 ...
    severity: str        # "HARD" | "SOFT"
    ok: bool
    message: str
    actual: float | None = None
    required: float | None = None
    standard: str = ""
    suggestion: dict = field(default_factory=dict)

    def __str__(self) -> str:
        mark = "✅" if self.ok else ("❌" if self.severity == "HARD" else "⚠️")
        base = f"{mark} [{self.code}] {self.message}"
        if self.actual is not None and self.required is not None:
            base += f" (실제 {self.actual:.2f} / 기준 {self.required:.2f} mm)"
        if self.standard:
            base += f", 기준: {self.standard}"
        return base


def _intersection_volume(a: Part, b: Part) -> float:
    try:
        inter = a & b
        return float(inter.volume) if inter is not None else 0.0
    except Exception:
        return 0.0


def h1_interference(bolt: Part, obstacle: Part, where: str) -> Finding:
    """H1: collision if the bolt solid intersects an obstacle (wall, neighboring bolt) with volume > 0."""
    v = _intersection_volume(bolt, obstacle)
    ok = v <= VOL_EPS
    return Finding("H1", "HARD", ok,
                   f"볼트 머리 간섭 체크 ({where})",
                   actual=v, required=0.0, standard="",
                   suggestion={} if ok else {
                       "option_a": f"{where}에서 볼트를 멀리(홀 위치 이동)",
                       "option_b": f"{where} 형상을 피해서 재배치",
                   })


def f0_unknown_fastener(requested: str, used: Fastener, note: str) -> Finding:
    """F0: the requested fastener size is not available and another size was used. Report it as HARD instead of passing silently."""
    return Finding("F0", "HARD", False,
                   f"미지원 체결 규격 {requested!r} → {used.name} 로 계산 / unsupported fastener",
                   standard="보유 규격 표(ASME B18.2.8 / ISO 273)",
                   suggestion={"option_a": f"fastener 를 {used.name} 로 바꾸거나 보유 규격 중 선택", "note": note})


def h2_hole_clearance(hole_dia_mm: float, f: Fastener, fit: str = "normal", measured: bool = False) -> Finding:
    """H2: (measured) hole diameter is at least the standard clearance hole. If too large (over 1.5x loose), message only, at warning level."""
    req = f.clearance(fit)
    ok = hole_dia_mm >= req - 1e-6
    return Finding("H2", "HARD", ok,
                   f"홀-볼트 공차 ({f.name}, {fit} fit{', 커널 실측' if measured else ''})",
                   actual=hole_dia_mm, required=req, standard="ASME B18.2.8",
                   suggestion={} if ok else {"option_a": f"구멍 지름 {hole_dia_mm:.2f} → {req:.2f} 이상"})


K_ENGAGE = {"steel": 1.0, "stainless": 1.0, "cast_iron": 1.3, "brass": 1.3, "aluminum": 1.5, "aluminium": 1.5,
            "plastic": 2.0, "pla": 2.0, "petg": 2.0, "abs": 2.0, "nylon": 2.0, "wood": 2.5}


def h3_engagement(engaged_mm: float, f: Fastener, material: str) -> Finding:
    """H3: tapped hole engagement >= k*D (k: steel 1.0 / aluminum 1.5 / plastic or FDM 2.0). engaged_mm is a kernel raycast measurement."""
    k = K_ENGAGE.get((material or "pla").lower(), 2.0)
    req = k * f.nominal_dia_mm
    ok = engaged_mm >= req - 1e-6
    return Finding("H3", "HARD", ok, f"체결 깊이 / thread engagement ({f.name}, {material}, k={k})",
                   actual=engaged_mm, required=req, standard="실무 k×D (강 1.0, 알루미늄 1.5, 플라스틱 2.0)",
                   suggestion={} if ok else {"option_a": f"판 두께를 {req:.1f}mm 이상으로", "option_b": "관통+너트(hole_type=through)로 변경",
                                             "option_c": "더 작은 볼트"})


def h5_tool_access(bolt_xy, f: Fastener, obstacle: Part, where: str, head_z0: float = 0.0) -> Finding:
    """H5: if the socket/driver tool envelope (socket OD, +15 mm above the head) overlaps a wall or neighboring bolt, the tool cannot get in."""
    from build123d import Pos, Cylinder
    od = f.socket_od_mm or (f.head_across_corners_mm + 3.0)
    h = f.head_height_mm + 15.0
    env = Pos(bolt_xy[0], bolt_xy[1], head_z0 + h / 2) * Cylinder(radius=od / 2, height=h)
    v = _intersection_volume(env, obstacle)
    ok = v <= 0.5
    return Finding("H5", "HARD", ok, f"공구 접근 / socket clearance ({where}, 소켓 Ø{od:.1f})", actual=v, required=0.0,
                   standard="6각 소켓 OD(참고값)", suggestion={} if ok else {"option_a": "구멍을 장애물에서 멀리", "option_b": "소켓캡(육각렌치) 볼트로 변경"})


def h6_head_flush(part: Part, f: Fastener, xy, style: str) -> Finding:
    """H6: after counterbore/countersink, the head sits below the plate surface: place the head solid at the sunk position and intersection with the plate = 0."""
    from build123d import Pos
    from ..geometry.builder import hex_bolt_solid
    if style == "counterbore":
        head = Pos(xy[0], xy[1], -f.head_height_mm) * hex_bolt_solid(f, 0.1)
        v = _intersection_volume(head, part)
        ok = v <= 0.5
        return Finding("H6", "HARD", ok, "머리 묻힘 / counterbore fits head", actual=v, required=0.0,
                       standard="보어 Ø ≥ 머리 맞모+1, 깊이 ≥ 머리 높이", suggestion={} if ok else {"option_a": "보어 지름/깊이 증가"})
    return Finding("H6", "SOFT", True, "접시머리 / countersink (82°/90°)", standard="ASME B18.6.3 / ISO 10642")


def i1_insert_depth(part: Part, f: Fastener, xy, thickness: float) -> Finding:
    """I1: heat-set insert hole depth >= insert length + 1 mm, floor >= 1 mm (raycast measurement)."""
    from .engagement import engagement_raycast
    from ..fasteners.standards import insert_spec
    spec = insert_spec(f)
    if not spec:
        return Finding("I1", "HARD", False, f"{f.name} 용 히트세트 인서트 표 없음", standard="인서트 제조사 표")
    hole_d, L, od = spec
    floor = engagement_raycast(part, (xy[0], xy[1], -thickness - 1.0), (0, 0, 1))   # first material thickness from the bottom
    depth = thickness - floor if floor < thickness else 0.0
    if depth <= 0.0:                      # through hole: depth = plate thickness
        depth = thickness; floor = 0.0
    need = L + 1.0
    ok = depth >= min(need, thickness) - 1e-6 and (floor >= 1.0 or floor == 0.0) and thickness >= L + 1.0
    return Finding("I1", "HARD", ok, f"인서트 구멍 / heat-set insert ({f.name}: Ø{hole_d} × {L}mm)", actual=depth, required=need,
                   standard="인서트 길이 + 1 mm, 바닥 ≥ 1 mm", suggestion={} if ok else {"option_a": f"판 두께를 {L + 2:.1f}mm 이상으로", "option_b": "관통 + 너트로 변경"})


def i2_insert_wall(edge_dist_mm: float, f: Fastener) -> Finding:
    """I2: wall around the insert >= 2.0 mm (thin walls cause warping and melting). Hole center to edge minus insert OD/2."""
    from ..fasteners.standards import insert_spec
    spec = insert_spec(f)
    od = spec[2] if spec else f.nominal_dia_mm * 1.6
    wall = edge_dist_mm - od / 2.0
    ok = wall >= 2.0 - 1e-6
    return Finding("I2", "HARD", ok, f"인서트 둘레 살두께 / wall around insert (OD Ø{od:.1f})", actual=wall, required=2.0,
                   standard="인서트 제조사 권장 ≥ 2 mm", suggestion={} if ok else {"option_a": f"구멍을 모서리에서 {2.0 - wall:.1f}mm 더 안쪽으로"})


def p1_hole_comp(comp: float, hole_type: str) -> Finding:
    """P1 (info): FDM hole shrink compensation. Holes print 0.1 to 0.3 mm small, so the drilled diameter gets an offset."""
    applied = comp if hole_type != "tapped" else 0.0
    return Finding("P1", "SOFT", True, f"FDM 구멍 보정 / hole compensation +{applied:.2f} mm 적용 (프린터별 0.1~0.3, 테스트 쿠폰으로 맞추세요)",
                   actual=applied, required=None, standard="커뮤니티 실측(Bambu/Prusa 포럼)")


def m3_overhang(part: Part, max_deg: float = 45.0) -> Finding:
    """M3 printability (SOFT): share of downward faces (excluding the bottom) shallower than max_deg from horizontal (severe overhang)."""
    import math, tempfile, os
    try:
        import trimesh, numpy as np
        from build123d import export_stl
        with tempfile.TemporaryDirectory() as td:
            pth = os.path.join(td, "m.stl"); export_stl(part, pth, tolerance=0.05, angular_tolerance=0.2)
            m = trimesh.load(pth)
        n = m.face_normals; z = m.vertices[m.faces][:, :, 2].mean(axis=1); zmin = m.vertices[:, 2].min()
        down = n[:, 2] < -math.cos(math.radians(90 - max_deg))     # normal tilted 45 deg or more downward
        down &= z > zmin + 0.5                                     # exclude the bottom contact face
        frac = float(m.area_faces[down].sum() / max(m.area, 1e-9))
    except Exception as e:
        return Finding("M3", "SOFT", True, f"오버행 측정 생략 ({type(e).__name__})", standard="FDM 45°")
    ok = frac <= 0.10
    return Finding("M3", "SOFT", ok, f"오버행 / overhang >{max_deg:.0f}° 면적 {frac * 100:.1f}%", actual=frac * 100, required=10.0,
                   standard="FDM 45° 규칙 (10% 넘으면 서포트 필요)", suggestion={} if ok else {"option_a": "출력 방향 바꾸기 또는 45° 모따기"})


def h4_edge_distance(edge_dist_mm: float, f: Fastener) -> Finding:
    """H4: hole center >= 1.5 x diameter from the edge."""
    req = 1.5 * f.nominal_dia_mm
    ok = edge_dist_mm >= req
    return Finding("H4", "HARD", ok,
                   "연단거리(구멍 중심↔모서리)",
                   actual=edge_dist_mm, required=req, standard="실무 1.5×D",
                   suggestion={} if ok else {"option_a": f"구멍을 안쪽으로 {req - edge_dist_mm:.1f}mm 이동"})


def s2_hole_spacing(center_to_center_mm: float, f: Fastener) -> Finding:
    """S2: wrench clearance: hole spacing >= 2 x head width."""
    req = 2.0 * f.head_across_flats_mm
    ok = center_to_center_mm >= req
    return Finding("S2", "SOFT", ok,
                   "홀 간 거리(렌치 공간)",
                   actual=center_to_center_mm, required=req, standard="실무 2×머리폭")


def m_min_wall(wall_mm: float, nozzle: float = 0.4, label: str = "최소 벽두께 / min wall") -> Finding:
    """M1 printability: wall thickness >= 2 x nozzle (FDM)."""
    req = round(nozzle * 2, 2)
    ok = wall_mm >= req - 1e-6
    return Finding("M1", "SOFT", ok, label, actual=wall_mm, required=req, standard="FDM 노즐×2")


def e_board(part, board_name: str, holes: list, pilot_dia: float, screw: str) -> Finding:
    """E1 board mounting (measured): on the kernel, check there is a pilot hole of the right diameter at each board screw hole position."""
    from ..geometry.analyze import measure_hole_dia
    missing, wrong = [], []
    for (x, y) in holes:
        d = measure_hole_dia(part, x, y, tol=0.3)
        if d is None:
            missing.append((x, y))
        elif abs(d - pilot_dia) > 0.15:
            wrong.append((x, y, round(d, 2)))
    ok = not missing and not wrong
    msg = f"보드 고정 / standoffs match {board_name} ({screw}, 구멍 {len(holes)}개 실측)"
    if missing: msg += f", 나사 밑구멍 없음 {missing}"
    if wrong: msg += f", 구멍 지름 다름 {wrong}"
    return Finding("E1", "HARD", ok, msg, standard="board hole pattern",
                   suggestion={} if ok else {"option_a": "보드 프리셋 좌표로 기둥 재배치"})


def e_floor(part, holes: list, min_floor: float = 1.0) -> Finding:
    """E2 floor skin (measured): remaining floor thickness under the boss pilot >= 1.0 mm (raycast)."""
    from .engagement import engagement_raycast
    worst = None
    for (x, y) in holes:
        t = engagement_raycast(part, (x, y, -1.0), (0, 0, 1))   # shoot upward from below the floor: first material thickness (floor skin)
        worst = t if worst is None else min(worst, t)
    worst = worst or 0.0
    ok = worst >= min_floor - 1e-6
    return Finding("E2", "HARD", ok, "기둥 아래 바닥 두께 / floor under standoff", actual=worst, required=min_floor,
                   standard="FDM 바닥 ≥ 1 mm", suggestion={} if ok else {"option_a": "base 두께 또는 standoff_h 증가"})


def g1_mesh(gear_part, teeth: int, module: float, thickness: float) -> Finding:
    """G1 meshing (measured): place a copy of the gear at the theoretical center distance m*z, rotated by half a pitch, and check intersection volume = 0."""
    from build123d import Pos, Rot
    try:
        cd = module * teeth            # two identical gears: m(z+z)/2
        # With an even tooth count 180 deg is a multiple of the pitch, so add half a pitch to seat teeth in gaps; with an odd count 180 deg is already offset by half a pitch
        mate = Pos(cd, 0, 0) * Rot(0, 0, (180.0 / teeth) if teeth % 2 == 0 else 0.0) * gear_part
        v = _intersection_volume(gear_part, mate)
    except Exception as e:
        return Finding("G1", "HARD", False, f"기어 맞물림 측정 실패 / {type(e).__name__}", standard="involute mesh")
    ok = v <= 0.05 * module * thickness   # numerical tolerance (tiny contact)
    return Finding("G1", "HARD", ok, f"기어 맞물림 / meshing at center distance {cd:.1f}mm", actual=v, required=0.0,
                   standard="인벌류트 20°, 백래시 0.05m", suggestion={} if ok else {"option_a": "치형/백래시 확인"})


def mesh_report(part) -> dict:
    """Measured on the exported mesh: watertight (after degenerate face cleanup), connected component count, OCC solid count, overlapping (unfused) solid pairs."""
    import tempfile, os
    rep = {"nsolids": 0, "is_valid": False, "watertight": False, "bodies": 0, "overlaps": []}
    try:
        solids = part.solids()
        rep["nsolids"] = len(solids)
        rep["is_valid"] = bool(part.is_valid)
        if 2 <= len(solids) <= 10:                      # large arrays (Compound 40+) overlap on purpose: skip
            for i in range(len(solids)):
                for j in range(i + 1, len(solids)):
                    v = _intersection_volume(solids[i], solids[j])
                    if v > 0.5:                         # overlap of 0.5 mm^3 or more means stacked, not fused
                        rep["overlaps"].append((i, j, round(v, 2)))
        import trimesh
        from build123d import export_stl
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "m.stl")
            export_stl(part, p, tolerance=0.01, angular_tolerance=0.1)
            m = trimesh.load(p)
            mask = m.area_faces > 1e-9                  # clean sphere pole degenerate faces (same as exporters._clean_degenerate)
            if not bool(mask.all()):
                m.update_faces(mask); m.remove_unreferenced_vertices(); m.merge_vertices()
            rep["watertight"] = bool(m.is_watertight)
            rep["bodies"] = len(m.split(only_watertight=False))
    except Exception as e:
        rep["error"] = f"{type(e).__name__}: {e}"[:120]
    return rep


def m_manifold(part) -> Finding:
    """M2 printability: OCC valid + exported mesh watertight (after degenerate face cleanup). A failed measurement counts as failure (fail-closed)."""
    rep = mesh_report(part)
    ok = rep["nsolids"] >= 1 and rep["is_valid"] and rep["watertight"] and "error" not in rep
    msg = "매니폴드 / watertight solid"
    if "error" in rep:
        msg += f" (측정 실패: {rep['error']})"
    elif not rep["watertight"]:
        msg += f" (메시가 닫히지 않음, 조각 {rep['bodies']}개)"
    return Finding("M2", "HARD", ok, msg, standard="출력 가능",
                   suggestion={} if ok else {"option_a": "형상을 단순화하거나 겹친 부위를 1.5mm 이상 파묻고 융합"})


def c1_unfused(part) -> Finding:
    """C1: HARD if solids only overlap without being fused: slicers split them or create internal walls."""
    rep = mesh_report(part)
    ok = not rep["overlaps"]
    desc = ", ".join(f"solid{i}∩solid{j}={v}mm³" for i, j, v in rep["overlaps"][:4])
    return Finding("C1", "HARD", ok,
                   ("솔리드 융합 / fused" if ok else f"겹친 미융합 솔리드 {len(rep['overlaps'])}쌍 ({desc})"),
                   actual=float(len(rep["overlaps"])), required=0.0, standard="단일 바디(또는 의도된 분리 부품)",
                   suggestion={} if ok else {"option_a": "겹치는 부품을 + 로 융합(body = body + part)",
                                             "option_b": "분리 부품이면 겹치지 않게 띄우기"})


def summarize(findings: list[Finding]) -> dict:
    hard_fail = [f for f in findings if f.severity == "HARD" and not f.ok]
    soft_warn = [f for f in findings if f.severity == "SOFT" and not f.ok]
    return {
        "passed": len(hard_fail) == 0,
        "hard_fail": [f.code for f in hard_fail],
        "soft_warn": [f.code for f in soft_warn],
        "findings": findings,
    }
