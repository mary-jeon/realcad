"""계약 → 조립 + 검증 (kind별 분기). meta_run·loop·web 공용."""
from __future__ import annotations
from .contract.schema import DesignContract
from .geometry.builder import build_from_contract, wall as make_wall, place, hex_bolt_solid
from .verify import checks as v


def build_and_verify(c: DesignContract):
    """return (part, fastener|None, hole_dia|None, findings, summary)."""
    part, f, dia = build_from_contract(c)
    findings = []

    if c.kind == "plate":
        L, W = c.plate.length, c.plate.width
        findings.append(v.h2_hole_clearance(dia, f, c.fit))
        wall_solid = (make_wall(c.wall.x, W, c.wall.height, c.wall.thickness)
                      if c.wall else None)
        bolts = []
        for i, h in enumerate(c.holes, 1):
            b = place(hex_bolt_solid(f, 20), h.x, h.y)
            bolts.append(b)
            if wall_solid is not None:
                findings.append(v.h1_interference(b, wall_solid, f"hole{i}-wall"))
            ed = min(L / 2 - h.x, L / 2 + h.x, W / 2 - h.y, W / 2 + h.y)
            findings.append(v.h4_edge_distance(ed, f))
        for i in range(len(bolts)):
            for j in range(i + 1, len(bolts)):
                findings.append(v.h1_interference(bolts[i], bolts[j], f"hole{i+1}-hole{j+1}"))
        findings.append(v.m_min_wall(c.plate.thickness, label="판 두께 / plate thickness"))

    elif c.kind == "container":
        cc = c.container
        findings.append(v.m_min_wall(cc.wall, label="용기 벽두께 / wall"))
        findings.append(v.m_min_wall(cc.base, label="바닥 두께 / base"))

    elif c.kind == "gear":
        findings.append(v.m_min_wall(c.gear.module, label="이뿌리 두께 / tooth (≈module)"))

    elif c.kind == "enclosure":
        from .geometry.builder import board_spec
        e = c.enclosure
        b = board_spec(e.board)
        findings.append(v.e_board(e.board, b["dx"], b["dy"], b["screw"]))
        findings.append(v.m_min_wall(e.wall, label="벽 두께 / wall"))
        findings.append(v.m_min_wall(e.base, label="바닥 두께 / base"))

    elif c.kind == "profile":
        findings.append(v.m_min_wall(c.profile.thickness, label="두께 / thickness"))

    elif c.kind == "clamp":
        findings.append(v.m_min_wall(c.clamp.wall, label="클립 살두께 / clip wall"))

    elif c.kind == "ball":
        findings.append(v.m_min_wall(c.ball.wall, label="쉘 두께 / shell wall"))

    findings.append(v.m_manifold(part))
    return part, f, dia, findings, v.summarize(findings)
