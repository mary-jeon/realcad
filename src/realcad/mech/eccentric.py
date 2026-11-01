"""Eccentric reciprocating mechanism (eccentric slider) assembly builder: second CAD practical exam preset.

Reference: 153LAB 2023 engineer exam commentary, craftsman course outline (stroke = 2e).
Parts: body (box), eccentric shaft, link (crank), slider, pin, guide bushing, top cover, V-belt pulley, parallel key,
      2 spacer rings, 2 ball bearings, 2 retaining rings, oil seal, 2 end covers, bolts.
      The pulley and bearing sides share their layout with power_train.

Coordinates: shaft = X, y = 0, z = Z_AXIS. At angle θ the eccentric journal is offset by (y, z) = (e cosθ, e sinθ) (θ = 0 is +Y).
The link is a strap around the journal plus an upward bar; a pin at its top joins the slider (vertical rod),
which is guided by the guide bushing in the top cover.
Kinematics: pin height z_pin(θ) = z_axis + e sinθ + sqrt(L² - (e cosθ)²), link tilt φ = asin(e cosθ / L). Stroke = 2e.
"""
from __future__ import annotations
import math

from build123d import Part, Compound, Box, Cylinder, Pos, Rot, Polygon, Plane, revolve

from . import standards as S
from .power_train import (PartInfo, Assembly, cyl_x, ring_x, shaft_keyway_cutter, hub_keyway_cutter, key_solid,
                          bearing_solid, retaining_ring_solid, pulley_solid, hex_bolt_x, _cover, _cover_bolt_points,
                          fit, BASE_T, COVER_T, SPIGOT, LIP)

WALL_Y = 8.0          # Body side wall thickness
TOP_T = 14.0          # Body top wall thickness (cover bolt tap 12 + margin)
COLLAR_L = 6.0        # Spacer ring length (3 on the bearing side + 3 on the link side)
LINK_W = 16.0         # Link thickness (X)
ROD_W = 24.0          # Link bar width (Y)
TONGUE_T = 8.0        # Slider tongue thickness (X)
TONGUE_H = 30.0
PIN_D = 10.0
BUSH_WALL = 4.0
BUSH_L = 30.0
BUSH_FLANGE = 4.0
TOPCOVER_T = 12.0
TOPCOVER_W = 80.0
CLEAR = 4.0           # Clearance between the link sweep and the body interior


def layout_eccentric(a) -> dict:
    bs = S.bearing(a.bearing)
    d = bs.d
    if a.shaft_d and a.shaft_d >= 5 and abs(a.shaft_d - d) > 1e-6:
        bs = S.bearing_for_shaft(a.shaft_d); d = bs.d
    dsh = bs.da_min
    key_p = S.parallel_key(d)
    ring = S.retaining_ring(d)
    e = float(a.eccentricity)
    L = float(a.link_length)
    if L < 3.0 * e:
        L = 3.0 * e                                        # Keeps link tilt ≤ 19.5 degrees
    de = d + 2 * e + 4.0                                   # Eccentric journal diameter (wraps the base shaft with 2 mm of material)
    strap_R = de / 2.0 + 8.0
    ds = float(a.slider_d)
    gs = S.vpulley_groove(a.pulley_type, a.pulley_dp) if a.pulley_type != "none" else None
    has_pulley = gs is not None
    Wp = (float(a.pulley_hub_w) if a.pulley_hub_w > 0 else
          (round(max(1.6 * d, gs.e * (a.pulley_grooves - 1) + 2 * gs.f), 1) if gs else 0.0))
    seal = S.oil_seal(dsh) if (has_pulley and a.oil_seal) else None
    bolt_name = S.cover_bolt_size(bs.D)
    pcd = S.cover_bolt_pcd(bs.D)
    from ..fasteners.standards import resolve as _resolve
    fb = _resolve(bolt_name)[0]
    hub_gap = fb.head_height_mm + 2.0
    Wy = pcd + 14.0

    # X coordinates
    x = 0.0
    stub = ring.n + 0.5
    xg1 = x + stub
    if has_pulley:
        xp0 = xg1 + ring.m
        x_hub_end = xp0 + Wp
        x_cov1_out = x_hub_end + hub_gap
        x_w1_0 = x_cov1_out + COVER_T
        xb1 = x_w1_0 + SPIGOT
        collar = (x_hub_end, xb1)
    else:
        xp0 = None
        xb1 = stub + ring.m + SPIGOT + COVER_T          # Temporary; left side recomputed below
        x_cov1_out = xb1 - SPIGOT - COVER_T
        x_w1_0 = x_cov1_out + COVER_T
        collar = None
        xg1 = xb1 - ring.m
        x = xg1 - stub
    x_w1_1 = xb1 + bs.B + LIP
    collar_l = max(COLLAR_L, (ds + 10.0 - LINK_W) / 2.0)    # Body interior length (2 collars + link - 2 shoulders) ≥ slider rod Ø + 6
    x_c2 = xb1 + bs.B                                      # Left spacer ring start
    xe0 = x_c2 + collar_l                                  # Eccentric journal left face
    xe1 = xe0 + LINK_W
    x_c3 = xe1                                             # Right spacer ring
    xb2 = xe1 + collar_l
    x_w2_0 = xb2 - LIP
    x_w2_1 = xb2 + bs.B + SPIGOT
    xg2 = xb2 + bs.B
    x_end = xg2 + ring.m + 1.0
    x_cov2_out = x_w2_1 + COVER_T
    xe_c = (xe0 + xe1) / 2.0                               # Eccentric journal center = link, slider and top cover center

    # Z, Y
    orbit = e + strap_R                                    # Link strap sweep radius
    z_axis = BASE_T + orbit + CLEAR
    if gs:
        z_axis = max(z_axis, gs.od / 2.0 + 3.0)
    z_axis = max(z_axis, BASE_T + Wy / 2.0 + 2.0)
    inner_half_y = max(orbit + CLEAR, Wy / 2.0 - WALL_Y + 1.0)
    outer_half_y = inner_half_y + WALL_Y
    z_pin_min = z_axis - e + L                             # θ = 270
    z_pin_max = z_axis + e + L                             # θ = 90
    z_cav_top = z_pin_max + TONGUE_H / 2.0 + 3.0           # Tongue top + clearance = bushing bottom
    z_top = z_cav_top + TOP_T                              # Body top face
    z_cover_top = z_top + TOPCOVER_T
    bush_z0 = z_cav_top
    bush_z1 = z_cover_top                                  # Bushing body passes through the top wall + cover thickness
    rod_len = (bush_z1 + 8.0) - (z_pin_min + TONGUE_H / 2.0 - 2.0)   # Leaves 8 mm above the bushing even at bottom dead center
    base = (x_w1_0 - 8.0, x_w2_1 + 8.0, -(outer_half_y + 8.0), outer_half_y + 8.0)
    tc_w = min(TOPCOVER_W, (x_w2_1 - x_w1_0) - 2.0, 2 * outer_half_y - 2.0)
    return dict(tc_w=tc_w, collar_l=collar_l,
        bearing=bs, d=d, dsh=dsh, key_p=key_p, ring=ring, e=e, L=L, de=de, strap_R=strap_R, ds=ds,
        groove=gs, pulley_w=Wp, grooves=int(a.pulley_grooves), seal=seal, bolt=bolt_name, pcd=pcd, Wy=Wy,
        x0=x, xg1=xg1, xp0=xp0, collar=collar, x_cov1_out=x_cov1_out, x_w1_0=x_w1_0, xb1=xb1, x_w1_1=x_w1_1,
        x_c2=x_c2, xe0=xe0, xe1=xe1, xe_c=xe_c, x_c3=x_c3, xb2=xb2, x_w2_0=x_w2_0, x_w2_1=x_w2_1, xg2=xg2,
        x_end=x_end, x_cov2_out=x_cov2_out, z_axis=z_axis, ys=[0.0], base=base, has_pulley=has_pulley,
        collar_od=dsh, inner_half_y=inner_half_y, outer_half_y=outer_half_y, z_cav_top=z_cav_top, z_top=z_top,
        z_cover_top=z_cover_top, bush_z0=bush_z0, bush_z1=bush_z1, rod_len=rod_len, z_pin_min=z_pin_min,
        z_pin_max=z_pin_max, collar_big=de + 4.0,
    )


# ── Kinematics ───────────────────────────────────────────────────
def kinematics(L: dict, theta_deg: float) -> dict:
    e, Lk, z = L["e"], L["L"], L["z_axis"]
    t = math.radians(theta_deg)
    yc, zc = e * math.cos(t), z + e * math.sin(t)          # Eccentric journal center
    phi = math.asin(max(-1.0, min(1.0, e * math.cos(t) / Lk)))   # Link tilt (so the pin stays at y = 0)
    z_pin = zc + Lk * math.cos(phi)
    return {"yc": yc, "zc": zc, "phi_deg": math.degrees(phi), "z_pin": z_pin}


# ── Parts ─────────────────────────────────────────────────────────
def _shaft(L: dict) -> Part:
    from build123d import Axis
    d, bs, ring, z = L["d"], L["bearing"], L["ring"], L["z_axis"]
    pts = [(L["x0"], 0.0), (L["x0"], d / 2.0), (L["x_end"], d / 2.0), (L["x_end"], 0.0)]
    s = Pos(0, 0, z) * revolve(Plane.XZ * Polygon(*pts, align=None), axis=Axis.X)
    s = s + cyl_x(L["xe0"], L["xe1"], L["de"] / 2.0, L["e"], z)            # Eccentric journal (θ=0: offset e toward +Y)
    for xg in (L["xg1"], L["xg2"]):
        s = s - ring_x(xg, xg + ring.m, d / 2.0 + 1.0, ring.d2 / 2.0, 0.0, z)
    if L["has_pulley"]:
        kp, Wp = L["key_p"], L["pulley_w"]
        s = s - shaft_keyway_cutter(L["xp0"] + Wp / 2.0, Wp - 4.0, kp.b, z + d / 2.0 - kp.t1, 0.0)
    return s


def _link_local(L: dict) -> Part:
    """Link (crank): journal bore center = origin, bar along +Z, thickness in X. Pin hole and slider slot (fork) at the top end."""
    de, R, Lk = L["de"], L["strap_R"], L["L"]
    strap = Rot(0, 90, 0) * Cylinder(radius=R, height=LINK_W)
    rod = Pos(0, 0, Lk / 2.0) * Box(LINK_W, ROD_W, Lk)
    boss = Pos(0, 0, Lk) * Rot(0, 90, 0) * Cylinder(radius=ROD_W / 2.0, height=LINK_W)
    body = strap + rod + boss
    body = body - Rot(0, 90, 0) * Cylinder(radius=de / 2.0, height=LINK_W + 2)                        # Journal bore (cut after fusing the bar)
    body = body - Pos(0, 0, Lk) * Rot(0, 90, 0) * Cylinder(radius=PIN_D / 2.0, height=LINK_W + 2)      # Pin hole
    slot_h = ROD_W / 2.0 + TONGUE_H / 2.0 + 2.0
    body = body - Pos(0, 0, Lk - TONGUE_H / 2.0 + slot_h / 2.0) * Box(TONGUE_T + 0.4, ROD_W + 2, slot_h)   # Slider slot (fork)
    return body


def _slider_local(L: dict) -> Part:
    """Slider: pin center = origin. Tongue (8×24×30) plus rod Ø ds upward."""
    ds = L["ds"]
    # Tongue = round eye around the pin (radius ROD_W/2) + square top, so it clears the slot bottom when the link tilts (clevis eye)
    eye = Rot(0, 90, 0) * Cylinder(radius=ROD_W / 2.0, height=TONGUE_T)
    upper = Pos(0, 0, TONGUE_H / 4.0) * Box(TONGUE_T, ROD_W, TONGUE_H / 2.0)
    tongue = eye + upper
    rod = Pos(0, 0, TONGUE_H / 2.0 - 2.0 + L["rod_len"] / 2.0) * Cylinder(radius=ds / 2.0, height=L["rod_len"])
    body = tongue + rod
    return body - Rot(0, 90, 0) * Cylinder(radius=PIN_D / 2.0, height=TONGUE_T + 2)


def place_link(L: dict, theta_deg: float, local: Part) -> Part:
    k = kinematics(L, theta_deg)
    return Pos(L["xe_c"], k["yc"], k["zc"]) * Rot(k["phi_deg"], 0, 0) * local


def place_slider(L: dict, theta_deg: float, local: Part) -> Part:
    k = kinematics(L, theta_deg)
    return Pos(L["xe_c"], 0.0, k["z_pin"]) * local


def place_pin(L: dict, theta_deg: float) -> Part:
    k = kinematics(L, theta_deg)
    return cyl_x(L["xe_c"] - LINK_W / 2.0 - 1.0, L["xe_c"] + LINK_W / 2.0 + 1.0, PIN_D / 2.0, 0.0, k["z_pin"])


def _housing(L: dict) -> Part:
    bs, z = L["bearing"], L["z_axis"]
    bx0, bx1, by0, by1 = L["base"]
    ohy, ihy = L["outer_half_y"], L["inner_half_y"]
    xa, xb = L["x_w1_0"], L["x_w2_1"]
    body = Pos((bx0 + bx1) / 2.0, (by0 + by1) / 2.0, BASE_T / 2.0) * Box(bx1 - bx0, by1 - by0, BASE_T)
    body = body + Pos((xa + xb) / 2.0, 0, L["z_top"] / 2.0) * Box(xb - xa, 2 * ohy, L["z_top"])
    ca, cb = L["x_w1_1"], L["x_w2_0"]
    cav_h = L["z_cav_top"] - BASE_T
    body = body - Pos((ca + cb) / 2.0, 0, BASE_T + cav_h / 2.0) * Box(cb - ca, 2 * ihy, cav_h)
    # Bearing bore + shoulder
    body = body - cyl_x(xa - 1, L["xb1"] + bs.B, bs.D / 2.0, 0.0, z)
    body = body - cyl_x(xa - 1, L["x_w1_1"] + 1, bs.Da_max / 2.0, 0.0, z)
    body = body - cyl_x(L["xb2"], xb + 1, bs.D / 2.0, 0.0, z)
    body = body - cyl_x(L["x_w2_0"] - 1, xb + 1, bs.Da_max / 2.0, 0.0, z)
    # Top wall: bushing hole Ø(ds+2 wall) through + cover spigot recess Ø50, depth 3
    bush_od = L["ds"] + 2 * BUSH_WALL
    xc = L["xe_c"]
    body = body - Pos(xc, 0, L["z_top"]) * Cylinder(radius=bush_od / 2.0, height=2 * TOP_T + 2)
    body = body - Pos(xc, 0, L["z_top"] - SPIGOT / 2.0 + 0.5) * Cylinder(radius=25.0, height=SPIGOT + 1.0)
    from ..fasteners.standards import resolve
    f = resolve(L["bolt"])[0]
    for (yc, zc) in _cover_bolt_points(L):                 # End cover bolt tapped holes
        body = body - cyl_x(xa - 1, xa + 12.0, f.nominal_dia_mm / 2.0, yc, zc)
        body = body - cyl_x(xb - 12.0, xb + 1, f.nominal_dia_mm / 2.0, yc, zc)
    for (px, py) in _top_bolt_points(L):                   # Top cover bolt tapped holes
        body = body - Pos(px, py, L["z_top"] - 6.0 + 0.5) * Cylinder(radius=f.nominal_dia_mm / 2.0, height=13.0)
    for sx in (bx0 + 10.0, bx1 - 10.0):
        for sy in (by0 + 10.0, by1 - 10.0):
            body = body - Pos(sx, sy, BASE_T / 2.0) * Cylinder(radius=4.5, height=BASE_T + 2)
    return body


def _top_bolt_points(L: dict):
    xc = L["xe_c"]; o = L["tc_w"] / 2.0 - 7.0            # At least 3 mm from the edge of the Ø50 spigot (r 25)
    return [(xc + sx * o, sy * o) for sx in (-1, 1) for sy in (-1, 1)]


def _top_cover(L: dict) -> Part:
    from ..fasteners.standards import resolve
    f = resolve(L["bolt"])[0]
    xc, zt = L["xe_c"], L["z_top"]
    bush_od = L["ds"] + 2 * BUSH_WALL
    plate = Pos(xc, 0, zt + TOPCOVER_T / 2.0) * Box(L["tc_w"], L["tc_w"], TOPCOVER_T)
    spig = Pos(xc, 0, zt - SPIGOT / 2.0) * Cylinder(radius=25.0, height=SPIGOT)
    body = plate + spig
    body = body - Pos(xc, 0, zt) * Cylinder(radius=bush_od / 2.0, height=2 * TOPCOVER_T + 2 * SPIGOT + 2)
    for (px, py) in _top_bolt_points(L):
        body = body - Pos(px, py, zt + TOPCOVER_T / 2.0) * Cylinder(radius=f.clearance("normal") / 2.0, height=TOPCOVER_T + 2)
    return body


def _bush(L: dict) -> Part:
    ds = L["ds"]; xc = L["xe_c"]
    z0, z1 = L["bush_z0"], L["bush_z1"]
    body = Pos(xc, 0, (z0 + z1) / 2.0) * Cylinder(radius=ds / 2.0 + BUSH_WALL, height=z1 - z0)
    body = body + Pos(xc, 0, z1 + BUSH_FLANGE / 2.0) * Cylinder(radius=ds / 2.0 + BUSH_WALL + 4.0, height=BUSH_FLANGE)
    return body - Pos(xc, 0, (z0 + z1 + BUSH_FLANGE) / 2.0) * Cylinder(radius=ds / 2.0, height=z1 - z0 + BUSH_FLANGE + 2)


def build_eccentric(a) -> Assembly:
    L = layout_eccentric(a)
    bs, d, dsh, z, ring = L["bearing"], L["d"], L["dsh"], L["z_axis"], L["ring"]
    parts: list[PartInfo] = []
    no = [0]

    def add(name, solid, spec="", qty=1, material="", explode=(0, 0, 0), group=""):
        no[0] += 1
        parts.append(PartInfo(name, solid, spec, qty, material, explode, group or name.split()[0], no[0]))

    if a.housing:
        add("본체", _housing(L), f"박스 하우징, 베어링 구멍 Ø{bs.D:g} H7 ×2, 턱 Ø{bs.Da_max:g}, 윗벽 부시 구멍 Ø{L['ds'] + 2 * BUSH_WALL:g}, 커버 끼움 Ø50", 1, "GC200", (0, 0, -1.0))
    add("편심축", _shaft(L), f"Ø{d:g} 베어링 자리 ×2 (k5), 편심 저널 Ø{L['de']:g}×{LINK_W:g} 편심량 e={L['e']:g}, 멈춤링 홈 Ø{ring.d2:g}×{ring.m:g} ×2"
        + (f", 풀리 자리 키홈 {L['key_p'].name}" if L["has_pulley"] else ""), 1, "SM45C", (0, 0, 0), "축")
    link_local, slider_local = _link_local(L), _slider_local(L)
    add("링크(크랭크)", place_link(L, 0.0, link_local), f"스트랩 보어 Ø{L['de']:g} H7, 외경 Ø{2 * L['strap_R']:g}, 중심 간 L={L['L']:g}, 두께 {LINK_W:g}, 핀 구멍 Ø{PIN_D:g}", 1, "SC49", (0, 0, 1.0), "기어")
    add("슬라이더", place_slider(L, 0.0, slider_local), f"봉 Ø{L['ds']:g} h6 ×{L['rod_len']:.0f}, 혀 {TONGUE_T:g}×{ROD_W:g}×{TONGUE_H:g}, 행정 {2 * L['e']:g}", 1, "SM45C", (0, 0, 3.0), "축")
    add("핀", place_pin(L, 0.0), f"Ø{PIN_D:g} × {LINK_W + 2:g}", 1, "SM45C", (1.5, 0, 1.0), "키")
    cb = L["collar_big"]; cl = L["collar_l"]
    for (xs, ex) in ((L["x_c2"], -1.0), (L["x_c3"], 1.0)):
        if ex < 0:   # Bearing side Ø da min (3 mm) → link side Ø(de+4)
            sp = ring_x(xs, xs + 3.0, dsh / 2.0, d / 2.0, 0.0, z) + ring_x(xs + 3.0 - 0.01, xs + cl, cb / 2.0, d / 2.0, 0.0, z)
        else:
            sp = ring_x(xs, xs + cl - 3.0 + 0.01, cb / 2.0, d / 2.0, 0.0, z) + ring_x(xs + cl - 3.0, xs + cl, dsh / 2.0, d / 2.0, 0.0, z)
        add("간격링", sp, f"단붙이 Ø{dsh:g}/Ø{cb:g}, 보어 Ø{d:g}, 길이 {cl:g} (링크 양면 접촉)", 1, "SM45C", (ex * 0.8, 0, 0), "스페이서")
    add("볼베어링", bearing_solid(bs, L["xb1"], 0.0, z), f"{bs.code} (d{bs.d:g} D{bs.D:g} B{bs.B:g}) KS B 2023", 1, "", (-1.0, 0, 0), "베어링")
    add("볼베어링", bearing_solid(bs, L["xb2"], 0.0, z), f"{bs.code} (d{bs.d:g} D{bs.D:g} B{bs.B:g}) KS B 2023", 1, "", (1.0, 0, 0), "베어링")
    if a.rings:
        add("멈춤링(C형)", retaining_ring_solid(ring, L["xg1"] + ring.m - ring.t, 0.0, z), f"축용 {ring.d1:g} KS B 1336", 1, "SK5", (-4.0, 0, 0), "멈춤링")
        add("멈춤링(C형)", retaining_ring_solid(ring, L["xg2"], 0.0, z), f"축용 {ring.d1:g} KS B 1336", 1, "SK5", (1.5, 0, 0), "멈춤링")
    if L["has_pulley"]:
        gs, Wp, kp = L["groove"], L["pulley_w"], L["key_p"]
        xpc = L["xp0"] + Wp / 2.0
        pul = pulley_solid(gs, L["grooves"], Wp, d, xpc, 0.0, z) - hub_keyway_cutter(xpc, Wp + 2.0, kp.b, z + d / 2.0 + kp.t2, 0.0)
        add("V벨트 풀리", pul, f"{gs.belt}형 ×{L['grooves']} PD Ø{gs.dp:g} KS B 1400, 보어 Ø{d:g} 키홈 {kp.b:g}×{kp.t2:g}", 1, "GC200", (-3.0, 0, 0), "풀리")
        add("평행키(풀리)", key_solid(xpc, Wp - 4.0, kp.b, kp.h, z + d / 2.0 - kp.t1), f"{kp.name}×{Wp - 4:g} KS B 1311", 1, "SM45C", (-3.0, 0, 1.0), "키")
        c0, c1 = L["collar"]
        add("칼라", ring_x(c0, c1, dsh / 2.0, d / 2.0, 0.0, z), f"Ø{dsh:g}/Ø{d:g}×{c1 - c0:g}", 1, "SM45C", (-1.5, 0, 0), "칼라")
        if L["seal"]:
            se = L["seal"]
            add("오일실", ring_x(L["x_cov1_out"], L["x_cov1_out"] + se.b, se.D / 2.0, se.d / 2.0, 0.0, z), f"{se.name} TC KS B 2804", 1, "NBR", (-2.5, 0, 0), "오일실")
    if a.covers:
        add("커버(왼)", _cover(L, -1, [0.0]), f"플랜지 Ø{L['Wy']:g}×{COVER_T:g}, 끼움부 Ø{bs.D:g}×{SPIGOT:g}" + (f", 오일실 자리 Ø{L['seal'].D:g}×{L['seal'].b:g}" if L["seal"] else ""), 1, "GC200", (-2.0, 0, 0), "커버")
        add("커버(오른)", _cover(L, 1, [0.0]), f"플랜지 Ø{L['Wy']:g}×{COVER_T:g}, 끼움부 Ø{bs.D:g}×{SPIGOT:g}, 블라인드", 1, "GC200", (2.0, 0, 0), "커버")
        add("커버(상부)", _top_cover(L), f"{L['tc_w']:g}×{L['tc_w']:g}×{TOPCOVER_T:g}, 끼움부 Ø50×{SPIGOT:g}, 부시 구멍 Ø{L['ds'] + 2 * BUSH_WALL:g} H7", 1, "GC200", (0, 0, 2.0), "커버")
        add("가이드부시", _bush(L), f"Ø{L['ds']:g} H7 / Ø{L['ds'] + 2 * BUSH_WALL:g} p6 × {L['bush_z1'] - L['bush_z0']:.0f}, 플랜지", 1, "BC6", (0, 0, 2.6), "칼라")
        if a.bolts:
            from ..fasteners.standards import resolve, std_length
            f = resolve(L["bolt"])[0]
            grip = COVER_T + 10.0
            pts = _cover_bolt_points(L)
            add("육각볼트(왼 커버)", Compound(children=[hex_bolt_x(f, L["x_cov1_out"], yc, zc, grip, +1) for yc, zc in pts]),
                f"{f.name}×{std_length(f, grip):g} ×{len(pts)}", len(pts), "SCM435", (-2.6, 0, 0), "볼트")
            add("육각볼트(오른 커버)", Compound(children=[hex_bolt_x(f, L["x_cov2_out"], yc, zc, grip, -1) for yc, zc in pts]),
                f"{f.name}×{std_length(f, grip):g} ×{len(pts)}", len(pts), "SCM435", (2.6, 0, 0), "볼트")
            gt = TOPCOVER_T + 10.0
            tb = []
            for (px, py) in _top_bolt_points(L):
                from .power_train import RegularPolygon, extrude
                shaft = Pos(0, 0, -gt / 2.0) * Cylinder(radius=f.nominal_dia_mm / 2.0, height=gt)
                head = extrude(RegularPolygon(radius=f.head_across_corners_mm / 2.0, side_count=6), amount=f.head_height_mm)
                tb.append(Pos(px, py, L["z_cover_top"]) * (shaft + head))
            add("육각볼트(상부 커버)", Compound(children=tb), f"{f.name}×{std_length(f, gt):g} ×4", 4, "SCM435", (0, 0, 2.8), "볼트")

    pub = _layout_public(L)
    pub["fits"] = _fits(L, parts)
    asm = Assembly(parts, pub, _mates(L, a), [{"no": p.no, "item": p.name, "spec": p.spec, "qty": p.qty, "material": p.material} for p in parts])
    shaft = asm.by_name("편심축")

    def motion(theta_deg: float) -> dict:
        out = {"링크(크랭크)": place_link(L, theta_deg, link_local), "슬라이더": place_slider(L, theta_deg, slider_local), "핀": place_pin(L, theta_deg)}
        if shaft is not None:    # Rotate the shaft too, to see the journal/strap relationship at that angle
            out["편심축"] = Pos(0, 0, z) * Rot(theta_deg, 0, 0) * Pos(0, 0, -z) * shaft.solid
        return out
    asm.motion = motion
    return asm


def _layout_public(L: dict) -> dict:
    bs = L["bearing"]
    out = {
        "preset": "eccentric_slider", "shaft_d": L["d"], "shoulder_d": L["dsh"], "bearing": bs.code,
        "bearing_dDB": [bs.d, bs.D, bs.B], "da_range": [bs.da_min, bs.da_max], "Da_max": bs.Da_max,
        "eccentricity": L["e"], "stroke": 2 * L["e"], "link_length": L["L"], "journal_d": L["de"], "slider_d": L["ds"],
        "key_pulley": (L["key_p"].name if L["has_pulley"] else None), "ring": {"d2": L["ring"].d2, "m": L["ring"].m, "t": L["ring"].t},
        "seal": (L["seal"].name if L["seal"] else None),
        "pulley": ({"type": L["groove"].belt, "dp": L["groove"].dp, "od": L["groove"].od, "alpha": L["groove"].alpha, "width": L["pulley_w"]} if L["groove"] else None),
        "cover_bolt": L["bolt"], "pcd": L["pcd"], "z_axis": L["z_axis"], "z_top": L["z_top"], "bush_z": [L["bush_z0"], L["bush_z1"]],
        "z_pin_range": [round(L["z_pin_min"], 2), round(L["z_pin_max"], 2)], "shaft_length": round(L["x_end"] - L["x0"], 2),
        "x": {k: round(L[k], 2) for k in ("xb1", "xb2", "xe0", "xe1", "xe_c", "x_w1_0", "x_w1_1", "x_w2_0", "x_w2_1", "x_end", "xg1", "xg2") if L.get(k) is not None},
        "ys": [0.0], "center_distance": 0.0, "pinion": None, "gear": None,
    }
    if L["has_pulley"]:
        out["x"]["xp0"] = round(L["xp0"], 2); out["collar"] = [round(L["collar"][0], 2), round(L["collar"][1], 2)]
    return out


def _fits(L: dict, parts) -> list[dict]:
    bs, d, dsh, z = L["bearing"], L["d"], L["dsh"], L["z_axis"]
    def P(name, idx=0):
        ps = [p for p in parts if p.name == name]
        return ps[idx] if len(ps) > idx else None
    out = []
    hs, shaft, link, slider, bush, tc = P("본체"), P("편심축"), P("링크(크랭크)"), P("슬라이더"), P("가이드부시"), P("커버(상부)")
    for bx, br in zip((L["xb1"], L["xb2"]), [p for p in parts if p.name == "볼베어링"]):
        if shaft: out.append(fit(f"베어링 내경 Ø{d:g} ↔ 축 자리", br, shaft, d / 2, bx, bx + bs.B, (0.0, z)))
        if hs: out.append(fit(f"베어링 외경 Ø{bs.D:g} ↔ 본체 구멍", br, hs, bs.D / 2, bx, bx + bs.B, (0.0, z)))
    if link and shaft:
        out.append(fit(f"링크 보어 Ø{L['de']:g} ↔ 편심 저널(축선 e={L['e']:g})", link, shaft, L["de"] / 2, L["xe0"], L["xe1"], (L["e"], z)))
    if bush and slider:
        out.append(fit(f"가이드부시 보어 Ø{L['ds']:g} ↔ 슬라이더 봉", bush, slider, L["ds"] / 2, L["bush_z0"], L["bush_z1"], (L["xe_c"], 0.0), axis="Z"))
    if bush and tc:
        out.append(fit(f"부시 외경 Ø{L['ds'] + 2 * BUSH_WALL:g} ↔ 상부 커버 구멍", bush, tc, L["ds"] / 2 + BUSH_WALL, L["z_top"], L["z_cover_top"], (L["xe_c"], 0.0), axis="Z"))
    if tc and hs:
        out.append(fit("상부 커버 끼움부 Ø50 ↔ 본체 윗벽 구멍", tc, hs, 25.0, L["z_top"] - SPIGOT, L["z_top"], (L["xe_c"], 0.0), axis="Z"))
    if L["has_pulley"] and P("V벨트 풀리") and shaft:
        out.append(fit(f"풀리 보어 Ø{d:g} ↔ 축 자리", P("V벨트 풀리"), shaft, d / 2, L["xp0"], L["xp0"] + L["pulley_w"], (0.0, z)))
    for cv, (x0, x1) in ((P("커버(왼)"), (L["x_w1_0"], L["xb1"])), (P("커버(오른)"), (L["xb2"] + bs.B, L["x_w2_1"]))):
        if cv and hs: out.append(fit(f"커버 끼움부 Ø{bs.D:g} ↔ 본체 구멍", cv, hs, bs.D / 2, x0, x1, (0.0, z)))
    return out


def _mates(L: dict, a) -> list[dict]:
    bs, d, dsh, ring = L["bearing"], L["d"], L["dsh"], L["ring"]
    m = [
        {"id": "M1", "pair": "베어링 내륜 ↔ 편심축 베어링 자리", "type": "동심 + 측면 접촉(간격링, 칼라)", "detail": f"자리 Ø{d:g} = 내경, 간격링 Ø{dsh:g} (da {bs.da_min:g}~{bs.da_max:g})", "ok": True},
        {"id": "M2", "pair": "베어링 외륜 ↔ 본체 구멍", "type": "동심 + 측면 접촉", "detail": f"구멍 Ø{bs.D:g} H7, 턱 Ø{bs.Da_max:g}", "ok": a.housing},
        {"id": "M3", "pair": "링크 스트랩 ↔ 편심 저널", "type": "동심(편심 축선) + 측면 접촉(간격링 양면)", "detail": f"저널 Ø{L['de']:g} 편심량 e={L['e']:g}, 링크 두께 {LINK_W:g} = 저널 길이", "ok": True},
        {"id": "M4", "pair": "핀 ↔ 링크 핀 구멍, 슬라이더 혀", "type": "동심(회전 조인트)", "detail": f"핀 Ø{PIN_D:g}, 슬라이더 홈 폭 {TONGUE_T + 0.4:g} / 혀 {TONGUE_T:g}", "ok": True},
    ]
    if L["has_pulley"]:
        m.append({"id": "M5", "pair": "V풀리 ↔ 축 풀리 자리", "type": "동심 + 키홈 정렬 + 측면 접촉", "detail": f"보어 Ø{d:g}, 키 {L['key_p'].name}", "ok": True})
    if a.covers:
        m.append({"id": "M6", "pair": "커버 3 ↔ 본체", "type": "동심(끼움부) + 면 접촉 + 볼트 패턴", "detail": f"끝 커버 Ø{bs.D:g}×{SPIGOT:g} PCD {L['pcd']:g}, 상부 커버 Ø50×{SPIGOT:g} 볼트 4", "ok": True})
        m.append({"id": "M9", "pair": "가이드부시 ↔ 상부 커버 구멍 ↔ 슬라이더 봉", "type": "동심 + 베어링 축선에 직각", "detail": f"부시 Ø{L['ds']:g} H7 / Ø{L['ds'] + 2 * BUSH_WALL:g} p6, 행정 {2 * L['e']:g} (= 2e)", "ok": True})
    if a.rings:
        m.append({"id": "M7", "pair": "멈춤링 ↔ 축 홈", "type": "동심 + 홈 안 위치", "detail": f"홈 Ø{ring.d2:g}×{ring.m:g}", "ok": ring.t < ring.m})
    if L["seal"]:
        m.append({"id": "M8", "pair": "오일실 ↔ 커버 구멍 / 칼라", "type": "동심 + 자리 바닥 접촉", "detail": f"{L['seal'].name}", "ok": True})
    return m
