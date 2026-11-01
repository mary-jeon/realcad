"""Drill jig assembly builder (preset drill_jig): CAD practical exam task 4. Builds the jig from workpiece size and hole coordinates.

Reference: 153LAB drill jig 2 (base, fixed bushing, clamp plate, stud bolt, C-washer);
bushing dimensions from the DIN 179 table (KS B 1030 family), bore tolerance G6 for drills, design rule bushing length ≥ 2d.
Coordinates: Z up, workpiece center = origin (x, y), base bottom z = 0. The jig plate sits above the workpiece on 2 posts (box jig),
and a side clamp (stud bolt + clamp plate) pushes the workpiece toward the locating pins.
"""
from __future__ import annotations

from build123d import Part, Compound, Box, Cylinder, Pos, Rot, RegularPolygon, extrude

from . import standards as S
from .power_train import PartInfo, Assembly, fit

BASE_T = 15.0
POST_W = 22.0          # Post thickness in X
SIDE = 12.0            # Clearance from workpiece to post inner face / sides
PIN_D = 8.0
PIN_H = 10.0
PAD_T = 10.0
STUD = "M10"
BOLT = "M8"


def layout_drill_jig(a) -> dict:
    wl, ww, wt, d = float(a.work_l), float(a.work_w), float(a.work_t), float(a.drill_d)
    bush = S.drill_bush(d)
    tp = bush.length_for(2.0 * d)                  # Jig plate thickness = bushing length (the standard length ≥ 2d, if any)
    gap = max(6.0, round(0.6 * d, 1))              # Chip clearance: bushing bottom to workpiece top
    half_l = wl / 2.0 + SIDE                        # Up to the post inner face
    Lb = 2 * (half_l + POST_W) + 2 * 10.0           # Base length (10 margin outside the posts)
    Wb = ww + 2 * SIDE + 2 * 12.0
    z_w1 = BASE_T + wt                              # Workpiece top face
    z_p0 = z_w1 + gap                               # Jig plate bottom
    z_p1 = z_p0 + tp
    holes = [(float(h[0]), float(h[1])) for h in a.holes]
    return dict(wl=wl, ww=ww, wt=wt, d=d, bush=bush, tp=tp, gap=gap, half_l=half_l, Lb=Lb, Wb=Wb,
                z_w1=z_w1, z_p0=z_p0, z_p1=z_p1, holes=holes, break_d=d + 2.0,
                pins=[(-wl / 2.0 - PIN_D / 2.0, -ww / 4.0), (-wl / 2.0 - PIN_D / 2.0, ww / 4.0), (0.0, -ww / 2.0 - PIN_D / 2.0)],
                pad_x=wl / 2.0, stud_y=0.0, stud_z=BASE_T + wt / 2.0, post_x=half_l + POST_W / 2.0)


def _base(L: dict) -> Part:
    b = Pos(0, 0, BASE_T / 2.0) * Box(L["Lb"], L["Wb"], BASE_T)
    for (x, y) in L["holes"]:                                             # Drill breakthrough hole Ø d+2
        b = b - Pos(x, y, BASE_T / 2.0) * Cylinder(radius=L["break_d"] / 2.0, height=BASE_T + 2)
    for sx in (-1, 1):                                                    # Post seats (posts are not separate parts: integral with the base)
        b = b + Pos(sx * L["post_x"], 0, (BASE_T + L["z_p0"]) / 2.0) * Box(POST_W, L["Wb"] - 16.0, L["z_p0"] - BASE_T)
    from ..fasteners.standards import resolve
    f = resolve(BOLT)[0]
    for sx in (-1, 1):                                                    # Jig plate bolt tapped holes, 2 per post (on top of the posts)
        for sy in (-1, 1):
            b = b - Pos(sx * L["post_x"], sy * (L["Wb"] / 2.0 - 8.0 - 8.0), L["z_p0"] - 6.0) * Cylinder(radius=f.nominal_dia_mm / 2.0, height=14.0)
    for (px, py) in L["pins"]:                                            # Locating pin holes (press fit)
        b = b - Pos(px, py, BASE_T - 4.0) * Cylinder(radius=PIN_D / 2.0, height=10.0)
    for sx in (-1, 1):                                                    # 4 Ø11 holes instead of jig mounting slots
        for sy in (-1, 1):
            b = b - Pos(sx * (L["Lb"] / 2.0 - 10.0), sy * (L["Wb"] / 2.0 - 8.0), BASE_T / 2.0) * Cylinder(radius=5.5, height=BASE_T + 2)
    # Side clamp stud tapped hole (through the +X post)
    from ..fasteners.standards import resolve as _r
    fs = _r(STUD)[0]
    b = b - Pos(L["post_x"], L["stud_y"], L["stud_z"]) * Rot(0, 90, 0) * Cylinder(radius=fs.nominal_dia_mm / 2.0, height=POST_W + 2)
    # If the jam nut drops below the base top (thin workpiece), cut a nut pocket in the base outside the post
    nut_r = fs.head_across_corners_mm / 2.0
    zlo = L["stud_z"] - nut_r - 1.5
    if zlo < BASE_T:
        x0 = L["post_x"] + POST_W / 2.0
        b = b - Pos((x0 + L["Lb"] / 2.0 + 1.0) / 2.0, L["stud_y"], (zlo + BASE_T + 1.0) / 2.0) * Box(L["Lb"] / 2.0 + 1.0 - x0, 2 * nut_r + 6.0, BASE_T + 1.0 - zlo)
    return b


def _plate(L: dict) -> Part:
    p = Pos(0, 0, (L["z_p0"] + L["z_p1"]) / 2.0) * Box(2 * (L["half_l"] + POST_W), L["Wb"] - 16.0, L["tp"])
    for (x, y) in L["holes"]:
        p = p - Pos(x, y, (L["z_p0"] + L["z_p1"]) / 2.0) * Cylinder(radius=L["bush"].d2 / 2.0, height=L["tp"] + 2)
    from ..fasteners.standards import resolve
    f = resolve(BOLT)[0]
    for sx in (-1, 1):
        for sy in (-1, 1):
            p = p - Pos(sx * L["post_x"], sy * (L["Wb"] / 2.0 - 16.0), (L["z_p0"] + L["z_p1"]) / 2.0) * Cylinder(radius=f.clearance("normal") / 2.0, height=L["tp"] + 2)
    return p


def build_drill_jig(a) -> Assembly:
    L = layout_drill_jig(a)
    bush, d, tp = L["bush"], L["d"], L["tp"]
    parts: list[PartInfo] = []
    no = [0]

    def add(name, solid, spec="", qty=1, material="", explode=(0, 0, 0), group=""):
        no[0] += 1
        parts.append(PartInfo(name, solid, spec, qty, material, explode, group or name.split()[0], no[0]))

    add("본체(베이스+기둥)", _base(L), f"베이스 {L['Lb']:g}×{L['Wb']:g}×{BASE_T:g}, 기둥 2, 드릴 빠짐 구멍 Ø{L['break_d']:g} ×{len(L['holes'])}, 핀 구멍 3, 스터드 탭 {STUD}", 1, "SM45C", (0, 0, -1.0), "본체")
    add("지그 판", _plate(L), f"두께 {tp:g} (= 부시 길이), 부시 구멍 Ø{bush.d2:g} H7 ×{len(L['holes'])}, 볼트 구멍 4", 1, "SM45C", (0, 0, 2.0), "커버")
    zc = (L["z_p0"] + L["z_p1"]) / 2.0
    for i, (x, y) in enumerate(L["holes"]):
        b = Pos(x, y, zc) * (Cylinder(radius=bush.d2 / 2.0, height=tp) - Cylinder(radius=d / 2.0, height=tp + 2))
        add("고정부시", b, f"드릴 Ø{d:g} G6 / 외경 Ø{bush.d2:g} n6 × {tp:g} (DIN 179 표, KS B 1030 계열)", 1, "STC3", (0, 0, 3.0), "칼라")
    work = Pos(0, 0, BASE_T + L["wt"] / 2.0) * Box(L["wl"], L["ww"], L["wt"])
    add("공작물(참조)", work, f"{L['wl']:g}×{L['ww']:g}×{L['wt']:g}, 구멍 Ø{d:g} ×{len(L['holes'])} 가공 전", 1, "", (0, 0, 0), "기어")
    for (px, py) in L["pins"]:
        add("위치결정 핀", Pos(px, py, BASE_T - 4.0 + (PIN_H + 4.0) / 2.0) * Cylinder(radius=PIN_D / 2.0, height=PIN_H + 4.0), f"Ø{PIN_D:g} m6 × {PIN_H + 4:g} (3-2-1 위치결정 2 + 1)", 1, "STC3", (0, 0, 1.0), "키")
    # Side clamp: clamp plate + stud + nut
    pad = Pos(L["pad_x"] + PAD_T / 2.0, L["stud_y"], BASE_T + L["wt"] / 2.0) * Box(PAD_T, min(L["ww"] * 0.6, 40.0), max(L["wt"] - 2.0, 4.0))
    add("누름판", pad, f"{PAD_T:g}×{min(L['ww'] * 0.6, 40):g}×{max(L['wt'] - 2, 4):g}, 공작물 +X 면 접촉", 1, "SM45C", (1.0, 0, 0), "스페이서")
    from ..fasteners.standards import resolve
    fs = resolve(STUD)[0]
    x0 = L["pad_x"] + PAD_T
    x1 = L["post_x"] + POST_W / 2.0 + 20.0
    stud = Pos((x0 + x1) / 2.0, L["stud_y"], L["stud_z"]) * Rot(0, 90, 0) * Cylinder(radius=fs.nominal_dia_mm / 2.0, height=x1 - x0)
    add("스터드 볼트", stud, f"{STUD} × {x1 - x0:.0f} (기둥 탭 관통, 누름판을 공작물에 밀착)", 1, "SCM435", (1.6, 0, 0), "볼트")
    nut = Pos(L["post_x"] + POST_W / 2.0 + fs.nut_height_mm / 2.0, L["stud_y"], L["stud_z"]) * Rot(0, 90, 0) * \
        (extrude(RegularPolygon(radius=fs.head_across_corners_mm / 2.0, side_count=6), amount=fs.nut_height_mm) - Pos(0, 0, fs.nut_height_mm / 2.0) * Cylinder(radius=fs.nominal_dia_mm / 2.0, height=fs.nut_height_mm + 2))
    add("육각너트", nut, f"{STUD} 잼 너트(기둥 바깥)", 1, "SM45C", (2.2, 0, 0), "볼트")
    fb = resolve(BOLT)[0]
    bl = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            grip = tp + 10.0
            shaft = Pos(0, 0, -grip / 2.0) * Cylinder(radius=fb.nominal_dia_mm / 2.0, height=grip)
            head = extrude(RegularPolygon(radius=fb.head_across_corners_mm / 2.0, side_count=6), amount=fb.head_height_mm)
            bl.append(Pos(sx * L["post_x"], sy * (L["Wb"] / 2.0 - 16.0), L["z_p1"]) * (shaft + head))
    from ..fasteners.standards import std_length
    add("육각볼트(지그 판)", Compound(children=bl), f"{BOLT}×{std_length(fb, tp + 10.0):g} ×4", 4, "SCM435", (0, 0, 3.4), "볼트")

    bushes = [p for p in parts if p.name == "고정부시"]
    plate = next(p for p in parts if p.name == "지그 판")
    base = parts[0]
    fits = [fit(f"부시 외경 Ø{bush.d2:g} ↔ 지그 판 구멍", b, plate, bush.d2 / 2, L["z_p0"], L["z_p1"], (x, y), axis="Z") for b, (x, y) in zip(bushes, L["holes"])]
    chip_ok = L["gap"] >= 0.5 * d - 1e-6
    len_ok = tp >= 2.0 * d - 1e-6
    extra = [
        {"code": "A9", "message": f"드릴 경로 / drill path: 칩 여유 {L['gap']:g} ≥ 0.5d({0.5 * d:g}), 베이스 빠짐 구멍 Ø{L['break_d']:g} ×{len(L['holes'])}, 부시 길이 {tp:g} {'≥' if len_ok else '<'} 2d({2 * d:g})",
         "ok": chip_ok and all(_has_break(base.solid, x, y, L) for x, y in L["holes"]), "actual": L["gap"], "required": 0.5 * d,
         "standard": "드릴 부시 설계 기준: 칩 여유 0.5~1 d, 부시 길이 ≥ 2 d(DIN 179 길이 표)", "suggestion": {"option_a": "gap 또는 부시 길이 조정"}},
    ]
    if not len_ok:
        extra.append({"code": "A9b", "severity": "SOFT", "message": f"부시 길이 {tp:g} < 2d: 표의 최대 길이 사용(드릴 안내 길이 부족 경고)", "ok": False, "standard": "부시 길이 ≥ 2d"})
    pub = {"preset": "drill_jig", "z_axis": zc, "ys": [0.0], "pinion": None, "work": [L["wl"], L["ww"], L["wt"]], "drill_d": d,
           "bush": {"d1": d, "d2": bush.d2, "l": tp}, "holes": L["holes"], "gap": L["gap"], "plate_z": [L["z_p0"], L["z_p1"]],
           "key_hubs": {}, "fits": fits, "extra_checks": extra,
           "hole_probe": {"r": d / 2.0, "points": L["holes"], "part": "고정부시"}}
    mates = [
        {"id": "M1", "pair": "고정부시 ↔ 지그 판 구멍", "type": "동심(압입 n6/H7) + 윗면 일치", "detail": f"Ø{bush.d2:g} ×{len(L['holes'])}, 보어 Ø{d:g} G6", "ok": True},
        {"id": "M2", "pair": "지그 판 ↔ 기둥 윗면", "type": "면 접촉 + 볼트 4", "detail": f"{BOLT} ×4, 판 두께 {tp:g}", "ok": True},
        {"id": "M3", "pair": "공작물 ↔ 베이스 + 위치결정 핀 3", "type": "3-2-1 위치결정(바닥면, -X 핀 2, -Y 핀 1)", "detail": f"공작물 {L['wl']:g}×{L['ww']:g}×{L['wt']:g}", "ok": True},
        {"id": "M4", "pair": "누름판 ↔ 공작물 +X 면", "type": "면 접촉, 스터드로 밀착", "detail": f"{STUD} 스터드 + 잼 너트", "ok": True},
        {"id": "M5", "pair": "부시 축선 ↔ 베이스 빠짐 구멍", "type": "동심(수직)", "detail": f"Ø{L['break_d']:g}, 칩 여유 {L['gap']:g}", "ok": True},
    ]
    return Assembly(parts, pub, mates, [{"no": p.no, "item": p.name, "spec": p.spec, "qty": p.qty, "material": p.material} for p in parts])


def _has_break(base_solid, x, y, L) -> bool:
    from ..verify.assembly import has_cyl
    return has_cyl(base_solid, L["break_d"] / 2.0, 0.0, BASE_T, (x, y), axis="Z")
