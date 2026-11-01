"""Power transmission assembly builder: shaft, parallel key, spur gear, V-pulley, deep groove ball bearing, body, cover, oil seal, retaining ring, bolts.

Derives the remaining dimensions from a few inputs (bearing size, gear m and z, pulley type and pitch diameter, pinion tooth count)
via the standards tables (standards.py), and builds every part **in assembled coordinates** (mates M1 to M9 fixed by coordinates).
Shaft along X, body bottom z=0.

Coordinate conventions
- Shaft centerlines: y = 0 (main shaft), y = a (pinion shaft, center distance a = m(z1+z2)/2), z = Z_AXIS.
- All keyways at +Z (top). Hub keyways (gear, pulley) are cut in world coordinates after placing the hub, so they line up with the shaft keyways (M3, M5).
- Axial retention chain (left to right): retaining ring → pulley hub → collar → bearing 1 inner ring → shaft shoulder (Ø da) → spacer → gear → spacer → bearing 2 inner ring → retaining ring.
  Outer rings: between the cover spigot shoulder and the body shoulder (Ø Da).
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math

from build123d import (Part, Compound, Box, Cylinder, Pos, Rot, Polygon, Plane, SlotOverall,
                       extrude, revolve, RegularPolygon)

from . import standards as S
from ..geometry.builder import involute_gear_outline, _wedge_cutter

Z_AXIS_MIN_CLEAR = 4.0      # Minimum clearance between gear tip and body floor
BASE_T = 10.0               # Body floor thickness
COVER_T = 10.0              # Cover flange thickness
SPIGOT = 3.0                # Cover spigot depth
LIP = 2.0                   # Body inner shoulder (outer ring stop) thickness
SPACER_L = 6.0              # Spacer length on each side of the gear
HUB_GAP = 3.0               # Gap between pulley hub and cover outer face

COLORS = {"축": "#b8bfc8", "기어": "#6fa8dc", "피니언": "#8ab4e0", "풀리": "#5c6670", "베어링": "#d9dde2",
          "키": "#e8a33c", "본체": "#7d9b86", "커버": "#9aa7b2", "오일실": "#2b2f35", "멈춤링": "#c94c4c",
          "볼트": "#8a5a44", "칼라": "#c9b27c", "스페이서": "#c9b27c"}


@dataclass
class PartInfo:
    name: str                 # Part name (Korean)
    solid: Part               # Assembled coordinates
    spec: str = ""            # Spec/dimension string (BOM)
    qty: int = 1
    material: str = ""
    explode: tuple = (0.0, 0.0, 0.0)   # Exploded view direction in multiples of gap (dx, dy, dz)
    group: str = ""           # Color group (COLORS key)
    no: int = 0               # Part number

    @property
    def color(self) -> str:
        return COLORS.get(self.group or self.name.split()[0], "#9aa7b2")


@dataclass
class Assembly:
    parts: list[PartInfo]
    layout: dict              # Dimensions and positions (for checks and reports). layout["fits"] = fit pairs (measured by A2)
    mates: list[dict]         # How M1 to M9 are satisfied
    bom: list[dict]
    motion: object = None     # For moving mechanisms: callable(theta_deg) -> {part name: solid at that angle} (A7 motion interference)

    def by_name(self, name: str, idx: int = 0):
        ps = [p for p in self.parts if p.name == name]
        return ps[idx] if len(ps) > idx else None

    @property
    def compound(self) -> Compound:
        return _compound(self.parts, 0.0)

    def exploded(self, gap: float) -> Compound:
        return _compound(self.parts, gap)

    def part_solids(self, gap: float = 0.0) -> list[tuple[PartInfo, Part]]:
        out = []
        for p in self.parts:
            s = p.solid
            if gap > 0 and any(abs(e) > 1e-9 for e in p.explode):
                s = Pos(p.explode[0] * gap, p.explode[1] * gap, p.explode[2] * gap) * s
            out.append((p, s))
        return out


def _compound(parts: list[PartInfo], gap: float) -> Compound:
    kids = []
    for p in parts:
        s = p.solid
        if gap > 0 and any(abs(e) > 1e-9 for e in p.explode):
            s = Pos(p.explode[0] * gap, p.explode[1] * gap, p.explode[2] * gap) * s
        try:
            s.label = p.name
        except Exception:
            pass
        kids.append(s)
    comp = Compound(children=kids)
    comp.label = "power_train"
    return comp


# ── Basic shape helpers (all world coordinates, shaft = X) ───
def cyl_x(x0: float, x1: float, r: float, y: float = 0.0, z: float = 0.0) -> Part:
    """Cylinder along X from x0 to x1."""
    return Pos((x0 + x1) / 2.0, y, z) * Rot(0, 90, 0) * Cylinder(radius=r, height=(x1 - x0))


def ring_x(x0: float, x1: float, r_out: float, r_in: float, y: float = 0.0, z: float = 0.0) -> Part:
    return cyl_x(x0, x1, r_out, y, z) - cyl_x(x0 - 0.5, x1 + 0.5, r_in, y, z)


def shaft_keyway_cutter(xc: float, L: float, b: float, z_bottom: float, y: float = 0.0, up: float = 6.0) -> Part:
    """Round-end (end mill) keyway cutter: bottom at z_bottom, extending up by `up` (past the shaft surface)."""
    return Pos(xc, y, z_bottom) * extrude(SlotOverall(L, b), amount=up)


def hub_keyway_cutter(xc: float, L: float, b: float, z_top: float, y: float = 0.0, down: float = 6.0) -> Part:
    """Hub keyway (through rectangular slot): top at z_top (= bore radius + t2), extending down by `down`. Cut well
    below t2 into the bore, because the bore arc sags below the slot edges."""
    return Pos(xc, y, z_top - down / 2.0) * Box(L, b, down)


def key_solid(xc: float, L: float, b: float, h: float, z_bottom: float, y: float = 0.0) -> Part:
    """Parallel key (round ends): bottom at z_bottom."""
    return Pos(xc, y, z_bottom) * extrude(SlotOverall(L, b), amount=h)


def bearing_solid(bs: S.BearingSpec, x0: float, y: float, z: float, n_balls: int = 8) -> Part:
    """Inner ring + outer ring + balls (simplified, no raceway; balls slightly embedded in the rings), fused into 1 solid."""
    pr = bs.pitch_d / 2.0
    br = bs.ball_d / 2.0
    ri_o = pr - br * 0.9           # Inner ring outer radius (balls embedded 10%)
    ro_i = pr + br * 0.9           # Outer ring inner radius
    inner = ring_x(x0, x0 + bs.B, ri_o, bs.d / 2.0, y, z)
    outer = ring_x(x0, x0 + bs.B, bs.D / 2.0, ro_i, y, z)
    body = inner + outer
    xc = x0 + bs.B / 2.0
    from build123d import Sphere
    for i in range(n_balls):
        a = 2 * math.pi * i / n_balls
        body = body + Pos(xc, y + pr * math.cos(a), z + pr * math.sin(a)) * Sphere(radius=br)
    return body


def retaining_ring_solid(rs: S.RingSpec, x0: float, y: float, z: float) -> Part:
    """C-type retaining ring (installed: inner diameter = groove diameter d2, thickness t), opening facing down (-Z)."""
    r_in = rs.d2 / 2.0
    r_out = r_in + rs.b
    body = Cylinder(radius=r_out, height=rs.t) - Cylinder(radius=r_in, height=rs.t + 1)
    body = body - Pos(0, 0, -rs.t / 2.0 - 0.1) * Rot(0, 0, -90) * _wedge_cutter(r_out + 1, rs.t + 0.2, 50)   # C shape with the opening at the bottom
    return Pos(x0 + rs.t / 2.0, y, z) * Rot(0, 90, 0) * body


def gear_solid(z: int, m: float, width: float, bore: float, xc: float, y: float, zc: float, rot_deg: float) -> Part:
    """Involute spur gear, axis = X, with one tooth pointing toward rot_deg (90 = +Y)."""
    pts = involute_gear_outline(z, m, n_flank=(8 if z <= 60 else 5 if z <= 120 else 3))
    body = extrude(Polygon(*pts, align=None), amount=width)
    body = body - Pos(0, 0, width / 2.0) * Cylinder(radius=bore / 2.0, height=width + 2)
    body = Pos(0, 0, -width / 2.0) * body
    return Pos(xc, y, zc) * Rot(0, 90, 0) * Rot(0, 0, rot_deg) * body


def pulley_solid(gs: S.GrooveSpec, grooves: int, width: float, bore: float, xc: float, y: float, zc: float) -> Part:
    """V-belt pulley (solid disc + n trapezoidal grooves at pitch e), axis = X."""
    R = gs.od / 2.0
    body = Cylinder(radius=R, height=width)
    depth = gs.depth
    half_top = gs.w1 / 2.0
    half_bot = max(half_top - depth * math.tan(math.radians(gs.alpha / 2.0)), 0.6)
    z0 = -(grooves - 1) * gs.e / 2.0
    for i in range(grooves):
        zc_g = z0 + i * gs.e
        prof = Plane.XZ * Polygon((R - depth, zc_g - half_bot), (R + 1.0, zc_g - half_top - 1.0 * math.tan(math.radians(gs.alpha / 2.0))),
                                  (R + 1.0, zc_g + half_top + 1.0 * math.tan(math.radians(gs.alpha / 2.0))), (R - depth, zc_g + half_bot), align=None)
        body = body - revolve(prof, axis=Axis_Z())
    body = body - Cylinder(radius=bore / 2.0, height=width + 2)
    return Pos(xc, y, zc) * Rot(0, 90, 0) * body


def Axis_Z():
    from build123d import Axis
    return Axis.Z


def hex_bolt_x(f, x_head: float, y: float, z: float, grip: float, direction: int) -> Part:
    """Hex bolt: head bearing face at x_head, shank extending grip along direction (+1: into +X, -1: into -X)."""
    shaft = Pos(0, 0, -grip / 2.0) * Cylinder(radius=f.nominal_dia_mm / 2.0, height=grip)
    head = extrude(RegularPolygon(radius=f.head_across_corners_mm / 2.0, side_count=6), amount=f.head_height_mm)
    bolt = shaft + head                    # Head z 0..hh, shank -grip..0 (local Z)
    rot = Rot(0, -90, 0) if direction > 0 else Rot(0, 90, 0)   # Local -Z (shank) → +X or -X
    return Pos(x_head, y, z) * rot * bolt


# ── Layout ──────────────────────────────────────────────────────
def layout_power_train(a) -> dict:
    """Assembly contract → all dimensions and x coordinates (mm). The only place that queries the standards tables."""
    bs = S.bearing(a.bearing)
    d = bs.d                                            # Bearing seat = shaft reference diameter
    if a.shaft_d and abs(a.shaft_d - d) > 1e-6:
        bs = S.bearing_for_shaft(a.shaft_d)             # If the user gave a shaft diameter, use the 62xx with that bore
        d = bs.d
    dsh = bs.da_min                                     # Shaft shoulder = gear seat diameter (within the da range)
    key_p = S.parallel_key(d)                           # Pulley key
    key_g = S.parallel_key(dsh)                         # Gear key
    ring = S.retaining_ring(d)
    m, z1 = float(a.gear_module), int(a.gear_teeth)
    gd = S.gear_dims(m, z1)
    bg = float(a.gear_width) if a.gear_width > 0 else S.gear_face_width(m)
    z2 = int(a.pinion_teeth or 0)
    pd = S.gear_dims(m, z2) if z2 >= 8 else None
    cd = S.center_distance(m, z1, z2) if pd else 0.0
    has_pulley = a.pulley_type != "none"
    gs = S.vpulley_groove(a.pulley_type, a.pulley_dp) if has_pulley else None
    Wp = (float(a.pulley_hub_w) if a.pulley_hub_w > 0 else
          (round(max(1.6 * d, gs.e * (a.pulley_grooves - 1) + 2 * gs.f), 1) if gs else 0.0))
    seal_d = dsh                                        # Oil seal runs on the collar (Ø dsh)
    seal = S.oil_seal(seal_d) if (has_pulley and a.oil_seal) else None
    bolt_name = S.cover_bolt_size(bs.D)
    pcd = S.cover_bolt_pcd(bs.D)
    from ..fasteners.standards import resolve as _resolve
    hub_gap = _resolve(bolt_name)[0].head_height_mm + 2.0      # Keep cover bolt heads clear of the pulley hub
    Wy = pcd + 14.0                                     # Body wall (pedestal) width = cover flange diameter
    Tw = bs.B + LIP + SPIGOT                            # Wall thickness = bearing width + shoulder + cover spigot

    # X coordinates (left to right). Shaft left end x=0.
    x = 0.0
    stub = ring.n + 0.5
    xg1 = x + stub                                      # Retaining ring groove 1 [xg1, xg1+m]
    xp0 = xg1 + ring.m if has_pulley else None          # Pulley hub left face
    if has_pulley:
        x_hub_end = xp0 + Wp
        x_cov1_out = x_hub_end + hub_gap                # Cover 1 outer face (bolt head + 2 clearance)
        x_w1_0 = x_cov1_out + COVER_T                   # Wall 1 outer face = cover flange inner face
        xb1 = x_w1_0 + SPIGOT                           # Bearing 1 left face
        collar = (x_hub_end, xb1)                       # Collar (Ø d / Ø dsh)
    else:
        x_cov1_out = xg1 + ring.m + 0.5 - COVER_T       # Without a pulley the left side also gets a blind cover; the shaft end stays inside the spigot
        x_w1_0 = x_cov1_out + COVER_T
        xb1 = x_w1_0 + SPIGOT
        collar = None
        # Retaining ring just outside the bearing 1 left face
        xg1 = xb1 - ring.m
        x = xg1 - stub
    x_w1_1 = xb1 + bs.B + LIP                           # Wall 1 inner face
    x_sp1 = xb1 + bs.B                                  # Spacer 1
    x_gear = x_sp1 + SPACER_L                           # Gear left face
    x_sp2 = x_gear + bg
    xb2 = x_sp2 + SPACER_L                              # Bearing 2 left face
    x_w2_0 = xb2 - LIP                                  # Wall 2 inner face
    x_w2_1 = xb2 + bs.B + SPIGOT                        # Wall 2 outer face
    xg2 = xb2 + bs.B                                    # Retaining ring groove 2
    x_end = xg2 + ring.m + 1.0                          # Shaft right end (stays inside the spigot recess)
    x_cov2_out = x_w2_1 + COVER_T

    z_axis = BASE_T + max(gd.da / 2.0 + Z_AXIS_MIN_CLEAR, Wy / 2.0 + 2.0, (pd.da / 2.0 + Z_AXIS_MIN_CLEAR) if pd else 0)
    if gs:
        z_axis = max(z_axis, gs.od / 2.0 + 3.0)         # Keep the pulley above the mounting surface (z=0)
    ys = [0.0] + ([cd] if pd else [])
    base_x0 = x_w1_0 - 8.0
    base_x1 = x_w2_1 + 8.0
    base_y0 = -max(Wy / 2.0, gd.da / 2.0 + 6.0)
    base_y1 = (cd if pd else 0.0) + max(Wy / 2.0, (pd.da if pd else gd.da) / 2.0 + 6.0)
    return dict(
        bearing=bs, d=d, dsh=dsh, key_p=key_p, key_g=key_g, ring=ring, gear=gd, gear_w=bg, pinion=pd, center_distance=cd,
        groove=gs, pulley_w=Wp, grooves=int(a.pulley_grooves), seal=seal, bolt=bolt_name, pcd=pcd, Wy=Wy, Tw=Tw,
        x0=x, xg1=xg1, xp0=xp0, collar=collar, x_cov1_out=x_cov1_out, x_w1_0=x_w1_0, xb1=xb1, x_w1_1=x_w1_1,
        x_sp1=x_sp1, x_gear=x_gear, x_sp2=x_sp2, xb2=xb2, x_w2_0=x_w2_0, x_w2_1=x_w2_1, xg2=xg2, x_end=x_end,
        x_cov2_out=x_cov2_out, z_axis=z_axis, ys=ys, base=(base_x0, base_x1, base_y0, base_y1),
        has_pulley=has_pulley, spacer_od=round(dsh + 7.0, 1), collar_od=dsh,
    )


# ── Part generation ───────────────────────────────────────────────
def _shaft_x(L: dict, with_pulley: bool) -> tuple[float, float]:
    """(shaft left end x0, retaining ring groove 1 start xg1). Without a pulley the groove sits just left of bearing 1."""
    ring = L["ring"]
    if with_pulley:
        return L["x0"], L["xg1"]
    xg1 = L["xb1"] - ring.m
    return xg1 - (ring.n + 0.5), xg1


def _shaft(L: dict, y: float, with_pulley: bool) -> Part:
    """Stepped shaft: revolve a half-section polyline about the X axis (1 solid in one go), then cut retaining ring grooves and keyways."""
    from build123d import Axis
    d, dsh, bs, ring = L["d"], L["dsh"], L["bearing"], L["ring"]
    z = L["z_axis"]
    x0, xg1 = _shaft_x(L, with_pulley)
    xa, xb = L["xb1"] + bs.B, L["xb2"]                    # Shoulder (Ø dsh) section = bearing 1 right face to bearing 2 left face
    pts = [(x0, 0.0), (x0, d / 2.0), (xa, d / 2.0), (xa, dsh / 2.0), (xb, dsh / 2.0), (xb, d / 2.0),
           (L["x_end"], d / 2.0), (L["x_end"], 0.0)]
    s = revolve(Plane.XZ * Polygon(*pts, align=None), axis=Axis.X)
    s = Pos(0, y, z) * s
    for xg in (xg1, L["xg2"]):                             # 2 retaining ring grooves
        s = s - ring_x(xg, xg + ring.m, d / 2.0 + 1.0, ring.d2 / 2.0, y, z)
    kg = L["key_g"]; bg = L["gear_w"]                      # Gear keyway (+Z)
    s = s - shaft_keyway_cutter(L["x_gear"] + bg / 2.0, bg - 4.0, kg.b, z + dsh / 2.0 - kg.t1, y)
    if with_pulley:
        kp = L["key_p"]; Wp = L["pulley_w"]
        s = s - shaft_keyway_cutter(L["xp0"] + Wp / 2.0, Wp - 4.0, kp.b, z + d / 2.0 - kp.t1, y)
    return s


def _housing(L: dict) -> Part:
    bs = L["bearing"]; z = L["z_axis"]; Wy = L["Wy"]
    bx0, bx1, by0, by1 = L["base"]
    base = Pos((bx0 + bx1) / 2.0, (by0 + by1) / 2.0, BASE_T / 2.0) * Box(bx1 - bx0, by1 - by0, BASE_T)
    ys = L["ys"]
    y_lo, y_hi = min(ys) - Wy / 2.0, max(ys) + Wy / 2.0
    body = base
    for (xa, xb) in ((L["x_w1_0"], L["x_w1_1"]), (L["x_w2_0"], L["x_w2_1"])):
        wall = Pos((xa + xb) / 2.0, (y_lo + y_hi) / 2.0, z / 2.0) * Box(xb - xa, y_hi - y_lo, z)
        for yc in ys:                                   # Rounded top (plummer block)
            wall = wall + cyl_x(xa, xb, Wy / 2.0, yc, z)
        if len(ys) > 1:                                 # With two shafts, fill the space between them flat
            wall = wall + Pos((xa + xb) / 2.0, (ys[0] + ys[1]) / 2.0, z + Wy / 4.0) * Box(xb - xa, ys[1] - ys[0], Wy / 2.0)
        body = body + wall
    # Bearing bore (Ø D) + inner shoulder (Ø Da_max)
    for yc in ys:
        body = body - cyl_x(L["x_w1_0"] - 1, L["xb1"] + bs.B, bs.D / 2.0, yc, z)
        body = body - cyl_x(L["x_w1_0"] - 1, L["x_w1_1"] + 1, bs.Da_max / 2.0, yc, z)
        body = body - cyl_x(L["xb2"], L["x_w2_1"] + 1, bs.D / 2.0, yc, z)
        body = body - cyl_x(L["x_w2_0"] - 1, L["x_w2_1"] + 1, bs.Da_max / 2.0, yc, z)
    # Cover bolt tapped holes, depth 12 (modeled at nominal diameter, no threads)
    from ..fasteners.standards import resolve
    f = resolve(L["bolt"])[0]
    for (yc, zc) in _cover_bolt_points(L):
        body = body - cyl_x(L["x_w1_0"] - 1, L["x_w1_0"] + 12.0, f.nominal_dia_mm / 2.0, yc, zc)
        body = body - cyl_x(L["x_w2_1"] - 12.0, L["x_w2_1"] + 1, f.nominal_dia_mm / 2.0, yc, zc)
    # 4 base mounting bolt holes (M8 clearance Ø9)
    for sx in (bx0 + 10.0, bx1 - 10.0):
        for sy in (by0 + 10.0, by1 - 10.0):
            body = body - Pos(sx, sy, BASE_T / 2.0) * Cylinder(radius=4.5, height=BASE_T + 2)
    return body


def _cover_bolt_points(L: dict) -> list[tuple[float, float]]:
    """List of cover bolt (y, z). One shaft: 4 on the PCD (45 degree spacing). Two shafts: 6 around the perimeter."""
    z = L["z_axis"]; r = L["pcd"] / 2.0; ys = L["ys"]
    if len(ys) == 1:
        return [(r * math.cos(math.radians(a)), z + r * math.sin(math.radians(a))) for a in (45, 135, 225, 315)]
    pts = []
    for yc in ys:
        for a in (45, 135, 225, 315):
            pts.append((yc + r * math.cos(math.radians(a)), z + r * math.sin(math.radians(a))))
    # The 4 inner holes between the two shafts are too close, so keep only the outer ones (2 outer per shaft + 2 at top/bottom middle)
    out = [p for p in pts if (p[0] < ys[0] + 1 or p[0] > ys[1] - 1)]
    ym = (ys[0] + ys[1]) / 2.0
    out += [(ym, z + r), (ym, z - r)]
    return out


def _cover(L: dict, side: int, y_list: list[float]) -> Part:
    """Cover. side=-1 left (oil seal, through), +1 right (blind). With two shafts, one plate covers both bores."""
    bs = L["bearing"]; z = L["z_axis"]; Wy = L["Wy"]
    from ..fasteners.standards import resolve
    f = resolve(L["bolt"])[0]
    if side < 0:
        x_out, x_in = L["x_cov1_out"], L["x_w1_0"]
        x_sp0, x_sp1 = L["x_w1_0"], L["xb1"]
    else:
        x_in, x_out = L["x_w2_1"], L["x_cov2_out"]
        x_sp0, x_sp1 = L["xb2"] + bs.B, L["x_w2_1"]
    xa, xb = min(x_out, x_in), max(x_out, x_in)
    if len(y_list) == 1:
        body = cyl_x(xa, xb, Wy / 2.0, y_list[0], z)                      # Round flange
    else:
        y_lo, y_hi = min(y_list) - Wy / 2.0, max(y_list) + Wy / 2.0
        body = Pos((xa + xb) / 2.0, (y_lo + y_hi) / 2.0, (BASE_T + 2.0 + z + Wy / 2.0) / 2.0) * \
            Box(xb - xa, y_hi - y_lo, (z + Wy / 2.0) - (BASE_T + 2.0))
    for yc in y_list:
        body = body + ring_x(x_sp0, x_sp1, bs.D / 2.0, bs.Da_max / 2.0, yc, z)   # Spigot + outer ring stop shoulder
        if side > 0 or not L["has_pulley"] or yc != 0.0:
            # Blind: pocket for the shaft end (Ø d+6, depth 3 into the flange)
            if side > 0:
                body = body - cyl_x(x_in - 1.0, x_in + 3.0, (L["d"] + 6.0) / 2.0, yc, z)
            else:
                body = body - cyl_x(x_in - 3.0, x_in + 1.0, (L["d"] + 6.0) / 2.0, yc, z)
        else:
            # Through + oil seal seat
            body = body - cyl_x(xa - 1, xb + 1, (L["collar_od"] + 1.0) / 2.0, yc, z)
            if L["seal"]:
                body = body - cyl_x(xa - 1, xa + L["seal"].b, L["seal"].D / 2.0, yc, z)
    for (yc, zc) in _cover_bolt_points(L):
        body = body - cyl_x(xa - 1, xb + 1, f.clearance("normal") / 2.0, yc, zc)
    return body


def build_power_train(a) -> Assembly:
    L = layout_power_train(a)
    bs, d, dsh, z, ring = L["bearing"], L["d"], L["dsh"], L["z_axis"], L["ring"]
    gd, bg, kg = L["gear"], L["gear_w"], L["key_g"]
    parts: list[PartInfo] = []
    no = [0]

    def add(name, solid, spec="", qty=1, material="", explode=(0, 0, 0), group=""):
        no[0] += 1
        parts.append(PartInfo(name, solid, spec, qty, material, explode, group or name.split()[0], no[0]))

    # 1 Body
    if a.housing:
        add("본체", _housing(L), f"베어링 구멍 Ø{bs.D:g} H7 ×{2 * len(L['ys'])}, 턱 Ø{bs.Da_max:g}, 커버 볼트 {L['bolt']}", 1, "GC200", (0, 0, -1.0))
    # 2 Shaft (main)
    add("축", _shaft(L, 0.0, L["has_pulley"]),
        f"Ø{d:g} 베어링 자리 ×2 (k5), 턱 Ø{dsh:g}, 기어 자리 Ø{dsh:g} h6 키홈 {kg.name}, 멈춤링 홈 Ø{ring.d2:g}×{ring.m:g} ×2"
        + (f", 풀리 자리 Ø{d:g} 키홈 {L['key_p'].name}" if L["has_pulley"] else ""), 1, "SM45C", (0, 0, 0))
    # 3 Spur gear + key
    xgc = L["x_gear"] + bg / 2.0
    gear = gear_solid(gd.z, gd.m, bg, dsh, xgc, 0.0, z, 90.0)
    gear = gear - hub_keyway_cutter(xgc, bg + 2.0, kg.b, z + dsh / 2.0 + kg.t2, 0.0)
    add("스퍼기어", gear, f"m{gd.m:g} z{gd.z} 압력각 20도, PCD Ø{gd.d:g}, 이끝원 Ø{gd.da:g}, 이폭 {bg:g}, 보어 Ø{dsh:g} H7, 키홈 {kg.b:g}×{kg.t2:g}",
        1, "SC49", (0, 0, 1.6), "기어")
    add("평행키(기어)", key_solid(xgc, bg - 4.0, kg.b, kg.h, z + dsh / 2.0 - kg.t1), f"{kg.name}×{bg - 4:g} KS B 1311, t1 {kg.t1:g} t2 {kg.t2:g}", 1, "SM45C", (0, 0, 2.4), "키")
    # 4 Spacers (2)
    sp = ring_x(L["x_sp1"], L["x_sp1"] + SPACER_L, L["spacer_od"] / 2.0, dsh / 2.0, 0.0, z) + \
        ring_x(L["x_sp2"], L["x_sp2"] + SPACER_L, L["spacer_od"] / 2.0, dsh / 2.0, 0.0, z)
    add("스페이서", sp, f"Ø{L['spacer_od']:g}/Ø{dsh:g}×{SPACER_L:g} (기어 축 방향 위치)", 2, "SM45C", (0, 0, 1.0), "스페이서")
    # 5 Bearings (2)
    b1 = bearing_solid(bs, L["xb1"], 0.0, z); b2 = bearing_solid(bs, L["xb2"], 0.0, z)
    add("볼베어링", b1, f"{bs.code} (d{bs.d:g} D{bs.D:g} B{bs.B:g}) KS B 2023", 1, "", (-1.0, 0, 0), "베어링")
    add("볼베어링", b2, f"{bs.code} (d{bs.d:g} D{bs.D:g} B{bs.B:g}) KS B 2023", 1, "", (1.0, 0, 0), "베어링")
    # 6 Retaining rings (2)
    if a.rings:
        r1 = retaining_ring_solid(ring, L["xg1"] + ring.m - ring.t, 0.0, z)     # In the groove, pressed against the hub side
        r2 = retaining_ring_solid(ring, L["xg2"], 0.0, z)                        # In the groove, pressed against the bearing 2 inner ring
        add("멈춤링(C형)", r1, f"축용 {ring.d1:g} KS B 1336, 홈 Ø{ring.d2:g}×{ring.m:g}", 1, "SK5", (-4.0, 0, 0), "멈춤링")
        add("멈춤링(C형)", r2, f"축용 {ring.d1:g} KS B 1336, 홈 Ø{ring.d2:g}×{ring.m:g}", 1, "SK5", (1.5, 0, 0), "멈춤링")
    # 7 Pulley + key + collar + oil seal
    if L["has_pulley"]:
        gs, Wp, kp = L["groove"], L["pulley_w"], L["key_p"]
        xpc = L["xp0"] + Wp / 2.0
        pul = pulley_solid(gs, L["grooves"], Wp, d, xpc, 0.0, z)
        pul = pul - hub_keyway_cutter(xpc, Wp + 2.0, kp.b, z + d / 2.0 + kp.t2, 0.0)
        add("V벨트 풀리", pul, f"{gs.belt}형 ×{L['grooves']} PD Ø{gs.dp:g} (외경 Ø{gs.od:g}, 홈 각 {gs.alpha:g}도) KS B 1400, 보어 Ø{d:g} 키홈 {kp.b:g}×{kp.t2:g}",
            1, "GC200", (-3.0, 0, 0), "풀리")
        add("평행키(풀리)", key_solid(xpc, Wp - 4.0, kp.b, kp.h, z + d / 2.0 - kp.t1), f"{kp.name}×{Wp - 4:g} KS B 1311", 1, "SM45C", (-3.0, 0, 1.0), "키")
        c0, c1 = L["collar"]
        add("칼라", ring_x(c0, c1, L["collar_od"] / 2.0, d / 2.0, 0.0, z), f"Ø{L['collar_od']:g}/Ø{d:g}×{c1 - c0:g} (풀리 ↔ 베어링 간격, 오일실 접촉면)", 1, "SM45C", (-1.5, 0, 0), "칼라")
        if L["seal"]:
            se = L["seal"]
            add("오일실", ring_x(L["x_cov1_out"], L["x_cov1_out"] + se.b, se.D / 2.0, se.d / 2.0, 0.0, z), f"{se.name} TC KS B 2804", 1, "NBR", (-2.5, 0, 0), "오일실")
    # 8 Pinion shaft
    if L["pinion"]:
        pdm = L["pinion"]; yp = L["center_distance"]
        rot2 = 90.0 + (180.0 / pdm.z if pdm.z % 2 == 0 else 0.0)
        add("축(피니언)", _shaft(L, yp, False), f"Ø{d:g} 베어링 자리 ×2, 피니언 자리 Ø{dsh:g} 키홈 {kg.name}", 1, "SM45C", (0, 0, 0), "축")
        pin = gear_solid(pdm.z, pdm.m, bg, dsh, xgc, yp, z, rot2)
        pin = pin - hub_keyway_cutter(xgc, bg + 2.0, kg.b, z + dsh / 2.0 + kg.t2, yp)
        add("피니언", pin, f"m{pdm.m:g} z{pdm.z}, PCD Ø{pdm.d:g}, 중심거리 a={yp:g}", 1, "SC49", (0, 0, 1.6), "피니언")
        add("평행키(피니언)", key_solid(xgc, bg - 4.0, kg.b, kg.h, z + dsh / 2.0 - kg.t1, yp), f"{kg.name}×{bg - 4:g} KS B 1311", 1, "SM45C", (0, 0, 2.4), "키")
        sp2 = ring_x(L["x_sp1"], L["x_sp1"] + SPACER_L, L["spacer_od"] / 2.0, dsh / 2.0, yp, z) + \
            ring_x(L["x_sp2"], L["x_sp2"] + SPACER_L, L["spacer_od"] / 2.0, dsh / 2.0, yp, z)
        add("스페이서(피니언)", sp2, f"Ø{L['spacer_od']:g}/Ø{dsh:g}×{SPACER_L:g}", 2, "SM45C", (0, 0, 1.0), "스페이서")
        add("볼베어링", bearing_solid(bs, L["xb1"], yp, z), f"{bs.code} KS B 2023", 1, "", (-1.0, 0, 0), "베어링")
        add("볼베어링", bearing_solid(bs, L["xb2"], yp, z), f"{bs.code} KS B 2023", 1, "", (1.0, 0, 0), "베어링")
        if a.rings:
            _x0p, _xg1p = _shaft_x(L, False)
            add("멈춤링(C형)", retaining_ring_solid(ring, _xg1p + ring.m - ring.t, yp, z), f"축용 {ring.d1:g}", 1, "SK5", (-1.5, 0, 0), "멈춤링")
            add("멈춤링(C형)", retaining_ring_solid(ring, L["xg2"], yp, z), f"축용 {ring.d1:g}", 1, "SK5", (1.5, 0, 0), "멈춤링")
    # 9 Covers + bolts
    if a.covers:
        ys = L["ys"]
        add("커버(왼)", _cover(L, -1, ys), f"플랜지 Ø{L['Wy']:g}×{COVER_T:g}, 끼움부 Ø{bs.D:g}×{SPIGOT:g}, 턱 Ø{bs.Da_max:g}" + (f", 오일실 자리 Ø{L['seal'].D:g}×{L['seal'].b:g}" if L["seal"] else ""),
            1, "GC200", (-2.0, 0, 0), "커버")
        add("커버(오른)", _cover(L, 1, ys), f"플랜지 Ø{L['Wy']:g}×{COVER_T:g}, 끼움부 Ø{bs.D:g}×{SPIGOT:g}, 블라인드", 1, "GC200", (2.0, 0, 0), "커버")
        if a.bolts:
            from ..fasteners.standards import resolve, std_length
            f = resolve(L["bolt"])[0]
            grip = COVER_T + 10.0
            pts = _cover_bolt_points(L)
            bl = Compound(children=[hex_bolt_x(f, L["x_cov1_out"], yc, zc, grip, +1) for yc, zc in pts])
            br = Compound(children=[hex_bolt_x(f, L["x_cov2_out"], yc, zc, grip, -1) for yc, zc in pts])
            Lstd = std_length(f, grip)
            add("육각볼트(왼 커버)", bl, f"{f.name}×{Lstd:g} KS B 1002 ×{len(pts)}", len(pts), "SCM435", (-2.6, 0, 0), "볼트")
            add("육각볼트(오른 커버)", br, f"{f.name}×{Lstd:g} KS B 1002 ×{len(pts)}", len(pts), "SCM435", (2.6, 0, 0), "볼트")

    mates = _mates(L, a)
    bom = [{"no": p.no, "item": p.name, "spec": p.spec, "qty": p.qty, "material": p.material} for p in parts]
    pub = _layout_public(L)
    pub["fits"] = _fits_power_train(L, parts)
    return Assembly(parts, pub, mates, bom)


def fit(desc, pa, pb, r, lo, hi, c, axis="X"):
    """Fit pairs for A2: two part numbers, radius, axial range [lo,hi], axis center c ((y,z) for an X axis, (x,y) for a Z axis)."""
    return {"desc": desc, "a": pa.no, "b": pb.no, "r": float(r), "lo": float(lo), "hi": float(hi), "c": [float(c[0]), float(c[1])], "axis": axis}


def _fits_power_train(L: dict, parts: list) -> list[dict]:
    bs, d, dsh, z = L["bearing"], L["d"], L["dsh"], L["z_axis"]
    def P(name, idx=0):
        ps = [p for p in parts if p.name == name]
        return ps[idx] if len(ps) > idx else None
    out = []
    hs = P("본체")
    for yi, y in enumerate(L["ys"]):
        shaft = P("축") if yi == 0 else P("축(피니언)")
        brs = [p for p in parts if p.name == "볼베어링" and abs(p.solid.bounding_box().center().Y - y) < 1.0]
        for bx, br in zip((L["xb1"], L["xb2"]), brs):
            if shaft: out.append(fit(f"베어링 내경 Ø{d:g} ↔ 축 자리", br, shaft, d / 2, bx, bx + bs.B, (y, z)))
            if hs: out.append(fit(f"베어링 외경 Ø{bs.D:g} ↔ 본체 구멍", br, hs, bs.D / 2, bx, bx + bs.B, (y, z)))
        gear = P("스퍼기어") if yi == 0 else P("피니언")
        if gear and shaft: out.append(fit(f"기어 보어 Ø{dsh:g} ↔ 축 자리", gear, shaft, dsh / 2, L["x_gear"], L["x_gear"] + L["gear_w"], (y, z)))
        if yi == 0 and L["has_pulley"] and P("V벨트 풀리") and shaft:
            out.append(fit(f"풀리 보어 Ø{d:g} ↔ 축 자리", P("V벨트 풀리"), shaft, d / 2, L["xp0"], L["xp0"] + L["pulley_w"], (y, z)))
        for cv, (x0, x1) in ((P("커버(왼)"), (L["x_w1_0"], L["xb1"])), (P("커버(오른)"), (L["xb2"] + bs.B, L["x_w2_1"]))):
            if cv and hs: out.append(fit(f"커버 끼움부 Ø{bs.D:g} ↔ 본체 구멍", cv, hs, bs.D / 2, x0, x1, (y, z)))
    return out


def _layout_public(L: dict) -> dict:
    bs = L["bearing"]; gd = L["gear"]
    out = {
        "shaft_d": L["d"], "shoulder_d": L["dsh"], "bearing": bs.code, "bearing_dDB": [bs.d, bs.D, bs.B],
        "da_range": [bs.da_min, bs.da_max], "Da_max": bs.Da_max,
        "gear": {"m": gd.m, "z": gd.z, "d": gd.d, "da": gd.da, "df": round(gd.df, 2), "width": L["gear_w"]},
        "key_gear": L["key_g"].name, "key_pulley": (L["key_p"].name if L["has_pulley"] else None),
        "ring": {"d2": L["ring"].d2, "m": L["ring"].m, "t": L["ring"].t},
        "seal": (L["seal"].name if L["seal"] else None),
        "pulley": ({"type": L["groove"].belt, "dp": L["groove"].dp, "od": L["groove"].od, "alpha": L["groove"].alpha, "width": L["pulley_w"]} if L["groove"] else None),
        "cover_bolt": L["bolt"], "pcd": L["pcd"], "z_axis": L["z_axis"], "shaft_length": round(L["x_end"] - L["x0"], 2),
        "x": {k: round(L[k], 2) for k in ("xb1", "xb2", "x_gear", "x_w1_0", "x_w1_1", "x_w2_0", "x_w2_1", "x_end", "xg1", "xg2") if L.get(k) is not None},
        "ys": L["ys"], "center_distance": L["center_distance"],
        "pinion": ({"z": L["pinion"].z, "d": L["pinion"].d, "da": L["pinion"].da} if L["pinion"] else None),
    }
    if L["has_pulley"]:
        out["x"]["xp0"] = round(L["xp0"], 2); out["collar"] = [round(L["collar"][0], 2), round(L["collar"][1], 2)]
    return out


def _mates(L: dict, a) -> list[dict]:
    bs, d, dsh, kg, ring = L["bearing"], L["d"], L["dsh"], L["key_g"], L["ring"]
    m = []
    m.append({"id": "M1", "pair": "베어링 내륜 ↔ 축 베어링 자리", "type": "동심 + 측면 접촉",
              "detail": f"자리 Ø{d:g} = 내경 Ø{bs.d:g}, 턱 Ø{dsh:g} (da {bs.da_min:g}~{bs.da_max:g})", "ok": bs.da_min - 1e-6 <= dsh <= bs.da_max + 1e-6})
    m.append({"id": "M2", "pair": "베어링 외륜 ↔ 본체 구멍", "type": "동심 + 측면 접촉",
              "detail": f"구멍 Ø{bs.D:g} H7 = 외경, 턱 Ø{bs.Da_max:g} ≤ Da max {bs.Da_max:g}", "ok": a.housing})
    m.append({"id": "M3", "pair": "기어 보어 ↔ 축 기어 자리", "type": "동심 + 키홈 각도 정렬 + 측면 접촉(스페이서)",
              "detail": f"보어 Ø{dsh:g} H7 / h6, 키홈 {kg.b:g} 폭 +Z 정렬, 스페이서 {SPACER_L:g} 양쪽", "ok": True})
    m.append({"id": "M4", "pair": "평행키 ↔ 축 키홈", "type": "폭 면 접촉 2 + 바닥 접촉",
              "detail": f"키 {kg.name}, t1 {kg.t1:g} + t2 {kg.t2:g} - h {kg.h:g} = 윗틈 {kg.top_clearance:g}", "ok": kg.top_clearance >= 0.1})
    if L["has_pulley"]:
        kp, gs = L["key_p"], L["groove"]
        m.append({"id": "M5", "pair": "V풀리 ↔ 축 풀리 자리", "type": "동심 + 키홈 정렬 + 측면 접촉(칼라/멈춤링)",
                  "detail": f"보어 Ø{d:g}, 키 {kp.name}, 허브 폭 {L['pulley_w']:g}, {gs.belt}형 PD{gs.dp:g}", "ok": True})
    if a.covers:
        m.append({"id": "M6", "pair": "커버 ↔ 본체", "type": "동심(끼움부) + 플랜지 면 접촉 + 볼트 패턴",
                  "detail": f"끼움 Ø{bs.D:g}×{SPIGOT:g}, 볼트 {L['bolt']} PCD {L['pcd']:g}", "ok": True})
    if a.rings:
        m.append({"id": "M7", "pair": "멈춤링 ↔ 축 홈", "type": "동심 + 홈 안 위치",
                  "detail": f"홈 Ø{ring.d2:g}×{ring.m:g}, 링 t {ring.t:g} < m, 끝 거리 ≥ n {ring.n:g}", "ok": ring.t < ring.m})
    if L["seal"]:
        se = L["seal"]
        m.append({"id": "M8", "pair": "오일실 ↔ 커버 구멍 / 칼라", "type": "동심 + 자리 바닥 접촉",
                  "detail": f"{se.name}: 커버 자리 Ø{se.D:g}, 칼라 Ø{L['collar_od']:g}", "ok": abs(se.d - L["collar_od"]) < 1e-6})
    if L["pinion"]:
        pdm, gd = L["pinion"], L["gear"]
        m.append({"id": "M9", "pair": "기어 쌍 ↔ 본체 두 구멍", "type": "평행 + 중심거리",
                  "detail": f"a = m(z1+z2)/2 = {L['center_distance']:g}, 이끝원 Ø{gd.da:g} + Ø{pdm.da:g}", "ok": True})
    return m
