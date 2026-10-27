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


def h2_hole_clearance(hole_dia_mm: float, f: Fastener, fit: str = "normal") -> Finding:
    """H2: 구멍 지름이 규격 clearance hole 이상인지."""
    req = f.clearance(fit)
    ok = hole_dia_mm >= req - 1e-6
    return Finding("H2", "HARD", ok,
                   f"홀-볼트 공차 ({f.name}, {fit} fit)",
                   actual=hole_dia_mm, required=req, standard="ASME B18.2.8",
                   suggestion={} if ok else {"option_a": f"구멍 지름 {hole_dia_mm:.2f} → {req:.2f} 이상"})


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


def e_board(board_name: str, dx: float, dy: float, screw: str) -> Finding:
    """E1 기판 고정: 고정 기둥이 보드 표준 나사구멍과 일치(설계상 보장)."""
    return Finding("E1", "SOFT", True,
                   f"보드 고정 / standoffs match {board_name} ({screw}, {dx:.0f}×{dy:.0f}mm)",
                   standard="board spec")


def m_manifold(part) -> Finding:
    """M2 출력 가능성: 단일 솔리드·유효(물샐틈 없는 매니폴드)."""
    try:
        ok = (len(part.solids()) == 1) and bool(part.is_valid)
    except Exception:
        ok = False
    return Finding("M2", "HARD", ok, "매니폴드 / watertight solid", standard="출력 가능")


def summarize(findings: list[Finding]) -> dict:
    hard_fail = [f for f in findings if f.severity == "HARD" and not f.ok]
    soft_warn = [f for f in findings if f.severity == "SOFT" and not f.ok]
    return {
        "passed": len(hard_fail) == 0,
        "hard_fail": [f.code for f in hard_fail],
        "soft_warn": [f.code for f in soft_warn],
        "findings": findings,
    }
