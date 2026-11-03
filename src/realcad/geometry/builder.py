"""Build part and bolt solids with build123d.

Coordinate convention: part top face = z=0. Bolts go in from above, so the head is at z>0 (above the top face) and the shank at z<0 (in the material).
"""
from __future__ import annotations
import math
from build123d import (
    Part, Box, Cylinder, Sphere, Pos, Rot, RegularPolygon, Circle,
    Polygon, RectangleRounded, extrude, Plane,
)
from ..fasteners.standards import Fastener


def plate(length: float, width: float, thickness: float) -> Part:
    """Plate with its top face at z=0 (extends down by the thickness)."""
    return Pos(0, 0, -thickness / 2) * Box(length, width, thickness)


def drill(part: Part, x: float, y: float, dia: float, depth: float) -> Part:
    """Cut a through or blind hole downward at (x,y)."""
    cutter = Pos(x, y, -depth / 2 + 0.01) * Cylinder(radius=dia / 2, height=depth + 0.1)
    return part - cutter


def wall(x: float, width: float, height: float, thickness: float) -> Part:
    """Wall standing up from the plate top face (z=0). Position x, width along y, height along z."""
    return Pos(x, 0, height / 2) * Box(thickness, width, height)


def hex_bolt_solid(f: Fastener, grip_mm: float) -> Part:
    """Hex bolt solid. Head z 0..head_height, shank -grip..0."""
    shaft = Pos(0, 0, -grip_mm / 2) * Cylinder(radius=f.nominal_dia_mm / 2, height=grip_mm)
    hexa = RegularPolygon(radius=f.head_across_corners_mm / 2, side_count=6)
    head = extrude(hexa, amount=f.head_height_mm)  # +Z relative to Plane.XY
    return Part() + shaft + head


def place(solid: Part, x: float, y: float) -> Part:
    return Pos(x, y, 0) * solid


def build_container(cc) -> Part:
    """Tub/cup/box: bottom z=0, wall + floor thickness, open-top container. Sits directly on the grid."""
    ih = max(cc.height - cc.base, 1.0)
    if cc.shape == "box":
        outer = Pos(0, 0, cc.height / 2) * Box(cc.length, cc.width, cc.height)
        inner = Pos(0, 0, cc.base + ih / 2 + 0.1) * Box(
            max(cc.length - 2 * cc.wall, 1), max(cc.width - 2 * cc.wall, 1), ih + 0.2)
        part = outer - inner
        if cc.dividers and cc.dividers > 0:
            step = cc.length / (cc.dividers + 1)
            for i in range(1, cc.dividers + 1):
                part = part + Pos(-cc.length / 2 + step * i, 0, cc.base + ih / 2) * \
                    Box(cc.wall, cc.width - 2 * cc.wall, ih)
    else:
        outer = Pos(0, 0, cc.height / 2) * Cylinder(radius=cc.outer_d / 2, height=cc.height)
        inner = Pos(0, 0, cc.base + ih / 2 + 0.1) * Cylinder(
            radius=max(cc.outer_d / 2 - cc.wall, 0.5), height=ih + 0.2)
        part = outer - inner
    return part


def involute_gear_outline(z: int, m: float, pressure_deg: float = 20.0, backlash: float = 0.05,
                          n_flank: int = 8) -> list[tuple[float, float]]:
    """Point list of the involute spur gear outer outline (one revolution, simple polygon).
    Standard profile: addendum 1.0m, dedendum 1.25m, pressure angle 20°. Tooth thickness is reduced by backlash (×m) so it meshes at the theoretical center distance."""
    a = math.radians(pressure_deg)
    rp = m * z / 2.0                      # Pitch circle
    rb = rp * math.cos(a)                 # Base circle
    ra = rp + m                           # Tip circle
    rf = max(rp - 1.25 * m, 0.3 * m)      # Root circle
    inv = lambda t: math.tan(t) - t
    half_t = (math.pi * m / 2.0 - backlash * m) / 2.0 / rp     # Half tooth thickness angle at the pitch circle
    theta0 = half_t + inv(a)                                     # Half angle from the base circle to the tooth centerline
    pitch = 2 * math.pi / z
    r_lo = max(rb, rf)
    t_lo = math.sqrt((r_lo / rb) ** 2 - 1.0) if r_lo > rb else 0.0
    t_hi = math.sqrt((ra / rb) ** 2 - 1.0)
    # Flank (radius, half angle from centerline): base/root → tip
    flank = []
    for k in range(n_flank + 1):
        t = t_lo + (t_hi - t_lo) * k / n_flank
        r = rb * math.sqrt(1 + t * t)
        half = theta0 - inv(t)
        flank.append((r, max(half, 0.0)))
    if flank[-1][1] <= 1e-4:              # If the tip becomes pointed (few teeth), lower the tip circle slightly
        flank = [(r, h) for r, h in flank if h > 1e-4]
    pts = []
    for i in range(z):
        c = i * pitch
        seq = []
        if rf < rb:                       # Root → base circle, radially (below the right flank)
            seq.append((rf, c - theta0))
        seq += [(r, c - h) for r, h in flank]                    # Right flank ↑
        tip_h = flank[-1][1]
        for k in (1, 2):                                          # Tip arc
            seq.append((ra, c - tip_h + 2 * tip_h * k / 3))
        seq += [(r, c + h) for r, h in reversed(flank)]          # Left flank ↓
        if rf < rb:
            seq.append((rf, c + theta0))
        # Root arc: left end of this tooth → right start of the next tooth
        a0, a1 = c + theta0, c + pitch - theta0
        for k in ((1, 2, 3) if z <= 120 else (2,)):
            seq.append((rf, a0 + (a1 - a0) * k / 4))
        pts += [(r * math.cos(t_), r * math.sin(t_)) for r, t_ in seq]
    return pts


def build_gear(g) -> Part:
    """Involute spur gear: extrude a single outline polygon (one boolean) + bore. Bottom z=0.
    Meshes with a mating gear at the theoretical center distance m(z1+z2)/2 without interference (backlash 0.05m)."""
    z = max(int(g.teeth), 6); m = float(g.module); th = float(g.thickness)
    pts = involute_gear_outline(z, m, n_flank=(8 if z <= 60 else 5 if z <= 120 else 3))
    body = extrude(Polygon(*pts, align=None), amount=th)
    if g.bore and g.bore > 0:
        rf = max(m * z / 2 - 1.25 * m, 0.3 * m)
        bore = min(float(g.bore), 2 * rf - 2 * m)          # Keep the bore from cutting into the tooth roots
        if bore > 0.2:
            body = body - Pos(0, 0, th / 2) * Cylinder(radius=bore / 2, height=th + 1)
    return body


# Board presets (public standard dimensions). holes = screw hole coordinates (mm) relative to the board center. The Pi pattern is asymmetric: 3.5mm from the left edge, 58×49 spacing.
def _centered(l, w, holes):
    return [(round(x - l / 2, 2), round(y - w / 2, 2)) for x, y in holes]


BOARDS = {
    "raspberry_pi_4":    {"l": 85.0, "w": 56.0, "screw": "M2.5", "pilot": 2.2,
                          "holes": _centered(85.0, 56.0, [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)])},
    "raspberry_pi_5":    {"l": 85.0, "w": 56.0, "screw": "M2.5", "pilot": 2.2,
                          "holes": _centered(85.0, 56.0, [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)])},
    "raspberry_pi_3b":   {"l": 85.0, "w": 56.0, "screw": "M2.5", "pilot": 2.2,
                          "holes": _centered(85.0, 56.0, [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)])},
    "raspberry_pi_zero": {"l": 65.0, "w": 30.0, "screw": "M2.5", "pilot": 2.2,
                          "holes": _centered(65.0, 30.0, [(3.5, 3.5), (61.5, 3.5), (3.5, 26.5), (61.5, 26.5)])},
    "arduino_uno":       {"l": 68.6, "w": 53.3, "screw": "M3", "pilot": 2.6,
                          "holes": _centered(68.6, 53.3, [(13.97, 2.54), (15.24, 50.8), (66.04, 7.62), (66.04, 35.56)])},
}
# Connectors, from the public board drawings (±1 mm): (name, side, centre along that edge from the board's lower-left
# corner, connector width, bottom above the board's underside, connector height). Sides: x- x+ y- y+.
_PI_USB_ROW = [("Ethernet / USB", "x+", 28.0, 53.0, 1.6, 16.0)]      # the three stacked connectors sit side by side; their order differs by model
_PI_SD = [("microSD", "x-", 28.0, 12.0, -2.0, 2.0)]
_PORTS = {
    "raspberry_pi_4": _PI_USB_ROW + _PI_SD + [("USB-C", "y-", 11.2, 9.0, 1.6, 3.5), ("HDMI 0", "y-", 26.0, 7.0, 1.6, 3.5),
                                               ("HDMI 1", "y-", 39.5, 7.0, 1.6, 3.5), ("audio", "y-", 54.0, 6.0, 1.6, 6.0)],
    "raspberry_pi_5": _PI_USB_ROW + _PI_SD + [("USB-C", "y-", 11.2, 9.0, 1.6, 3.5), ("HDMI 0", "y-", 25.8, 7.0, 1.6, 3.5),
                                               ("HDMI 1", "y-", 39.2, 7.0, 1.6, 3.5)],
    "raspberry_pi_3b": _PI_USB_ROW + _PI_SD + [("micro USB", "y-", 10.6, 8.0, 1.6, 3.0), ("HDMI", "y-", 32.0, 15.0, 1.6, 6.0),
                                                ("audio", "y-", 53.5, 6.0, 1.6, 6.0)],
    "raspberry_pi_zero": [("microSD", "x-", 16.9, 12.0, -2.0, 2.0), ("mini HDMI", "y-", 12.4, 11.0, 1.6, 3.5),
                          ("USB", "y-", 41.4, 8.0, 1.6, 3.0), ("power", "y-", 54.0, 8.0, 1.6, 3.0)],
    "arduino_uno": [("USB", "x-", 38.1, 12.0, 1.6, 11.0), ("power jack", "x-", 7.6, 9.0, 1.6, 11.0)],
}
for _n, _b in BOARDS.items():
    _b["ports"] = _PORTS.get(_n, [])
for _b in BOARDS.values():   # Backward compatibility: dx, dy = bounding size of the hole pattern
    _xs = [h[0] for h in _b["holes"]]; _ys = [h[1] for h in _b["holes"]]
    _b["dx"] = round(max(_xs) - min(_xs), 2); _b["dy"] = round(max(_ys) - min(_ys), 2)


class UnknownBoard(ValueError):
    pass


def board_spec(name: str, e=None) -> dict:
    """Preset board or board="custom" (defined by the contract's board_l/board_w/board_holes)."""
    if name == "custom" and e is not None and e.board_l > 0 and e.board_w > 0:
        from ..fasteners.standards import resolve, insert_spec
        f = resolve(e.board_screw)[0]
        pilot = round(f.nominal_dia_mm - 1.0825 * f.pitch_mm, 2)      # Pilot hole for self-tapping/tapping
        return {"l": e.board_l, "w": e.board_w, "screw": f.name, "pilot": pilot,
                "holes": _centered(e.board_l, e.board_w, [tuple(h) for h in e.board_holes]),
                "dx": 0.0, "dy": 0.0}
    if name not in BOARDS:
        raise UnknownBoard(f"미지원 보드 {name!r}. 지원: {', '.join(BOARDS)} 또는 custom(board_l, board_w, board_holes)")
    return BOARDS[name]


PORT_MARGIN = 1.0      # room on each side of a connector and under it


def port_boxes(e, b: dict) -> list[dict]:
    """Where each connector passes through the case wall, case frame: name, side, centre along the wall, width,
    z range. The case is centred on the board, so these follow the board drawing."""
    so_top = e.base + e.standoff_h
    out = []
    for name, side, along, width, z0, h in b.get("ports") or []:
        half = b["l"] / 2 if side[0] == "y" else b["w"] / 2
        out.append({"name": name, "side": side, "at": along - half, "width": width,
                    "z0": so_top + z0, "z1": so_top + z0 + h})
    return out


def _port_slots(e, b: dict, outer_l: float, outer_w: float, total_h: float) -> list:
    """Slots open at the rim: the board drops in from above, and its connectors stick out past the inner wall.
    Slots with less than 3 mm of wall between them are joined, since a sliver like that would snap off."""
    slots = []
    for side in ("x-", "x+", "y-", "y+"):
        spans = sorted((p["at"] - p["width"] / 2 - PORT_MARGIN, p["at"] + p["width"] / 2 + PORT_MARGIN, p["z0"] - PORT_MARGIN)
                       for p in port_boxes(e, b) if p["side"] == side)
        merged: list = []
        for lo, hi, zb in spans:
            if merged and lo - merged[-1][1] < 3.0:
                merged[-1] = [merged[-1][0], max(merged[-1][1], hi), min(merged[-1][2], zb)]
            else:
                merged.append([lo, hi, zb])
        sign = 1 if side[1] == "+" else -1
        for lo, hi, zb in merged:
            zb = max(zb, e.base)
            h = total_h + 1 - zb
            through = e.wall + 1.0
            if side[0] == "x":
                slots.append(Pos(sign * (outer_l - e.wall) / 2, (lo + hi) / 2, zb + h / 2) * Box(through, hi - lo, h))
            else:
                slots.append(Pos((lo + hi) / 2, sign * (outer_w - e.wall) / 2, zb + h / 2) * Box(hi - lo, through, h))
    return slots


def build_enclosure(e) -> Part:
    """Board case: shell + board standoffs (screw pilot holes) + connector slots. Bottom z=0."""
    b = board_spec(e.board, e)
    bl, bw = b["l"], b["w"]
    inner_l, inner_w = bl + 2 * e.clearance, bw + 2 * e.clearance
    outer_l, outer_w = inner_l + 2 * e.wall, inner_w + 2 * e.wall
    total_h = e.base + e.standoff_h + e.inner_h

    outer = Pos(0, 0, total_h / 2) * Box(outer_l, outer_w, total_h)
    cav_h = total_h - e.base
    inner = Pos(0, 0, e.base + cav_h / 2 + 0.1) * Box(inner_l, inner_w, cav_h + 0.2)
    part = outer - inner

    so_top = e.base + e.standoff_h
    pilot_depth = max(min(6.0, so_top - 1.2), 1.0)      # From the standoff top down, keeping at least 1.2 mm of floor
    for sx, sy in b["holes"]:
        part = part + Pos(sx, sy, so_top / 2) * Cylinder(radius=3.0, height=so_top)
        part = part - Pos(sx, sy, so_top - pilot_depth / 2 + 0.05) * Cylinder(radius=b["pilot"] / 2, height=pilot_depth + 0.1)

    if e.open_ports and b.get("ports"):
        for slot in _port_slots(e, b, outer_l, outer_w, total_h):
            part = part - slot
    elif e.open_ports:                     # A custom board: connector positions unknown, so open both long walls
        oh = total_h - (so_top + 2)
        for sign in (-1, 1):
            part = part - Pos(0, sign * outer_w / 2, (so_top + 2) + oh / 2) * \
                Box(bl - 6, e.wall * 4, oh)
    return part


def build_wrap_case(l: float, w: float, h: float,
                    clearance: float = 2.0, wall: float = 2.0,
                    base: float = 2.0, top_gap: float = 5.0,
                    mounts=None, standoff_h: float = 0.0, pilot: float = 2.2) -> Part:
    """Case enclosing an external reference bounding box l×w×h. Bottom z=0.
    If mounts=[(x,y),...] is given, standoffs + screw pilot holes are placed there to mount the board."""
    lift = standoff_h if (mounts and standoff_h > 0) else 0.0
    inner_l, inner_w = l + 2 * clearance, w + 2 * clearance
    inner_h = lift + h + top_gap
    total_h = base + inner_h
    outer = Pos(0, 0, total_h / 2) * Box(inner_l + 2 * wall, inner_w + 2 * wall, total_h)
    inner = Pos(0, 0, base + inner_h / 2 + 0.1) * Box(inner_l, inner_w, inner_h + 0.2)
    part = outer - inner
    if mounts and standoff_h > 0:
        for (mx, my) in mounts:
            part = part + Pos(mx, my, base + standoff_h / 2) * Cylinder(radius=3.0, height=standoff_h)
            part = part - Pos(mx, my, base + standoff_h - 3 + 0.1) * Cylinder(radius=pilot / 2, height=6)
    return part


def pi_port_cuts(holes_rel, size, base, lift, h, clearance, wall):
    """Orient a Pi 4 board from the detected screw holes and compute a separate cutout for each connector
    (2 stacked USB, Ethernet, 2 HDMI, USB-C, audio, SD), including plug clearance. Returns [(cx,cy,cz,sx,sy,sz), ...] (case frame).
    Board coordinates are community approximations (±1 to 2mm)."""
    inner_l, inner_w = size[0] + 2 * clearance, size[1] + 2 * clearance
    outer_l, outer_w = inner_l + 2 * wall, inner_w + 2 * wall
    hx = sorted(set(round(p[0], 1) for p in holes_rel))
    hy = sorted(set(round(p[1], 1) for p in holes_rel))
    if len(hx) < 2 or len(hy) < 2:
        return []
    hx0, hx1, hy0, hy1 = hx[0], hx[-1], hy[0], hy[-1]
    bz = base + lift
    usb_plus_x = (size[0] / 2 - hx1) > (hx0 + size[0] / 2)       # USB/Ethernet toward +x?
    hdmi_minus_y = (hy0 + size[1] / 2) > (size[1] / 2 - hy1)      # Power/HDMI toward -y?

    def bx2cx(bx):   # Board x (3.5 = first hole) → case x
        return (bx + (hx0 - 3.5)) if usb_plus_x else ((hx1 + 3.5) - bx)

    def by2cy(by):
        return (by + (hy0 - 3.5)) if hdmi_minus_y else ((hy1 + 3.5) - by)

    t = wall * 4
    xw = (outer_l / 2) if usb_plus_x else (-outer_l / 2)          # USB/Ethernet wall
    sdw = -xw                                                     # SD wall
    yw = (-outer_w / 2) if hdmi_minus_y else (outer_w / 2)        # Power/HDMI wall
    cuts = []
    # USB/Ethernet short end: (board y, opening width (+clearance), z min, z max)
    for by, ww, z0, z1 in [(9.0, 16, 2, 17), (27.0, 16, 2, 17), (45.75, 17, 2, 15.5)]:
        cuts.append((xw, by2cy(by), bz + (z0 + z1) / 2, t, ww, z1 - z0))
    # Power/HDMI/audio long side: (board x, opening width (+clearance), z min, z max)
    for bx, ww, z0, z1 in [(11.2, 11, 1.5, 6), (26.0, 9, 1.5, 6), (39.5, 9, 1.5, 6), (53.5, 8, 1.5, 8)]:
        cuts.append((bx2cx(bx), yw, bz + (z0 + z1) / 2, ww, t, z1 - z0))
    # SD card: opposite short end
    cuts.append((sdw, by2cy(28.0), bz + 1.5, t, 15, 4))
    return cuts


def build_case_with_lid(l, w, h, clearance=2.5, wall=2.5, base=2.5,
                        standoff_h=4.0, mounts=None, lid_t=3.0,
                        gasket=True, screw="M3", ports=False, port_cuts=None):
    """Sealed case (body + lid). Body: closed walls + board standoffs + corner screw bosses + gasket groove.
    Lid: corner screw through holes + inner lip. Returns (body, lid). (Aimed at waterproof/IP use)"""
    pilot = {"M2.5": 2.1, "M3": 2.5}.get(screw, 2.5)
    clear = {"M2.5": 2.8, "M3": 3.4}.get(screw, 3.4)
    inner_l, inner_w = l + 2 * clearance, w + 2 * clearance
    outer_l, outer_w = inner_l + 2 * wall, inner_w + 2 * wall
    lift = standoff_h if (mounts and standoff_h > 0) else 0.0
    inner_h = lift + h + 4.0
    total_h = base + inner_h

    outer = Pos(0, 0, total_h / 2) * Box(outer_l, outer_w, total_h)
    inner = Pos(0, 0, base + inner_h / 2 + 0.1) * Box(inner_l, inner_w, inner_h + 0.2)
    body = outer - inner

    if mounts and standoff_h > 0:                       # Board standoffs
        for (mx, my) in mounts:
            body = body + Pos(mx, my, base + standoff_h / 2) * Cylinder(radius=3.0, height=standoff_h)
            body = body - Pos(mx, my, base + standoff_h - 3 + 0.1) * Cylinder(radius=pilot / 2, height=6)

    br = 3.5
    corners = [(sx * (outer_l / 2 - br), sy * (outer_w / 2 - br)) for sx in (-1, 1) for sy in (-1, 1)]
    for (cx, cy) in corners:                            # Corner screw bosses (wall corners)
        body = body + Pos(cx, cy, total_h / 2) * Cylinder(radius=br, height=total_h)
        body = body - Pos(cx, cy, total_h - 12 / 2 + 0.1) * Cylinder(radius=pilot / 2, height=12)

    if port_cuts:                                       # Per-face port cutouts (Pi port map)
        for (cx, cy, cz, sx, sy, sz) in port_cuts:
            body = body - Pos(cx, cy, cz) * Box(sx, sy, sz)
    elif ports:                                         # Generic: cut the long wall up to connector height
        board_bottom = base + lift
        oz0, oz1 = board_bottom + 1.5, board_bottom + h - 1.0
        ow = max(l - 10, 5)
        for sign in (-1, 1):
            body = body - Pos(0, sign * outer_w / 2, (oz0 + oz1) / 2) * \
                Box(ow, wall * 4, max(oz1 - oz0, 2))

    if gasket:                                          # Gasket groove (ring) on the top face
        gw, gd = 1.6, 1.5
        cl, cw = (inner_l + outer_l) / 2, (inner_w + outer_w) / 2
        ring_o = Pos(0, 0, total_h - gd / 2 + 0.1) * Box(cl + gw, cw + gw, gd + 0.2)
        ring_i = Pos(0, 0, total_h - gd / 2 + 0.1) * Box(cl - gw, cw - gw, gd + 0.3)
        body = body - (ring_o - ring_i)

    lid_z = total_h + 6 + lid_t / 2                     # Assembly view: lift the lid up
    lid = Pos(0, 0, lid_z) * Box(outer_l, outer_w, lid_t)
    for (cx, cy) in corners:
        lid = lid - Pos(cx, cy, lid_z) * Cylinder(radius=clear / 2, height=lid_t + 1)
    lid = lid + Pos(0, 0, lid_z - lid_t / 2 - 1.2) * Box(inner_l - 0.6, inner_w - 0.6, 2.4)  # Inner lip
    return body, lid


def build_profile(p) -> Part:
    """Flat outline → extrude by thickness. Bottom z=0, up by thickness. Single watertight solid."""
    r = max(p.outer_d / 2.0, 0.5)
    th = max(p.thickness, 0.1)
    shape = (p.shape or "asterisk").lower()
    if shape == "disc":
        sk = Circle(radius=r)
    elif shape == "polygon":
        sk = RegularPolygon(radius=r, side_count=max(int(p.points or 6), 3))
    elif shape == "rounded_rect":
        cr = p.corner_radius if p.corner_radius and p.corner_radius > 0 else p.outer_d * 0.1
        cr = max(min(cr, r - 0.01), 0.1)
        sk = RectangleRounded(p.outer_d, p.outer_d, cr)
    elif shape == "star":
        n = max(int(p.points or 6), 3)
        inner = r * 0.45
        pts = []
        for i in range(2 * n):
            rad = r if i % 2 == 0 else inner
            a = math.pi * i / n
            pts.append((rad * math.cos(a), rad * math.sin(a)))
        sk = Polygon(*pts)
    else:  # asterisk: union of n rounded bars radiating from the center (logo style)
        n = max(int(p.arms or 6), 2)
        aw = p.arm_width if p.arm_width and p.arm_width > 0 else p.outer_d * 0.12
        aw = max(aw, 1.0)
        sk = Circle(radius=aw * 0.6)                      # Center hub (keeps the bars connected)
        for i in range(n):
            arm = Pos(r / 2, 0) * RectangleRounded(r, aw, aw / 2 * 0.99)
            sk = sk + Rot(0, 0, 360.0 * i / n) * arm
    return extrude(sk, amount=th)


def _wedge_cutter(radius: float, height: float, deg: float) -> Part:
    """Pie-shaped wedge opening deg around the +x axis (cuts the C-clip mouth). Through z 0..height."""
    half = math.radians(deg) / 2.0
    steps = max(4, int(deg / 8))
    pts = [(0.0, 0.0)]
    for i in range(steps + 1):
        a = -half + (2 * half) * i / steps
        pts.append((radius * math.cos(a), radius * math.sin(a)))
    return Pos(0, 0, -0.1) * extrude(Polygon(*pts), amount=height + 0.2)


def build_clamp(c) -> Part:
    """C-shaped clip that grips a rod, plus an optional attachment. Bottom z=0. Mouth opens toward +x."""
    ri = c.rod_d / 2.0 + max(c.clearance, 0.0)
    R = ri + max(c.wall, 0.8)
    h = max(c.height, 1.0)
    part = Pos(0, 0, h / 2) * Cylinder(radius=R, height=h) \
        - Pos(0, 0, h / 2) * Cylinder(radius=ri, height=h + 1)
    if c.gap_deg and c.gap_deg > 0:
        part = part - _wedge_cutter(R + 2, h, min(c.gap_deg, 300))
    if c.attach == "pocket":
        pw, pd, ph, w = max(c.pocket_w, 2), max(c.pocket_d, 2), max(c.pocket_h, 2), max(c.wall, 1.2)
        cx = -(R - 2.0) - pd / 2.0                        # Joined with a 2mm overlap on the side opposite the mouth (-x)
        part = part + Pos(cx, 0, ph / 2) * Box(pd, pw, ph)
        part = part - Pos(cx, 0, w + ph / 2 + 0.1) * \
            Box(max(pd - 2 * w, 1), max(pw - 2 * w, 1), ph)   # Open-top pocket
    elif c.attach == "plate":
        tl, tw, tt = max(c.tab_l, 2), max(c.tab_w, 2), max(c.tab_t, 0.8)
        cx = -(R - 2.0) - tl / 2.0
        part = part + Pos(cx, 0, tt / 2) * Box(tl, tw, tt)
    return part


def build_ball(b) -> Part:
    """Hollow sphere shell (moon lamp) + bottom socket hole. Bottom pole sits at z=0. Watertight."""
    R = max(b.outer_d / 2.0, 1.0)
    inner_r = max(R - max(b.wall, 0.4), 0.5)
    shell = Sphere(radius=R) - Sphere(radius=inner_r)
    if b.socket_d and b.socket_d > 0:
        sh = b.socket_h if (b.socket_h and b.socket_h > 0) else (max(b.wall, 0.4) + 3)
        shell = shell - Pos(0, 0, -R + sh / 2 - 0.1) * \
            Cylinder(radius=b.socket_d / 2.0, height=sh)
    return Pos(0, 0, R) * shell                           # Move the bottom pole to z=0


def build_from_contract(c):
    """DesignContract → (Part, Fastener|None, hole_dia|None). Branches on kind."""
    if c.kind == "container":
        return build_container(c.container), None, None
    if c.kind == "gear":
        return build_gear(c.gear), None, None
    if c.kind == "enclosure":
        return build_enclosure(c.enclosure), None, None
    if c.kind == "profile":
        return build_profile(c.profile), None, None
    if c.kind == "clamp":
        return build_clamp(c.clamp), None, None
    if c.kind == "ball":
        return build_ball(c.ball), None, None
    if c.kind == "assembly":
        from ..mech import build_assembly
        asm = build_assembly(c.assembly)
        part = asm.exploded(c.assembly.exploded) if c.assembly.exploded > 0 else asm.compound
        part._rc_asm = asm
        return part, None, None
    from ..fasteners.standards import resolve
    f, exact, note = resolve(c.fastener)
    c.fastener_exact, c.fastener_note = exact, note      # The pipeline reports this as F0
    part = plate(c.plate.length, c.plate.width, c.plate.thickness)
    if c.wall is not None:
        part = part + wall(c.wall.x, c.plate.width, c.wall.height, c.wall.thickness)
    ht = getattr(c, "hole_type", "through")
    if ht == "tapped":
        # Tapped hole: tap drill ≈ D - 1.0825 p (75% thread engagement). Threads not modeled; H3 verifies depth only
        dia = float(c.hole_dia) if getattr(c, "hole_dia", None) else round(f.nominal_dia_mm - 1.0825 * f.pitch_mm, 2)
    elif ht == "insert":
        from ..fasteners.standards import insert_spec
        spec = insert_spec(f)
        dia = float(c.hole_dia) if getattr(c, "hole_dia", None) else (spec[0] if spec else f.clearance(c.fit))
    else:
        dia = float(c.hole_dia) if getattr(c, "hole_dia", None) else f.clearance(c.fit)
    style = getattr(c, "hole_style", "plain")
    comp = float(getattr(c, "hole_comp", 0.0) or 0.0)
    if ht != "tapped" and comp > 0 and not getattr(c, "hole_dia", None):   # FDM shrink compensation only for auto-sized holes (explicit diameters unchanged)
        dia = round(dia + comp, 2)
    for h in c.holes:
        if ht == "insert":
            # Insert holes are blind (1 mm floor left), insert length + 1 mm clearance; through if the plate is thin
            from ..fasteners.standards import insert_spec
            spec = insert_spec(f); L = (spec[1] + 1.0) if spec else c.plate.thickness
            depth = min(L, c.plate.thickness - 1.0) if c.plate.thickness - 1.0 > 1.0 else c.plate.thickness
            if depth >= c.plate.thickness - 1e-6:
                part = drill(part, h.x, h.y, dia, c.plate.thickness)
            else:
                part = part - Pos(h.x, h.y, -depth / 2 + 0.01) * Cylinder(radius=dia / 2, height=depth + 0.02)
        else:
            part = drill(part, h.x, h.y, dia, c.plate.thickness)
        if style == "counterbore":
            part = part - counterbore_cutter(f, h.x, h.y)
        elif style == "countersink":
            part = part - countersink_cutter(f, h.x, h.y)
    return part, f, dia


def counterbore_cutter(f: Fastener, x: float, y: float) -> Part:
    """Counterbore: diameter = head across-corners + 1.0 mm, depth = head height (head top flush with the plate face)."""
    d = f.head_across_corners_mm + 1.0
    depth = f.head_height_mm
    return Pos(x, y, -depth / 2 + 0.01) * Cylinder(radius=d / 2, height=depth + 0.02)


def countersink_cutter(f: Fastener, x: float, y: float) -> Part:
    """Countersink (flat head): entry diameter ≈ 2.0×D, angle 90° (metric) / 82° (inch). Conical cutter."""
    from build123d import Cone
    top_d = 2.0 * f.nominal_dia_mm
    ang = 90.0 if f.is_metric else 82.0
    depth = (top_d / 2.0) / math.tan(math.radians(ang / 2.0))
    # Cone(bottom_radius, top_radius, height) has its bottom at -h/2 and top at +h/2, so align the top with the plate face (z=0)
    return Pos(x, y, -depth / 2 + 0.01) * Cone(bottom_radius=0.01, top_radius=top_d / 2, height=depth + 0.02)
