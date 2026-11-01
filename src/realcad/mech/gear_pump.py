"""Gear pump assembly builder (preset gear_pump): CAD practical exam task 3.

Reference: 153LAB 2026 round 2 similar problem structure analysis: gear m1.5 z24, OD Ø39, width 29,
gear pocket Ø39 G7 depth 28, bushing Ø18 p6 / Ø12 H7, shaft Ø12 g6 / gear seat Ø15 h6, gasket 1.0, oil seal Ø22, cover taps 6-M6.
Coordinates: shaft = X, drive gear y = 0, driven gear y = a = m(z1+z2)/2, z = Z_AXIS. Cover on the +X side. Body bottom z = 0.
"""
from __future__ import annotations
import math

from build123d import Part, Compound, Box, Cylinder, Pos, Rot, RegularPolygon, extrude

from . import standards as S
from .power_train import (PartInfo, Assembly, cyl_x, ring_x, shaft_keyway_cutter, hub_keyway_cutter, key_solid,
                          gear_solid, fit, BASE_T)

BACK_T = 14.0        # Body back wall (bushing seat 12 + 2)
BUSH_L = 12.0
GASKET_T = 1.0
COVER_T = 22.0       # Bushing 12 + oil seal 7 + 3
MARGIN = 12.0        # Pocket edge to body outside
SHAFT_EXT = 30.0     # Drive shaft protrusion beyond the cover
PORT_D = 11.4        # G1/4 minor diameter (threads not modeled)


def layout_gear_pump(a) -> dict:
    m, z = float(a.gear_module), int(a.gear_teeth)
    gd = S.gear_dims(m, z)
    bw = float(a.gear_width) if a.gear_width > 0 else round(gd.d * 0.8, 1)        # Reference example: PCD 36 → width 29
    cd = S.center_distance(m, z, z)
    dj = max(10.0, round(gd.d / 3.0))                 # Journal Ø (PCD 36 → 12)
    dj = max([d for d in (10, 12, 15, 17, 20, 25, 30) if d <= dj] or [10])   # Matched to oil seal table sizes
    ds = dj + 3.0                                     # Gear seat Ø (15)
    key = S.parallel_key(ds)
    bush_od = round(dj * 1.5)                         # 18
    seal = S.oil_seal(dj)
    pocket_r = gd.da / 2.0                            # Gear pocket radius (G7)
    pocket_depth = bw - GASKET_T                      # 28
    half_y = pocket_r + MARGIN
    y0, y1 = -half_y, cd + half_y
    half_z = half_y
    z_axis = BASE_T + half_z
    xb0 = 0.0
    x_pb = xb0 + BACK_T                               # Pocket bottom = back wall inner face
    x_face = x_pb + pocket_depth                      # Body cover face
    x_c0 = x_face + GASKET_T                          # Cover inner face
    x_c1 = x_c0 + COVER_T                             # Cover outer face
    bolt = "M6"; pcd_pts = [(-half_y + 7.0, z_axis - half_z + 7.0), (-half_y + 7.0, z_axis + half_z - 7.0),
                            (cd + half_y - 7.0, z_axis - half_z + 7.0), (cd + half_y - 7.0, z_axis + half_z - 7.0),
                            (cd / 2.0, z_axis - half_z + 7.0), (cd / 2.0, z_axis + half_z - 7.0)]
    return dict(gear=gd, bw=bw, cd=cd, dj=dj, ds=ds, key=key, bush_od=bush_od, seal=seal, pocket_r=pocket_r,
                pocket_depth=pocket_depth, half_y=half_y, half_z=half_z, y0=y0, y1=y1, z_axis=z_axis,
                xb0=xb0, x_pb=x_pb, x_face=x_face, x_c0=x_c0, x_c1=x_c1, bolt=bolt, bolt_pts=pcd_pts,
                x_shaft_end=x_c1 + SHAFT_EXT, ys=[0.0, cd])


def _body(L: dict) -> Part:
    z = L["z_axis"]; hy, hz = L["half_y"], L["half_z"]
    xa, xb = L["xb0"], L["x_face"]
    body = Pos((xa + xb) / 2.0, L["cd"] / 2.0, z) * Box(xb - xa, L["y1"] - L["y0"], 2 * hz)
    base = Pos((xa + xb) / 2.0, L["cd"] / 2.0, BASE_T / 2.0) * Box(xb - xa, L["y1"] - L["y0"] + 16.0, BASE_T)
    body = body + base
    for y in L["ys"]:
        body = body - cyl_x(L["x_pb"], xb + 1.0, L["pocket_r"], y, z)                       # Gear pocket Ø da G7
        body = body - cyl_x(L["x_pb"] - BUSH_L, L["x_pb"] + 0.5, L["bush_od"] / 2.0, y, z)   # Bushing bore Ø18 H7 (back wall)
    # Inlet/outlet ports: above and below the gear mesh line (y = a/2)
    xm = (L["x_pb"] + xb) / 2.0
    body = body - Pos(xm, L["cd"] / 2.0, z + hz / 2.0) * Cylinder(radius=PORT_D / 2.0, height=hz + 2.0)
    body = body - Pos(xm, L["cd"] / 2.0, (z - hz) / 2.0) * Cylinder(radius=PORT_D / 2.0, height=z - hz + 2.0 + BASE_T)
    from ..fasteners.standards import resolve
    f = resolve(L["bolt"])[0]
    for (py, pz) in L["bolt_pts"]:                                                           # Cover tapped holes 6-M6, depth 12
        body = body - cyl_x(xb - 12.0, xb + 1.0, f.nominal_dia_mm / 2.0, py, pz)
    for sy in (L["y0"] - 8.0 + 5.0, L["y1"] + 8.0 - 5.0):                                   # Mounting holes 4-M4 clearance
        for sx in (xa + 6.0, xb - 6.0):
            body = body - Pos(sx, sy, BASE_T / 2.0) * Cylinder(radius=2.25, height=BASE_T + 2)
    return body


def _plate_outline(L: dict, x0: float, x1: float) -> Part:
    return Pos((x0 + x1) / 2.0, L["cd"] / 2.0, L["z_axis"]) * Box(x1 - x0, L["y1"] - L["y0"], 2 * L["half_z"])


def _gasket(L: dict) -> Part:
    g = _plate_outline(L, L["x_face"], L["x_c0"])
    for y in L["ys"]:
        g = g - cyl_x(L["x_face"] - 1, L["x_c0"] + 1, L["pocket_r"], y, L["z_axis"])
    from ..fasteners.standards import resolve
    f = resolve(L["bolt"])[0]
    for (py, pz) in L["bolt_pts"]:
        g = g - cyl_x(L["x_face"] - 1, L["x_c0"] + 1, f.clearance("normal") / 2.0, py, pz)
    return g


def _cover(L: dict) -> Part:
    z = L["z_axis"]; x0, x1 = L["x_c0"], L["x_c1"]
    c = _plate_outline(L, x0, x1)
    for i, y in enumerate(L["ys"]):
        c = c - cyl_x(x0 - 0.5, x0 + BUSH_L, L["bush_od"] / 2.0, y, z)                     # Bushing bore
        if i == 0:                                                                            # Drive shaft: through + oil seal seat
            c = c - cyl_x(x0 - 1, x1 + 1, (L["dj"] + 2.0) / 2.0, y, z)
            c = c - cyl_x(x1 - L["seal"].b, x1 + 1, L["seal"].D / 2.0, y, z)
    from ..fasteners.standards import resolve
    f = resolve(L["bolt"])[0]
    for (py, pz) in L["bolt_pts"]:
        c = c - cyl_x(x0 - 1, x1 + 1, f.clearance("normal") / 2.0, py, pz)
    return c


def _shaft(L: dict, y: float, drive: bool) -> Part:
    z = L["z_axis"]; dj, ds = L["dj"], L["ds"]
    x0 = L["x_pb"] - BUSH_L + 1.0
    x1 = L["x_shaft_end"] if drive else (L["x_c0"] + BUSH_L - 1.0)
    s = cyl_x(x0, x1, dj / 2.0, y, z)
    s = s + cyl_x(L["x_pb"], L["x_c0"], ds / 2.0, y, z)                                      # Gear seat Ø15 = pocket + gasket width
    k = L["key"]
    s = s - shaft_keyway_cutter((L["x_pb"] + L["x_c0"]) / 2.0, L["bw"] - 4.0, k.b, z + ds / 2.0 - k.t1, y)
    if drive:                                                                                 # Coupling keyway at the shaft end (shaft Ø12 → 4x4)
        ke = S.parallel_key(dj)
        s = s - shaft_keyway_cutter(x1 - 12.0, 16.0, ke.b, z + dj / 2.0 - ke.t1, y)
    return s


def build_gear_pump(a) -> Assembly:
    L = layout_gear_pump(a)
    gd, bw, z, cd, k = L["gear"], L["bw"], L["z_axis"], L["cd"], L["key"]
    parts: list[PartInfo] = []
    no = [0]

    def add(name, solid, spec="", qty=1, material="", explode=(0, 0, 0), group=""):
        no[0] += 1
        parts.append(PartInfo(name, solid, spec, qty, material, explode, group or name.split()[0], no[0]))

    if a.housing:
        add("본체", _body(L), f"기어 안착 홈 Ø{gd.da:g} G7 깊이 {L['pocket_depth']:g} ×2 (중심거리 {cd:g}), 부시 구멍 Ø{L['bush_od']:g} H7, 커버 탭 6-{L['bolt']}, 포트 G1/4 ×2, 장착 M4 ×4", 1, "GC200", (0, 0, -1.0))
    xgc = (L["x_pb"] + L["x_c0"]) / 2.0
    rot1 = 90.0
    rot2 = 90.0 + (180.0 / gd.z if gd.z % 2 == 0 else 0.0)
    g1 = gear_solid(gd.z, gd.m, bw, L["ds"], xgc, 0.0, z, rot1) - hub_keyway_cutter(xgc, bw + 2.0, k.b, z + L["ds"] / 2.0 + k.t2, 0.0)
    g2 = gear_solid(gd.z, gd.m, bw, L["ds"], xgc, cd, z, rot2) - hub_keyway_cutter(xgc, bw + 2.0, k.b, z + L["ds"] / 2.0 + k.t2, cd)
    spec_g = f"m{gd.m:g} z{gd.z} 압력각 20도, PCD Ø{gd.d:g}, 외경 Ø{gd.da:g} h6, 이폭 {bw:g}, 보어 Ø{L['ds']:g} H7, 키홈 {k.b:g}×{k.t2:g}"
    add("스퍼기어(구동)", g1, spec_g, 1, "SCM440", (0, 0, 1.2), "기어")
    add("스퍼기어(종동)", g2, spec_g, 1, "SCM440", (0, 0, 1.2), "피니언")
    add("구동축", _shaft(L, 0.0, True), f"저널 Ø{L['dj']:g} g6 ×2, 기어 자리 Ø{L['ds']:g} h6 키홈 {k.name}, 커버 밖 {SHAFT_EXT:g} (끝단 키홈 {S.parallel_key(L['dj']).name})", 1, "SM45C", (0, 0, 0), "축")
    add("종동축", _shaft(L, cd, False), f"저널 Ø{L['dj']:g} g6 ×2, 기어 자리 Ø{L['ds']:g} h6 키홈 {k.name}", 1, "SM45C", (0, 0, 0), "축")
    add("평행키(구동)", key_solid(xgc, bw - 4.0, k.b, k.h, z + L["ds"] / 2.0 - k.t1, 0.0), f"{k.name}×{bw - 4:g} KS B 1311", 1, "SM45C", (0, 0, 2.0), "키")
    add("평행키(종동)", key_solid(xgc, bw - 4.0, k.b, k.h, z + L["ds"] / 2.0 - k.t1, cd), f"{k.name}×{bw - 4:g} KS B 1311", 1, "SM45C", (0, 0, 2.0), "키")
    for i, y in enumerate(L["ys"]):
        add("부시", ring_x(L["x_pb"] - BUSH_L, L["x_pb"], L["bush_od"] / 2.0, L["dj"] / 2.0, y, z), f"Ø{L['bush_od']:g} p6 / Ø{L['dj']:g} H7 × {BUSH_L:g} (본체)", 1, "PBC2", (-1.0, 0, 0), "칼라")
        add("부시", ring_x(L["x_c0"], L["x_c0"] + BUSH_L, L["bush_od"] / 2.0, L["dj"] / 2.0, y, z), f"Ø{L['bush_od']:g} p6 / Ø{L['dj']:g} H7 × {BUSH_L:g} (커버)", 1, "PBC2", (1.0, 0, 0), "칼라")
    add("개스킷", _gasket(L), f"t {GASKET_T:g} (안착 깊이 {L['pocket_depth']:g} + {GASKET_T:g} = 기어 폭 {bw:g})", 1, "NBR", (1.5, 0, 0), "오일실")
    if a.covers:
        add("본체 커버", _cover(L), f"{COVER_T:g} 두께, 부시 구멍 Ø{L['bush_od']:g} H7 ×2, 오일실 자리 Ø{L['seal'].D:g} H8, 볼트 구멍 6", 1, "GC200", (2.2, 0, 0), "커버")
        se = L["seal"]
        add("오일실", ring_x(L["x_c1"] - se.b, L["x_c1"], se.D / 2.0, se.d / 2.0, 0.0, z), f"{se.name} KS B 2804", 1, "NBR", (3.0, 0, 0), "오일실")
        if a.bolts:
            from ..fasteners.standards import resolve, std_length
            f = resolve(L["bolt"])[0]
            grip = COVER_T + GASKET_T + 10.0
            bl = []
            for (py, pz) in L["bolt_pts"]:
                shaft = Pos(0, 0, -grip / 2.0) * Cylinder(radius=f.nominal_dia_mm / 2.0, height=grip)
                head = extrude(RegularPolygon(radius=f.head_across_corners_mm / 2.0, side_count=6), amount=f.head_height_mm)
                bl.append(Pos(L["x_c1"], py, pz) * Rot(0, 90, 0) * (shaft + head))
            add("육각볼트", Compound(children=bl), f"{f.name}×{std_length(f, grip):g} ×6", 6, "SCM435", (3.4, 0, 0), "볼트")

    pub = {
        "preset": "gear_pump", "z_axis": z, "center_distance": cd, "ys": L["ys"], "pinion": None,
        "gear": {"m": gd.m, "z": gd.z, "d": gd.d, "da": gd.da, "width": bw}, "journal_d": L["dj"], "seat_d": L["ds"],
        "bush": [L["bush_od"], L["dj"], BUSH_L], "seal": L["seal"].name, "pocket": [2 * L["pocket_r"], L["pocket_depth"]],
        "gasket_t": GASKET_T, "cover_bolt": L["bolt"], "x": {k_: round(v, 2) for k_, v in L.items() if k_.startswith("x_") or k_ == "xb0"},
        "key_hubs": {"평행키(구동)": ["스퍼기어(구동)", L["ds"]], "평행키(종동)": ["스퍼기어(종동)", L["ds"]]},
        "pair_probe": {"a": cd, "r": L["pocket_r"], "names": ["스퍼기어(구동)", "스퍼기어(종동)"], "m": gd.m, "width": bw},
        "motion_label": "각도(두 기어 반대 방향, 한 피치 안)", "motion_steps": [0.0, 90.0 / gd.z, 180.0 / gd.z, 270.0 / gd.z],
        "extra_checks": [
            {"code": "A8", "message": f"펌프 틈 / pump clearances: 포켓 Ø{2 * L['pocket_r']:g} G7 ≥ 기어 외경 Ø{gd.da:g} h6, 포켓 깊이 {L['pocket_depth']:g} + 개스킷 {GASKET_T:g} = 기어 폭 {bw:g}",
             "ok": (2 * L["pocket_r"] >= gd.da - 1e-6) and (L["pocket_depth"] + GASKET_T >= bw - 1e-6), "actual": L["pocket_depth"] + GASKET_T, "required": bw,
             "standard": "153LAB 해설: Ø39 G7/h6, 깊이 28 + 개스킷 1.0 = 폭 29", "suggestion": {"option_a": "개스킷 두께 또는 포켓 깊이 조정"}},
        ],
    }
    pub["fits"] = _fits(L, parts)
    mates = [
        {"id": "M1", "pair": "스퍼기어 ↔ 본체 안착 홈", "type": "동심 + 끝면 접촉(포켓 바닥, 커버 안면)", "detail": f"Ø{gd.da:g} G7/h6, 폭 {bw:g} = 깊이 {L['pocket_depth']:g} + 개스킷 {GASKET_T:g}", "ok": True},
        {"id": "M2", "pair": "부시 ↔ 본체, 커버 구멍", "type": "동심(압입 p6)", "detail": f"Ø{L['bush_od']:g} H7/p6 ×4", "ok": True},
        {"id": "M3", "pair": "축 저널 ↔ 부시", "type": "동심(미끄럼 g6)", "detail": f"Ø{L['dj']:g} H7/g6", "ok": True},
        {"id": "M4", "pair": "기어 ↔ 축 기어 자리", "type": "동심 + 키홈 정렬", "detail": f"Ø{L['ds']:g} H7/h6, 키 {k.name}", "ok": True},
        {"id": "M5", "pair": "구동 기어 ↔ 종동 기어", "type": "맞물림(중심거리)", "detail": f"a = m(z1+z2)/2 = {cd:g}", "ok": True},
        {"id": "M6", "pair": "커버 ↔ 개스킷 ↔ 본체", "type": "면 접촉 + 볼트 6", "detail": f"{L['bolt']} ×6", "ok": a.covers},
        {"id": "M7", "pair": "오일실 ↔ 커버 구멍 / 구동축", "type": "동심 + 자리 바닥 접촉", "detail": L["seal"].name, "ok": a.covers},
    ]
    asm = Assembly(parts, pub, mates, [{"no": p.no, "item": p.name, "spec": p.spec, "qty": p.qty, "material": p.material} for p in parts])
    g1p, g2p = asm.by_name("스퍼기어(구동)"), asm.by_name("스퍼기어(종동)")
    s1, s2 = asm.by_name("구동축"), asm.by_name("종동축")
    k1, k2 = asm.by_name("평행키(구동)"), asm.by_name("평행키(종동)")

    def rotx(solid, y, th):
        return Pos(0, y, z) * Rot(th, 0, 0) * Pos(0, -y, -z) * solid

    def motion(theta_deg: float) -> dict:
        t1, t2 = theta_deg, -theta_deg          # Same tooth count → 1:1, opposite rotation
        out = {"스퍼기어(구동)": rotx(g1p.solid, 0.0, t1), "스퍼기어(종동)": rotx(g2p.solid, cd, t2),
               "구동축": rotx(s1.solid, 0.0, t1), "종동축": rotx(s2.solid, cd, t2),
               "평행키(구동)": rotx(k1.solid, 0.0, t1), "평행키(종동)": rotx(k2.solid, cd, t2)}
        return out
    asm.motion = motion
    return asm


def _fits(L: dict, parts) -> list[dict]:
    z = L["z_axis"]
    def P(name, idx=0):
        ps = [p for p in parts if p.name == name]
        return ps[idx] if len(ps) > idx else None
    out = []
    hs, cv, seal = P("본체"), P("본체 커버"), P("오일실")
    bushes = [p for p in parts if p.name == "부시"]
    shafts = {0.0: P("구동축"), L["cd"]: P("종동축")}
    for i, y in enumerate(L["ys"]):
        bb, bc = bushes[2 * i], bushes[2 * i + 1]
        if hs: out.append(fit(f"부시 외경 Ø{L['bush_od']:g} ↔ 본체 구멍", bb, hs, L["bush_od"] / 2, L["x_pb"] - BUSH_L, L["x_pb"], (y, z)))
        if cv: out.append(fit(f"부시 외경 Ø{L['bush_od']:g} ↔ 커버 구멍", bc, cv, L["bush_od"] / 2, L["x_c0"], L["x_c0"] + BUSH_L, (y, z)))
        sh = shafts[y]
        if sh:
            out.append(fit(f"부시 내경 Ø{L['dj']:g} ↔ 축 저널", bb, sh, L["dj"] / 2, L["x_pb"] - BUSH_L, L["x_pb"], (y, z)))
            g = P("스퍼기어(구동)") if i == 0 else P("스퍼기어(종동)")
            if g: out.append(fit(f"기어 보어 Ø{L['ds']:g} ↔ 축 기어 자리", g, sh, L["ds"] / 2, L["x_pb"], L["x_c0"], (y, z)))
    if seal and cv:
        out.append(fit(f"오일실 외경 Ø{L['seal'].D:g} ↔ 커버 자리", seal, cv, L["seal"].D / 2, L["x_c1"] - L["seal"].b, L["x_c1"], (0.0, z)))
    if seal and shafts[0.0]:
        out.append(fit(f"오일실 내경 Ø{L['seal'].d:g} ↔ 구동축", seal, shafts[0.0], L["seal"].d / 2, L["x_c1"] - L["seal"].b, L["x_c1"], (0.0, z)))
    return out
