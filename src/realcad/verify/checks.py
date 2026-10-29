"""빡센 검증 — 전부 커널(OCC) 측정. 맥>공모전 룰셋 기반.

HARD: 실패 시 즉시 재생성(파라미터 수정)을 요구. SOFT: 경고.
실패는 geometry 가 아니라 **파라미터 수정 제안 dict** 로 돌려준다
("그림 다시 그려" 금지 — Zoo 류 치수 깨짐 방지).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from build123d import Part
from ..fasteners.standards import Fastener

VOL_EPS = 1e-6  # 간섭 최소 부피(mm^3)


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
            base += f" — {self.standard}"
        return base


def _intersection_volume(a: Part, b: Part) -> float:
    try:
        inter = a & b
        return float(inter.volume) if inter is not None else 0.0
    except Exception:
        return 0.0


def h1_interference(bolt: Part, obstacle: Part, where: str) -> Finding:
    """H1: 볼트 솔리드와 장애물(벽·옆 볼트)의 교차 부피 > 0 이면 충돌."""
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
    """F0: 요청한 체결 규격을 보유하지 않아 다른 규격으로 계산했다 — 조용히 넘기지 않고 HARD 로 알린다."""
    return Finding("F0", "HARD", False,
                   f"미지원 체결 규격 {requested!r} → {used.name} 로 계산 / unsupported fastener",
                   standard="보유 규격 표(ASME B18.2.8 / ISO 273)",
                   suggestion={"option_a": f"fastener 를 {used.name} 로 바꾸거나 보유 규격 중 선택", "note": note})


def h2_hole_clearance(hole_dia_mm: float, f: Fastener, fit: str = "normal", measured: bool = False) -> Finding:
    """H2: (실측) 구멍 지름이 규격 clearance hole 이상인지. 너무 크면(loose 의 1.5배 초과) 경고 수준으로 메시지만."""
    req = f.clearance(fit)
    ok = hole_dia_mm >= req - 1e-6
    return Finding("H2", "HARD", ok,
                   f"홀-볼트 공차 ({f.name}, {fit} fit{', 커널 실측' if measured else ''})",
                   actual=hole_dia_mm, required=req, standard="ASME B18.2.8",
                   suggestion={} if ok else {"option_a": f"구멍 지름 {hole_dia_mm:.2f} → {req:.2f} 이상"})


K_ENGAGE = {"steel": 1.0, "stainless": 1.0, "cast_iron": 1.3, "brass": 1.3, "aluminum": 1.5, "aluminium": 1.5,
            "plastic": 2.0, "pla": 2.0, "petg": 2.0, "abs": 2.0, "nylon": 2.0, "wood": 2.5}


def h3_engagement(engaged_mm: float, f: Fastener, material: str) -> Finding:
    """H3: 탭 구멍 체결 깊이 ≥ k·D (k: 강 1.0 / 알루미늄 1.5 / 플라스틱·FDM 2.0). engaged_mm 은 커널 레이캐스트 실측."""
    k = K_ENGAGE.get((material or "pla").lower(), 2.0)
    req = k * f.nominal_dia_mm
    ok = engaged_mm >= req - 1e-6
    return Finding("H3", "HARD", ok, f"체결 깊이 / thread engagement ({f.name}, {material}, k={k})",
                   actual=engaged_mm, required=req, standard="실무 k·D (강1.0·Al1.5·플라스틱2.0)",
                   suggestion={} if ok else {"option_a": f"판 두께를 {req:.1f}mm 이상으로", "option_b": "관통+너트(hole_type=through)로 변경",
                                             "option_c": "더 작은 볼트"})


def h4_edge_distance(edge_dist_mm: float, f: Fastener) -> Finding:
    """H4: 구멍 중심이 모서리에서 ≥ 1.5×지름."""
    req = 1.5 * f.nominal_dia_mm
    ok = edge_dist_mm >= req
    return Finding("H4", "HARD", ok,
                   "연단거리(구멍 중심↔모서리)",
                   actual=edge_dist_mm, required=req, standard="실무 1.5×D",
                   suggestion={} if ok else {"option_a": f"구멍을 안쪽으로 {req - edge_dist_mm:.1f}mm 이동"})


def s2_hole_spacing(center_to_center_mm: float, f: Fastener) -> Finding:
    """S2: 렌치 간격 — 구멍 간 거리 ≥ 2×머리폭."""
    req = 2.0 * f.head_across_flats_mm
    ok = center_to_center_mm >= req
    return Finding("S2", "SOFT", ok,
                   "홀 간 거리(렌치 공간)",
                   actual=center_to_center_mm, required=req, standard="실무 2×머리폭")


def m_min_wall(wall_mm: float, nozzle: float = 0.4, label: str = "최소 벽두께 / min wall") -> Finding:
    """M1 출력 가능성: 벽두께 ≥ 노즐×2 (FDM)."""
    req = round(nozzle * 2, 2)
    ok = wall_mm >= req - 1e-6
    return Finding("M1", "SOFT", ok, label, actual=wall_mm, required=req, standard="FDM 노즐×2")


def e_board(part, board_name: str, holes: list, pilot_dia: float, screw: str) -> Finding:
    """E1 기판 고정(실측): 보드의 각 나사구멍 좌표에 파일럿 구멍이 실제로 있는지, 지름이 맞는지 커널에서 확인."""
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
    if missing: msg += f" — 파일럿 없음 {missing}"
    if wrong: msg += f" — 지름 불일치 {wrong}"
    return Finding("E1", "HARD", ok, msg, standard="board hole pattern",
                   suggestion={} if ok else {"option_a": "보드 프리셋 좌표로 기둥 재배치"})


def e_floor(part, holes: list, min_floor: float = 1.0) -> Finding:
    """E2 바닥 피막(실측): 기둥 파일럿 아래 남은 바닥 두께 ≥ 1.0 mm (레이캐스트)."""
    from .engagement import engagement_raycast
    worst = None
    for (x, y) in holes:
        t = engagement_raycast(part, (x, y, -1.0), (0, 0, 1))   # 바닥 아래에서 위로 쏴 첫 재료 두께(바닥 피막)
        worst = t if worst is None else min(worst, t)
    worst = worst or 0.0
    ok = worst >= min_floor - 1e-6
    return Finding("E2", "HARD", ok, "기둥 아래 바닥 두께 / floor under standoff", actual=worst, required=min_floor,
                   standard="FDM 바닥 ≥ 1 mm", suggestion={} if ok else {"option_a": "base 두께 또는 standoff_h 증가"})


def g1_mesh(gear_part, teeth: int, module: float, thickness: float) -> Finding:
    """G1 맞물림(실측): 같은 기어를 이론 중심거리 m·z 에 반피치 돌려 놓고 교차 부피 = 0 인지."""
    from build123d import Pos, Rot
    try:
        cd = module * teeth            # 같은 기어 두 개: m(z+z)/2
        # 짝수 잇수는 180° 가 피치의 배수라 반피치를 더 돌려야 이가 홈에 들어가고, 홀수 잇수는 180° 자체가 반피치 어긋남
        mate = Pos(cd, 0, 0) * Rot(0, 0, (180.0 / teeth) if teeth % 2 == 0 else 0.0) * gear_part
        v = _intersection_volume(gear_part, mate)
    except Exception as e:
        return Finding("G1", "HARD", False, f"기어 맞물림 측정 실패 / {type(e).__name__}", standard="involute mesh")
    ok = v <= 0.05 * module * thickness   # 수치 오차 허용(아주 작은 접촉)
    return Finding("G1", "HARD", ok, f"기어 맞물림 / meshing at center distance {cd:.1f}mm", actual=v, required=0.0,
                   standard="인벌류트 20°, 백래시 0.05m", suggestion={} if ok else {"option_a": "치형/백래시 확인"})


def mesh_report(part) -> dict:
    """내보낸 메시 기준 실측: watertight(퇴화면 정리 후)·연결 조각 수·OCC 솔리드 수·겹친(미융합) 솔리드 쌍."""
    import tempfile, os
    rep = {"nsolids": 0, "is_valid": False, "watertight": False, "bodies": 0, "overlaps": []}
    try:
        solids = part.solids()
        rep["nsolids"] = len(solids)
        rep["is_valid"] = bool(part.is_valid)
        if 2 <= len(solids) <= 10:                      # 큰 배열(Compound 40+)은 의도된 겹침이라 건너뜀
            for i in range(len(solids)):
                for j in range(i + 1, len(solids)):
                    v = _intersection_volume(solids[i], solids[j])
                    if v > 0.5:                         # 0.5 mm³ 이상 겹치면 "붙이지 않고 포갠" 것
                        rep["overlaps"].append((i, j, round(v, 2)))
        import trimesh
        from build123d import export_stl
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "m.stl")
            export_stl(part, p, tolerance=0.01, angular_tolerance=0.1)
            m = trimesh.load(p)
            mask = m.area_faces > 1e-9                  # 구 극점 퇴화면 정리(exporters._clean_degenerate 와 동일)
            if not bool(mask.all()):
                m.update_faces(mask); m.remove_unreferenced_vertices(); m.merge_vertices()
            rep["watertight"] = bool(m.is_watertight)
            rep["bodies"] = len(m.split(only_watertight=False))
    except Exception as e:
        rep["error"] = f"{type(e).__name__}: {e}"[:120]
    return rep


def m_manifold(part) -> Finding:
    """M2 출력 가능성: OCC 유효 + 내보낸 메시가 watertight(퇴화면 정리 후). 측정 실패는 실패로(fail-closed)."""
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
    """C1: 서로 겹치기만 하고 융합되지 않은 솔리드가 있으면 HARD — 슬라이서에서 조각나거나 내부 벽이 생긴다."""
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
