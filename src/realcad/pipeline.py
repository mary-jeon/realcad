"""Contract -> assembly + verification (branches by kind). Shared by the agent loop and the web server."""
from __future__ import annotations
from .contract.schema import DesignContract
from .geometry.builder import build_from_contract, wall as make_wall, place, hex_bolt_solid
from .verify import checks as v


def build_and_verify(c: DesignContract):
    """return (part, fastener|None, hole_dia|None, findings, summary)."""
    if c.kind == "assembly":
        # Assembly: build per-part solids in assembly coordinates, check A1~A6 plus per-part M2. Single-part C1/M3 are skipped (parts are intentionally separate).
        from .mech import build_assembly
        from .verify.assembly import verify_assembly
        asm = build_assembly(c.assembly)
        findings = verify_assembly(asm, c)
        part = asm.compound
        part._rc_asm = asm                      # for the web response (per-part STL, BOM, mates)
        return part, None, None, findings, v.summarize(findings)
    part, f, dia = build_from_contract(c)
    findings = []

    if c.kind == "plate":
        L, W = c.plate.length, c.plate.width
        if not getattr(c, "fastener_exact", True):
            findings.append(v.f0_unknown_fastener(c.fastener, f, getattr(c, "fastener_note", "")))
        from .geometry.analyze import measure_hole_dia
        wall_solid = (make_wall(c.wall.x, W, c.wall.height, c.wall.thickness)
                      if c.wall else None)
        bolts = []
        tapped = getattr(c, "hole_type", "through") == "tapped"
        if tapped:
            from .verify.engagement import engagement_raycast
        for i, h in enumerate(c.holes, 1):
            md = measure_hole_dia(part, h.x, h.y)                 # measure the actual hole diameter in the kernel
            if getattr(c, "hole_type", "through") == "insert":
                pass                                               # inserts are checked with I1 (not a clearance hole)
            elif tapped:
                # tapped hole: raycast the bolt axis into the plate to measure the actual engaged length (plate thickness minus walls, etc.)
                # The axis is inside the hole (empty) and reads 0, so cast at the thread engagement radius (0.47D, outside the tap drill, inside the major diameter)
                rr = 0.47 * f.nominal_dia_mm
                eng = max(engagement_raycast(part, (h.x + rr, h.y, 50.0), (0, 0, -1)),
                          engagement_raycast(part, (h.x - rr, h.y, 50.0), (0, 0, -1)))
                findings.append(v.h3_engagement(eng, f, getattr(c, "material", "pla")))
            else:
                findings.append(v.h2_hole_clearance(md if md is not None else 0.0, f, c.fit, measured=True))
            b = place(hex_bolt_solid(f, 20), h.x, h.y)
            bolts.append(b)
            if wall_solid is not None:
                findings.append(v.h1_interference(b, wall_solid, f"hole{i}-wall"))
                findings.append(v.h5_tool_access((h.x, h.y), f, wall_solid, f"hole{i}-wall"))
            style = getattr(c, "hole_style", "plain")
            if style in ("counterbore", "countersink"):
                findings.append(v.h6_head_flush(part, f, (h.x, h.y), style))
            if getattr(c, "hole_type", "through") == "insert":
                findings.append(v.i1_insert_depth(part, f, (h.x, h.y), c.plate.thickness))
                findings.append(v.i2_insert_wall(min(L / 2 - h.x, L / 2 + h.x, W / 2 - h.y, W / 2 + h.y), f))
            ed = min(L / 2 - h.x, L / 2 + h.x, W / 2 - h.y, W / 2 + h.y)
            findings.append(v.h4_edge_distance(ed, f))
        for i in range(len(bolts)):
            for j in range(i + 1, len(bolts)):
                findings.append(v.h1_interference(bolts[i], bolts[j], f"hole{i+1}-hole{j+1}"))
                hi, hj = c.holes[i], c.holes[j]
                findings.append(v.s2_hole_spacing(((hi.x - hj.x) ** 2 + (hi.y - hj.y) ** 2) ** 0.5, f))
        findings.append(v.m_min_wall(c.plate.thickness, label="판 두께 / plate thickness", nozzle=getattr(c, "nozzle", 0.4)))
        findings.append(v.p1_hole_comp(getattr(c, "hole_comp", 0.0), getattr(c, "hole_type", "through")))

    elif c.kind == "container":
        cc = c.container
        findings.append(v.m_min_wall(cc.wall, label="용기 벽두께 / wall", nozzle=getattr(c, "nozzle", 0.4)))
        findings.append(v.m_min_wall(cc.base, label="바닥 두께 / base", nozzle=getattr(c, "nozzle", 0.4)))

    elif c.kind == "gear":
        findings.append(v.m_min_wall(c.gear.module, label="이뿌리 두께 / tooth (≈module)", nozzle=getattr(c, "nozzle", 0.4)))
        findings.append(v.g1_mesh(part, max(int(c.gear.teeth), 6), c.gear.module, c.gear.thickness))

    elif c.kind == "enclosure":
        from .geometry.builder import board_spec
        e = c.enclosure
        b = board_spec(e.board, e)
        if b["holes"]:
            findings.append(v.e_board(part, e.board, b["holes"], b["pilot"], b["screw"]))
            findings.append(v.e_floor(part, b["holes"]))
        if e.open_ports:
            findings.append(v.e_ports(part, e, b) if b.get("ports") else v.e_ports_unknown())
        findings.append(v.m_min_wall(e.wall, label="벽 두께 / wall", nozzle=getattr(c, "nozzle", 0.4)))
        findings.append(v.m_min_wall(e.base, label="바닥 두께 / base", nozzle=getattr(c, "nozzle", 0.4)))

    elif c.kind == "profile":
        findings.append(v.m_min_wall(c.profile.thickness, label="두께 / thickness", nozzle=getattr(c, "nozzle", 0.4)))

    elif c.kind == "clamp":
        findings.append(v.m_min_wall(c.clamp.wall, label="클립 살두께 / clip wall", nozzle=getattr(c, "nozzle", 0.4)))

    elif c.kind == "ball":
        findings.append(v.m_min_wall(c.ball.wall, label="쉘 두께 / shell wall", nozzle=getattr(c, "nozzle", 0.4)))

    findings.append(v.m_manifold(part))
    findings.append(v.c1_unfused(part))
    findings.append(v.m3_overhang(part))
    return part, f, dia, findings, v.summarize(findings)
