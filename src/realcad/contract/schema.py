"""Design contract (DesignContract): Meta (Muse Spark) translates natural-language requests into this.
The kernel trusts only this contract to build and verify parts (it never execs model-generated code).

kind: plate (plate/bracket + bolt holes), container (tub/cup/box, walls + floor), gear (spur gear),
    enclosure (board case), profile (custom flat silhouette extrusion), clamp (C-clip that grips a rod),
    ball (hollow sphere shell, moon lamp),
    assembly (power_train power transmission, eccentric_slider eccentric reciprocating mechanism; dimensions from standards tables),
    retrieve (organic freeform shapes parametric primitives cannot make; handed off to an external 3D library search).
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Plate:
    length: float
    width: float
    thickness: float


@dataclass
class Wall:
    x: float
    height: float
    thickness: float


@dataclass
class Hole:
    x: float
    y: float


@dataclass
class Container:
    shape: str = "round"          # "round" | "box"
    outer_d: float = 60.0         # round: outer diameter
    length: float = 60.0          # box: length
    width: float = 60.0           # box: width
    height: float = 90.0
    wall: float = 2.4
    base: float = 2.4
    dividers: int = 0             # Number of internal dividers (0 = none)


@dataclass
class Gear:
    teeth: int = 20
    module: float = 2.0
    thickness: float = 6.0
    bore: float = 6.0             # Center bore diameter


@dataclass
class Enclosure:
    board: str = "raspberry_pi_4"   # Board preset
    clearance: float = 2.0          # Board edge to inner wall
    wall: float = 2.0
    base: float = 2.0
    standoff_h: float = 4.0         # Standoff height lifting the board off the floor
    inner_h: float = 22.0           # Component space above the board
    open_ports: bool = True         # Open the port side (long wall)
    board_l: float = 0.0            # Board length when board="custom"
    board_w: float = 0.0            # Board width when board="custom"
    board_holes: list = field(default_factory=list)   # custom: [[x,y],...] in mm, origin at the board lower-left corner
    board_screw: str = "M3"         # custom: standoff screw


@dataclass
class Profile:
    """Part made by extruding a flat outline by a thickness (coasters, logo tags, etc.)."""
    shape: str = "asterisk"       # asterisk | star | disc | polygon | rounded_rect
    outer_d: float = 100.0        # Outer diameter/size (mm)
    thickness: float = 5.0
    arms: int = 6                 # Number of asterisk arms
    points: int = 6               # Star points / polygon sides
    arm_width: float = 0.0        # Asterisk bar width (0 = auto outer_d*0.12)
    corner_radius: float = 0.0    # rounded_rect corner radius (0 = auto outer_d*0.1)


@dataclass
class Clamp:
    """C-shaped clip that grips a rod (cylinder), plus an optional attachment."""
    rod_d: float = 16.0           # Gripped rod diameter
    clearance: float = 0.3        # Gap to the rod
    wall: float = 3.0             # Clip wall thickness
    gap_deg: float = 120.0        # Mouth opening angle (so it can snap on)
    height: float = 20.0          # Clip height
    attach: str = "none"          # none | pocket | plate
    pocket_w: float = 80.0        # pocket: width (Y)
    pocket_d: float = 15.0        # pocket: depth (X, protrusion)
    pocket_h: float = 100.0       # pocket: height (Z)
    tab_l: float = 30.0           # plate: tab length (X, protrusion)
    tab_w: float = 20.0           # plate: tab width (Y)
    tab_t: float = 4.0            # plate: tab thickness (Z)


@dataclass
class Ball:
    """Hollow sphere shell (moon lamp) with a bulb socket hole in the bottom."""
    outer_d: float = 150.0        # Sphere diameter
    wall: float = 2.0             # Shell thickness (the slicer hollows it)
    socket_d: float = 30.0        # Bottom socket hole diameter (0 = no hole)
    socket_h: float = 0.0         # Socket hole depth (0 = auto wall+3)


@dataclass
class Assembly:
    """Power transmission (power_train) assembly. The remaining dimensions are derived from a few key inputs (bearing size, gear m and z,
    pulley type and pitch diameter, pinion tooth count) via the KS tables (mech/standards.py). The builder fixes mates M1 to M9 by coordinates."""
    preset: str = "power_train"
    bearing: str = "6204"         # Deep groove ball bearing size → shaft bearing seat diameter = bore
    shaft_d: float = 0.0          # 0 means the bearing bore
    gear_module: float = 2.0
    gear_teeth: int = 30
    gear_width: float = 0.0       # 0 means 10m
    pinion_teeth: int = 0         # 0 means no pinion (second shaft)
    pulley_type: str = "A"        # V-belt type A B C D, "none" for no pulley
    pulley_dp: float = 100.0      # Pulley pitch (nominal) diameter
    pulley_grooves: int = 1
    pulley_hub_w: float = 0.0     # 0 means auto (groove count, shaft diameter)
    housing: bool = True
    covers: bool = True
    bolts: bool = True
    oil_seal: bool = True
    rings: bool = True            # Retaining ring
    exploded: float = 0.0         # Exploded view gap (mm), 0 = assembled
    # Only for preset "eccentric_slider" (eccentric reciprocating mechanism)
    eccentricity: float = 8.0     # Eccentricity e (stroke = 2e)
    link_length: float = 50.0     # Link center distance (eccentric journal center to pin)
    slider_d: float = 20.0        # Slider rod diameter (= guide bushing bore)
    # Only for preset "drill_jig": workpiece and hole pattern
    work_l: float = 80.0
    work_w: float = 50.0
    work_t: float = 15.0
    drill_d: float = 10.0
    holes: list = field(default_factory=lambda: [[-20.0, 0.0], [20.0, 0.0]])   # (x, y) relative to the workpiece center
    # Only for preset "vise" (bench vise)
    jaw_w: float = 80.0           # Jaw width (Y)
    open_max: float = 60.0        # Maximum opening
    screw_d: float = 16.0         # Lead screw nominal diameter
    # Only for preset "cam_clamp"
    work_d: float = 30.0          # Cylindrical workpiece diameter
    cam_lift: float = 4.0         # Cam eccentricity (lift)


@dataclass
class Retrieve:
    """Cannot be expressed with parametric primitives, so search and import from an external 3D model library."""
    query: str = ""               # External library search query (English)
    note: str = ""                # One line on why parametric generation is impossible
    parts: list = field(default_factory=list)   # When asked to split a compound object into parts: [{name, query}]


@dataclass
class DesignContract:
    kind: str = "plate"
    plate: Plate | None = None
    fastener: str = "1/4-20"
    fit: str = "normal"
    hole_dia: float | None = None      # Explicit hole diameter (mm). None means a standard clearance hole. The kernel verifies it by measurement (H2)
    hole_type: str = "through"         # through (through + nut) | tapped (threads directly in the plate) | insert (heat-set insert)
    hole_style: str = "plain"          # plain | counterbore (recessed head) | countersink (flat head)
    hole_comp: float = 0.2             # FDM hole shrink compensation (mm, added to the diameter). Community measurements show holes 0.1 to 0.3 undersize. 0 means none
    material: str = "pla"              # Plate material: pla/petg/abs/plastic(k=2.0) aluminum(1.5) brass(1.3) steel(1.0)
    mate_thickness: float = 0.0        # Mating part thickness for through fastening (mm), for bolt length (0 = unknown, plate thickness only)
    washer: bool = False               # Include a flat washer (for length)
    nut: bool = True                   # Include a nut for through fastening (for length)
    wall: Wall | None = None
    holes: list[Hole] = field(default_factory=list)
    container: Container | None = None
    gear: Gear | None = None
    enclosure: Enclosure | None = None
    profile: Profile | None = None
    clamp: Clamp | None = None
    ball: Ball | None = None
    assembly: Assembly | None = None
    retrieve: Retrieve | None = None
    fastener_exact: bool = True        # Set by the builder: whether the requested spec exists exactly
    fastener_note: str = ""            # Substitution note when missing (F0 message)

    @classmethod
    def from_dict(cls, d: dict) -> "DesignContract":
        """LLM/user input dict → contract. Numbers are clamped to safe ranges by _sanitize (prevents DoS and OCC blowups)."""
        return _sanitize(cls._from_dict_raw(d))

    @classmethod
    def _from_dict_raw(cls, d: dict) -> "DesignContract":
        kind = d.get("kind", "plate")
        if kind == "retrieve":
            rd = d.get("retrieve", d)
            parts = []
            for p in (rd.get("parts") or []):
                if isinstance(p, dict) and (p.get("name") or p.get("query")):
                    parts.append({"name": str(p.get("name", "")).strip(),
                                  "query": str(p.get("query", "") or p.get("name", "")).strip()})
            return cls(kind="retrieve", retrieve=Retrieve(
                query=str(rd.get("query", "")).strip(),
                note=str(rd.get("note", "")).strip(), parts=parts))
        if kind == "enclosure":
            ed = d.get("enclosure", d)
            return cls(kind="enclosure", enclosure=Enclosure(
                board=ed.get("board", "raspberry_pi_4"),
                clearance=float(ed.get("clearance", 2)), wall=float(ed.get("wall", 2)),
                base=float(ed.get("base", 2)), standoff_h=float(ed.get("standoff_h", 4)),
                inner_h=float(ed.get("inner_h", 22)),
                open_ports=bool(ed.get("open_ports", True)),
                board_l=float(ed.get("board_l", 0) or 0), board_w=float(ed.get("board_w", 0) or 0),
                board_holes=[[float(h[0]), float(h[1])] for h in (ed.get("board_holes") or []) if isinstance(h, (list, tuple)) and len(h) == 2][:12],
                board_screw=str(ed.get("board_screw", "M3") or "M3")))
        if kind == "container":
            cd = d.get("container", d)
            return cls(kind="container", container=Container(
                shape=cd.get("shape", "round"),
                outer_d=float(cd.get("outer_d", 60)),
                length=float(cd.get("length", 60)), width=float(cd.get("width", 60)),
                height=float(cd.get("height", 90)),
                wall=float(cd.get("wall", 2.4)), base=float(cd.get("base", 2.4)),
                dividers=int(cd.get("dividers", 0))))
        if kind == "gear":
            gd = d.get("gear", d)
            return cls(kind="gear", gear=Gear(
                teeth=int(gd.get("teeth", 20)), module=float(gd.get("module", 2)),
                thickness=float(gd.get("thickness", 6)), bore=float(gd.get("bore", 6))))
        if kind == "profile":
            pd = d.get("profile", d)
            return cls(kind="profile", profile=Profile(
                shape=pd.get("shape", "asterisk"),
                outer_d=float(pd.get("outer_d", 100)),
                thickness=float(pd.get("thickness", 5)),
                arms=int(pd.get("arms", 6)), points=int(pd.get("points", 6)),
                arm_width=float(pd.get("arm_width", 0) or 0),
                corner_radius=float(pd.get("corner_radius", 0) or 0)))
        if kind == "clamp":
            cd = d.get("clamp", d)
            return cls(kind="clamp", clamp=Clamp(
                rod_d=float(cd.get("rod_d", 16)),
                clearance=float(cd.get("clearance", 0.3)),
                wall=float(cd.get("wall", 3)), gap_deg=float(cd.get("gap_deg", 120)),
                height=float(cd.get("height", 20)), attach=cd.get("attach", "none"),
                pocket_w=float(cd.get("pocket_w", 80)), pocket_d=float(cd.get("pocket_d", 15)),
                pocket_h=float(cd.get("pocket_h", 100)), tab_l=float(cd.get("tab_l", 30)),
                tab_w=float(cd.get("tab_w", 20)), tab_t=float(cd.get("tab_t", 4))))
        if kind == "assembly":
            ad = d.get("assembly", d)
            g = ad.get("gear") if isinstance(ad.get("gear"), dict) else {}
            pu = ad.get("pulley") if isinstance(ad.get("pulley"), dict) else {}
            ptype = str(pu.get("type", ad.get("pulley_type", "A")) or "A")
            return cls(kind="assembly", assembly=Assembly(
                preset=str(ad.get("preset", "power_train") or "power_train"),
                bearing=str(ad.get("bearing", "6204") or "6204"),
                shaft_d=float(ad.get("shaft_d", 0) or 0),
                gear_module=float(g.get("module", ad.get("gear_module", 2)) or 2),
                gear_teeth=int(g.get("teeth", ad.get("gear_teeth", 30)) or 30),
                gear_width=float(g.get("width", ad.get("gear_width", 0)) or 0),
                pinion_teeth=int(ad.get("pinion_teeth", 0) or 0),
                pulley_type=("none" if ptype.lower() in ("none", "no", "false", "") else ptype.upper()),
                pulley_dp=float(pu.get("dp", ad.get("pulley_dp", 100)) or 100),
                pulley_grooves=int(pu.get("grooves", ad.get("pulley_grooves", 1)) or 1),
                pulley_hub_w=float(pu.get("hub_width", ad.get("pulley_hub_w", 0)) or 0),
                housing=bool(ad.get("housing", True)), covers=bool(ad.get("covers", True)),
                bolts=bool(ad.get("bolts", True)), oil_seal=bool(ad.get("oil_seal", True)),
                rings=bool(ad.get("rings", True)),
                exploded=float(ad.get("exploded", 0) or 0),
                eccentricity=float(ad.get("eccentricity", ad.get("e", 8)) or 8),
                link_length=float(ad.get("link_length", 50) or 50),
                slider_d=float(ad.get("slider_d", 20) or 20),
                work_l=float((ad.get("work") or {}).get("length", ad.get("work_l", 80)) or 80),
                work_w=float((ad.get("work") or {}).get("width", ad.get("work_w", 50)) or 50),
                work_t=float((ad.get("work") or {}).get("thickness", ad.get("work_t", 15)) or 15),
                drill_d=float(ad.get("drill_d", 10) or 10),
                jaw_w=float(ad.get("jaw_w", 80) or 80), open_max=float(ad.get("open_max", 60) or 60), screw_d=float(ad.get("screw_d", 16) or 16),
                work_d=float(ad.get("work_d", 30) or 30), cam_lift=float(ad.get("cam_lift", 4) or 4),
                holes=[[float(h[0]), float(h[1])] for h in (ad.get("holes") or [[-20, 0], [20, 0]]) if isinstance(h, (list, tuple)) and len(h) == 2][:16]))
        if kind == "ball":
            bd = d.get("ball", d)
            return cls(kind="ball", ball=Ball(
                outer_d=float(bd.get("outer_d", 150)), wall=float(bd.get("wall", 2)),
                socket_d=float(bd.get("socket_d", 30)), socket_h=float(bd.get("socket_h", 0))))
        # plate / bracket (default)
        p = d["plate"]; w = d.get("wall")
        return cls(
            kind="plate",
            plate=Plate(float(p["length"]), float(p["width"]), float(p["thickness"])),
            fastener=d.get("fastener", "1/4-20"), fit=d.get("fit", "normal"),
            hole_dia=(float(d["hole_dia"]) if d.get("hole_dia") not in (None, "", 0) else None),
            hole_type=str(d.get("hole_type", "through") or "through").lower(),
            hole_style=str(d.get("hole_style", "plain") or "plain").lower(),
            hole_comp=float(d.get("hole_comp", 0.2) if d.get("hole_comp") is not None else 0.2),
            material=str(d.get("material", "pla") or "pla").lower(),
            mate_thickness=float(d.get("mate_thickness", 0) or 0),
            washer=bool(d.get("washer", False)), nut=bool(d.get("nut", True)),
            wall=Wall(float(w["x"]), float(w["height"]), float(w["thickness"])) if w else None,
            holes=[Hole(float(h["x"]), float(h["y"])) for h in d.get("holes", [])],
        )

    def to_dict(self) -> dict:
        if self.kind == "container":
            c = self.container
            return {"kind": "container", "container": {
                "shape": c.shape, "outer_d": c.outer_d, "length": c.length,
                "width": c.width, "height": c.height, "wall": c.wall,
                "base": c.base, "dividers": c.dividers}}
        if self.kind == "gear":
            g = self.gear
            return {"kind": "gear", "gear": {
                "teeth": g.teeth, "module": g.module,
                "thickness": g.thickness, "bore": g.bore}}
        if self.kind == "enclosure":
            e = self.enclosure
            return {"kind": "enclosure", "enclosure": {
                "board": e.board, "clearance": e.clearance, "wall": e.wall,
                "base": e.base, "standoff_h": e.standoff_h, "inner_h": e.inner_h,
                "open_ports": e.open_ports, "board_l": e.board_l, "board_w": e.board_w,
                "board_holes": e.board_holes, "board_screw": e.board_screw}}
        if self.kind == "profile":
            p = self.profile
            return {"kind": "profile", "profile": {
                "shape": p.shape, "outer_d": p.outer_d, "thickness": p.thickness,
                "arms": p.arms, "points": p.points, "arm_width": p.arm_width,
                "corner_radius": p.corner_radius}}
        if self.kind == "clamp":
            c = self.clamp
            return {"kind": "clamp", "clamp": {
                "rod_d": c.rod_d, "clearance": c.clearance, "wall": c.wall,
                "gap_deg": c.gap_deg, "height": c.height, "attach": c.attach,
                "pocket_w": c.pocket_w, "pocket_d": c.pocket_d, "pocket_h": c.pocket_h,
                "tab_l": c.tab_l, "tab_w": c.tab_w, "tab_t": c.tab_t}}
        if self.kind == "ball":
            b = self.ball
            return {"kind": "ball", "ball": {
                "outer_d": b.outer_d, "wall": b.wall,
                "socket_d": b.socket_d, "socket_h": b.socket_h}}
        if self.kind == "assembly":
            a = self.assembly
            return {"kind": "assembly", "assembly": {
                "preset": a.preset, "bearing": a.bearing, "shaft_d": a.shaft_d,
                "gear": {"module": a.gear_module, "teeth": a.gear_teeth, "width": a.gear_width},
                "pinion_teeth": a.pinion_teeth,
                "pulley": {"type": a.pulley_type, "dp": a.pulley_dp, "grooves": a.pulley_grooves, "hub_width": a.pulley_hub_w},
                "housing": a.housing, "covers": a.covers, "bolts": a.bolts, "oil_seal": a.oil_seal,
                "rings": a.rings, "exploded": a.exploded,
                **({"eccentricity": a.eccentricity, "link_length": a.link_length, "slider_d": a.slider_d}
                   if a.preset == "eccentric_slider" else {}),
                **({"work": {"length": a.work_l, "width": a.work_w, "thickness": a.work_t}, "drill_d": a.drill_d, "holes": a.holes}
                   if a.preset == "drill_jig" else {}),
                **({"jaw_w": a.jaw_w, "open_max": a.open_max, "screw_d": a.screw_d} if a.preset == "vise" else {}),
                **({"work_d": a.work_d, "cam_lift": a.cam_lift} if a.preset == "cam_clamp" else {})}}
        if self.kind == "retrieve":
            r = self.retrieve
            return {"kind": "retrieve", "retrieve": {
                "query": r.query, "note": r.note, "parts": r.parts}}
        return {
            "kind": "plate",
            "plate": {"length": self.plate.length, "width": self.plate.width,
                      "thickness": self.plate.thickness},
            "fastener": self.fastener, "fit": self.fit, "hole_dia": self.hole_dia, "hole_type": self.hole_type, "hole_style": self.hole_style, "hole_comp": self.hole_comp, "material": self.material, "mate_thickness": self.mate_thickness, "washer": self.washer, "nut": self.nut,
            "wall": ({"x": self.wall.x, "height": self.wall.height,
                      "thickness": self.wall.thickness} if self.wall else None),
            "holes": [{"x": h.x, "y": h.y} for h in self.holes],
        }


# ── Input range guards ────────────────────────────────────
MAX_DIM_MM = 1000.0        # Max side length (several times a typical printer build volume)
MIN_DIM_MM = 0.2
_INT_LIMITS = {"teeth": (4, 200), "dividers": (0, 50), "arms": (2, 64), "points": (3, 64),
               "gear_teeth": (8, 200), "pinion_teeth": (0, 200), "pulley_grooves": (1, 6)}
_MAX_HOLES = 64


def _clampf(v, lo=MIN_DIM_MM, hi=MAX_DIM_MM):
    try:
        v = float(v)
    except Exception:
        return lo
    if v != v:            # NaN
        return lo
    return max(lo, min(hi, v))


def _sanitize(c: "DesignContract") -> "DesignContract":
    """Clamp every number so values like negatives, NaN or 10^6 cannot hang the kernel."""
    for obj in (c.plate, c.wall, c.container, c.gear, c.enclosure, c.profile, c.clamp, c.ball, c.assembly):
        if obj is None:
            continue
        for k, v in list(vars(obj).items()):
            if isinstance(v, bool) or isinstance(v, str) or v is None:
                continue
            if k in _INT_LIMITS:
                lo, hi = _INT_LIMITS[k]
                try:
                    iv = int(v)
                except Exception:
                    iv = lo
                setattr(obj, k, max(lo, min(hi, iv)))
            elif k == "gap_deg":
                setattr(obj, k, _clampf(v, 10.0, 300.0))
            elif k in ("clearance", "socket_h", "arm_width", "corner_radius", "socket_d"):
                setattr(obj, k, _clampf(v, 0.0, MAX_DIM_MM))
            elif obj is c.wall and k == "x":                 # Wall position may be negative (relative to the plate center)
                setattr(obj, k, _clampf(v, -MAX_DIM_MM, MAX_DIM_MM))
            elif isinstance(v, (int, float)):
                setattr(obj, k, _clampf(v))
    if c.assembly is not None:
        a = c.assembly
        # Fields where 0 means auto were raised to 0.2 by the generic loop, so restore them
        a.shaft_d = 0.0 if a.shaft_d < 5.0 else _clampf(a.shaft_d, 5.0, 75.0)
        a.gear_module = _clampf(a.gear_module, 0.5, 10.0)
        a.gear_width = 0.0 if a.gear_width < 1.0 else _clampf(a.gear_width, 1.0, 200.0)
        a.pulley_dp = _clampf(a.pulley_dp, 40.0, 600.0)
        a.pulley_hub_w = 0.0 if a.pulley_hub_w < 1.0 else _clampf(a.pulley_hub_w, 1.0, 200.0)
        a.exploded = 0.0 if a.exploded < 0.5 else _clampf(a.exploded, 0.5, 120.0)
        if a.pulley_type not in ("A", "B", "C", "D", "none"):
            a.pulley_type = "A"
        if a.preset not in ("power_train", "eccentric_slider", "gear_pump", "drill_jig", "vise", "cam_clamp"):
            a.preset = "power_train"
        a.eccentricity = _clampf(a.eccentricity, 2.0, 30.0)
        a.link_length = _clampf(a.link_length, 20.0, 200.0)
        a.slider_d = _clampf(a.slider_d, 8.0, 40.0)
        a.work_l = _clampf(a.work_l, 10.0, 400.0); a.work_w = _clampf(a.work_w, 10.0, 400.0); a.work_t = _clampf(a.work_t, 1.0, 100.0)
        a.drill_d = _clampf(a.drill_d, 1.0, 20.0)
        a.jaw_w = _clampf(a.jaw_w, 30.0, 300.0); a.open_max = _clampf(a.open_max, 10.0, 300.0); a.screw_d = _clampf(a.screw_d, 8.0, 40.0)
        a.work_d = _clampf(a.work_d, 5.0, 200.0); a.cam_lift = _clampf(a.cam_lift, 1.0, 20.0)
        a.holes = [[_clampf(h[0], -200.0, 200.0), _clampf(h[1], -200.0, 200.0)] for h in (a.holes or [])][:16] or [[0.0, 0.0]]
    if c.hole_dia is not None:
        c.hole_dia = _clampf(c.hole_dia, 0.5, 100.0)
    if c.fit not in ("close", "normal", "loose"):
        c.fit = "normal"
    if c.hole_type not in ("through", "tapped", "insert"):
        c.hole_type = "through"
    if c.hole_style not in ("plain", "counterbore", "countersink"):
        c.hole_style = "plain"
    c.mate_thickness = _clampf(c.mate_thickness, 0.0, 500.0)
    c.hole_comp = _clampf(c.hole_comp, 0.0, 1.0)
    if len(c.holes) > _MAX_HOLES:
        c.holes = c.holes[:_MAX_HOLES]
    for h in c.holes:
        h.x = _clampf(h.x, -MAX_DIM_MM, MAX_DIM_MM)
        h.y = _clampf(h.y, -MAX_DIM_MM, MAX_DIM_MM)
    return c
