"""Bench vise assembly builder (preset vise): CAD practical exam task 5.

Reference: 153LAB 2023 round 2 bench vise (1 lead screw + 2 guide posts in a triangle);
part roles from the table clamp commentary: body, movable jaw, fixed jaw, lead screw, guide bushing, jaw plate, lever, handle, ring, nut.
Coordinates: lead screw = X, fixed jaw (integral with the body) at the +X end, movable jaw opens toward -X. Z up, body bottom z = 0.
The 2 guide posts are pressed into the body (fixed jaw) and extend toward -X; the movable jaw's guide bushings slide on them.
The lead screw is held axially in the movable jaw by a collar + retaining ring so it only rotates, and engages the nut
in the fixed jaw to pull the movable jaw.
"""
from __future__ import annotations

from build123d import Part, Compound, Box, Cylinder, Sphere, Pos, Rot, RegularPolygon, extrude

from . import standards as S
from .power_train import PartInfo, Assembly, cyl_x, ring_x, retaining_ring_solid, fit

BASE_T = 15.0
JAW_T0 = 30.0         # Minimum fixed/movable jaw thickness (X); grows to fit the nut length
JAW_H = 60.0          # Jaw height (above the base plate)
PLATE_T = 8.0         # Jaw plate
PLATE_H = 22.0
POST_D = 14.0
BUSH_WALL = 3.0
NUT_OD_ADD = 12.0
COLLAR_T = 6.0
HEAD_L = 16.0
HANDLE_D = 10.0
BALL_D = 16.0


def layout_vise(a) -> dict:
    jw, om, ds = float(a.jaw_w), float(a.open_max), float(a.screw_d)
    ring = S.retaining_ring(ds) if ds in (15, 16, 17, 20, 25, 30) else S.retaining_ring(min((15, 16, 17, 20, 25, 30), key=lambda r: abs(r - ds)))
    nut_od = ds + NUT_OD_ADD
    nut_l = round(1.8 * ds)                     # Nut length ≥ 1.5 d
    JAW_T = max(JAW_T0, nut_l + 2.0)            # Jaw thickness large enough to house the nut
    collar_od = ds + 10.0
    z_s = BASE_T + JAW_H - PLATE_H - ds / 2.0 - 4.0   # Lead screw height: 4 mm clearance below the jaw plates
    z_g = BASE_T + 12.0                                # Guide post height (lower two corners of the triangle, bushing holes clear of the base)
    y_g = jw / 2.0 - 14.0
    x_fj0 = 0.0; x_fj1 = JAW_T                  # Fixed jaw (body)
    x_mj1_closed = x_fj0 - 2 * PLATE_T          # Closed: jaw plates touching
    post_len = om + JAW_T + 2 * PLATE_T + 2.0 + 20.0   # Press fit 20 into the fixed jaw
    Lb0 = x_mj1_closed - om - JAW_T - HEAD_L - 24.0    # Base plate -X end (clearance for the handle head)
    Lb1 = x_fj1 + om + 10.0                           # Lead screw rear protrusion + margin
    return dict(jw=jw, om=om, ds=ds, ring=ring, nut_od=nut_od, nut_l=nut_l, collar_od=collar_od, z_s=z_s, z_g=z_g, y_g=y_g, jaw_t=JAW_T,
                x_fj0=x_fj0, x_fj1=x_fj1, x_mj1_closed=x_mj1_closed, post_len=post_len, Lb0=Lb0, Lb1=Lb1, Wb=jw + 20.0,
                motion_steps=[0.0, om * 0.25, om * 0.5, om * 0.75, om])


def _body(L: dict) -> Part:
    jw = L["jw"]
    base = Pos((L["Lb0"] + L["Lb1"]) / 2.0, 0, BASE_T / 2.0) * Box(L["Lb1"] - L["Lb0"], L["Wb"], BASE_T)
    fj = Pos((L["x_fj0"] + L["x_fj1"]) / 2.0, 0, BASE_T + JAW_H / 2.0) * Box(L["jaw_t"], jw, JAW_H)
    b = base + fj
    b = b - cyl_x(L["x_fj0"] - 1, L["x_fj1"] + 1, L["nut_od"] / 2.0, 0.0, L["z_s"])                       # Nut bore H7 (through)
    for sy in (-1, 1):
        b = b - cyl_x(L["x_fj0"] - 1, L["x_fj0"] + 20.0, POST_D / 2.0, sy * L["y_g"], L["z_g"])          # Post press-fit holes, depth 20
    for sx in (L["Lb0"] + 10.0, L["Lb1"] - 10.0):                                                          # 4 base mounting holes
        for sy in (-1, 1):
            b = b - Pos(sx, sy * (L["Wb"] / 2.0 - 8.0), BASE_T / 2.0) * Cylinder(radius=5.5, height=BASE_T + 2)
    return b


def _moving_jaw(L: dict) -> Part:
    """Movable jaw (at the closed position, +X face = x_mj1_closed). 2 guide bushing holes, lead screw hole + collar counterbore (-X face), retaining ring on the +X face."""
    x1 = L["x_mj1_closed"]; x0 = x1 - L["jaw_t"]
    j = Pos((x0 + x1) / 2.0, 0, BASE_T + JAW_H / 2.0) * Box(L["jaw_t"], L["jw"], JAW_H)
    for sy in (-1, 1):
        j = j - cyl_x(x0 - 1, x1 + 1, POST_D / 2.0 + BUSH_WALL, sy * L["y_g"], L["z_g"])                  # Bushing holes
    j = j - cyl_x(x0 - 1, x1 + 1, (L["ds"] + 1.0) / 2.0, 0.0, L["z_s"])                                      # Lead screw clearance hole
    j = j - cyl_x(x0 - 1, x0 + COLLAR_T, L["collar_od"] / 2.0, 0.0, L["z_s"])                                # Collar counterbore
    return j


def build_vise(a) -> Assembly:
    L = layout_vise(a)
    ds, jw, z_s, z_g = L["ds"], L["jw"], L["z_s"], L["z_g"]
    parts: list[PartInfo] = []
    no = [0]

    def add(name, solid, spec="", qty=1, material="", explode=(0, 0, 0), group=""):
        no[0] += 1
        parts.append(PartInfo(name, solid, spec, qty, material, explode, group or name.split()[0], no[0]))

    x1 = L["x_mj1_closed"]; x0 = x1 - L["jaw_t"]
    add("본체(고정조)", _body(L), f"바닥판 {L['Lb1'] - L['Lb0']:.0f}×{L['Wb']:g}×{BASE_T:g}, 고정조 {L["jaw_t"]:g}×{jw:g}×{JAW_H:g}, 너트 구멍 Ø{L['nut_od']:g} H7, 포스트 구멍 Ø{POST_D:g} H7 ×2(삼각 배치)", 1, "GC200", (0, 0, -1.0), "본체")
    add("이동조", _moving_jaw(L), f"{L["jaw_t"]:g}×{jw:g}×{JAW_H:g}, 가이드부시 구멍 Ø{POST_D + 2 * BUSH_WALL:g} H7 ×2, 나사축 구멍 Ø{ds + 1:g}, 칼라 자리 Ø{L['collar_od']:g}", 1, "GC200", (0, 0, 1.5), "커버")
    # 2 jaw plates
    add("물림판(고정조)", Pos(L["x_fj0"] - PLATE_T / 2.0, 0, BASE_T + JAW_H - PLATE_H / 2.0) * Box(PLATE_T, jw, PLATE_H), f"{PLATE_T:g}×{jw:g}×{PLATE_H:g} 열처리 HRC50", 1, "STC5", (0, 0, 2.0), "키")
    add("물림판(이동조)", Pos(x1 + PLATE_T / 2.0, 0, BASE_T + JAW_H - PLATE_H / 2.0) * Box(PLATE_T, jw, PLATE_H), f"{PLATE_T:g}×{jw:g}×{PLATE_H:g} 열처리 HRC50", 1, "STC5", (0, 0, 2.0), "키")
    # 2 guide posts + 2 bushings
    for sy in (-1, 1):
        add("가이드 포스트", cyl_x(L["x_fj0"] + 20.0 - L["post_len"], L["x_fj0"] + 20.0, POST_D / 2.0, sy * L["y_g"], z_g), f"Ø{POST_D:g} h6 × {L['post_len']:.0f}, 고정조 압입 20", 1, "SM45C", (0, sy * 0.8, 0), "축")
    for sy, tag in ((-1, "좌"), (1, "우")):
        add(f"가이드부시({tag})", ring_x(x0, x1, POST_D / 2.0 + BUSH_WALL, POST_D / 2.0, sy * L["y_g"], z_g), f"Ø{POST_D + 2 * BUSH_WALL:g} p6 / Ø{POST_D:g} H7 × {L["jaw_t"]:g}", 1, "PBC2", (0, sy * 0.8, 1.5), "칼라")
    # Nut (inside the fixed jaw)
    nx0 = L["x_fj0"] + (L["jaw_t"] - L["nut_l"]) / 2.0
    add("너트", ring_x(nx0, nx0 + L["nut_l"], L["nut_od"] / 2.0, ds / 2.0, 0.0, z_s), f"Ø{L['nut_od']:g} p6 × {L['nut_l']:g}, 암나사 M{ds:g} (나사산 미모델)", 1, "PBC2", (0, 0, 0), "칼라")
    # Lead screw: head (handle hole) + collar + shaft (at the closed position; sticks out open_max further at the rear)
    xs_end = L["x_fj1"] + L["om"]
    screw = cyl_x(x0 - 2.0, xs_end, ds / 2.0, 0.0, z_s)
    screw = screw + cyl_x(x0, x0 + COLLAR_T, L["collar_od"] / 2.0, 0.0, z_s)                                # Collar (inside the counterbore)
    head = cyl_x(x0 - 2.0 - HEAD_L, x0 - 2.0, (ds + 8.0) / 2.0, 0.0, z_s)
    head = head - Pos(x0 - 2.0 - HEAD_L / 2.0, 0, z_s) * Rot(90, 0, 0) * Cylinder(radius=HANDLE_D / 2.0 + 0.2, height=ds + 10.0)   # Handle hole (Y)
    screw = screw + head
    rg = L["ring"]
    screw = screw - ring_x(x1, x1 + rg.m, ds / 2.0 + 1.0, rg.d2 / 2.0, 0.0, z_s)                                  # Retaining ring groove (+X face)
    add("리드나사축", screw, f"M{ds:g} (나사산 미모델) 길이 {xs_end - (x0 - 2.0 - HEAD_L):.0f}, 칼라 Ø{L['collar_od']:g}×{COLLAR_T:g}, 머리 Ø{ds + 8:g}×{HEAD_L:g} 핸들 구멍 Ø{HANDLE_D:g}, 멈춤링 홈 Ø{rg.d2:g}×{rg.m:g}", 1, "SM45C", (0, 0, 0), "축")
    add("멈춤링(C형)", retaining_ring_solid(rg, x1, 0.0, z_s), f"축용 {rg.d1:g} KS B 1336 (이동조 +X 면에 밀착)", 1, "SK5", (1.0, 0, 0), "멈춤링")
    # Handle: bar + ball at each end
    hx = x0 - 2.0 - HEAD_L / 2.0
    bar = Pos(hx, 0, z_s) * Rot(90, 0, 0) * Cylinder(radius=HANDLE_D / 2.0, height=jw)
    handle = bar + Pos(hx, jw / 2.0, z_s) * Sphere(radius=BALL_D / 2.0) + Pos(hx, -jw / 2.0, z_s) * Sphere(radius=BALL_D / 2.0)
    add("핸들", handle, f"바 Ø{HANDLE_D:g} × {jw:g} + 볼 Ø{BALL_D:g} ×2 (KS B 1334 손잡이 대용)", 1, "SM45C", (-1.5, 0, 0), "풀리")

    posts = [p for p in parts if p.name == "가이드 포스트"]; bushes = [p for p in parts if p.name.startswith("가이드부시")]
    body, jaw, nut, screw_p = parts[0], parts[1], next(p for p in parts if p.name == "너트"), next(p for p in parts if p.name == "리드나사축")
    fits = []
    for sy, po, bu in zip((-1, 1), posts, bushes):
        fits.append(fit(f"가이드 포스트 Ø{POST_D:g} ↔ 고정조 구멍", po, body, POST_D / 2, L["x_fj0"], L["x_fj0"] + 20.0, (sy * L["y_g"], z_g)))
        fits.append(fit(f"가이드부시 내경 Ø{POST_D:g} ↔ 포스트", bu, po, POST_D / 2, x0, x1, (sy * L["y_g"], z_g)))
        fits.append(fit(f"가이드부시 외경 Ø{POST_D + 2 * BUSH_WALL:g} ↔ 이동조 구멍", bu, jaw, POST_D / 2 + BUSH_WALL, x0, x1, (sy * L["y_g"], z_g)))
    fits.append(fit(f"너트 외경 Ø{L['nut_od']:g} ↔ 고정조 구멍", nut, body, L["nut_od"] / 2, nx0, nx0 + L["nut_l"], (0.0, z_s)))
    fits.append(fit(f"너트 내경 Ø{ds:g} ↔ 나사축", nut, screw_p, ds / 2, nx0, nx0 + L["nut_l"], (0.0, z_s)))
    fits.append(fit(f"칼라 Ø{L['collar_od']:g} ↔ 이동조 카운터보어", screw_p, jaw, L["collar_od"] / 2, x0, x0 + COLLAR_T, (0.0, z_s)))
    om = L["om"]
    extra = [
        {"code": "A11", "message": f"최대 벌림 {om:g} 에서 포스트가 부시에 {L['post_len'] - 20.0 - om - 2 * PLATE_T:.0f} mm 물림(≥ 부시 길이 {L["jaw_t"]:g}), 나사축이 너트에 {L['nut_l']:g} mm 물림(≥ 1.5d = {1.5 * ds:g})",
         "ok": (L["post_len"] - 20.0 - om - 2 * PLATE_T >= L["jaw_t"] - 1e-6) and (L["nut_l"] >= 1.5 * ds - 1e-6), "actual": L["post_len"] - 20.0 - om - 2 * PLATE_T, "required": L["jaw_t"],
         "standard": "안내 길이 ≥ 부시 길이, 나사 물림 ≥ 1.5d(주철/청동 너트)", "suggestion": {"option_a": "포스트 길이 또는 너트 길이 증가"}},
    ]
    pub = {"preset": "vise", "z_axis": z_s, "ys": [0.0], "pinion": None, "jaw_w": jw, "open_max": om, "screw_d": ds,
           "post": [POST_D, L["post_len"]], "nut": [L["nut_od"], L["nut_l"]], "triangle": {"screw": [0.0, z_s], "posts": [[-L["y_g"], z_g], [L["y_g"], z_g]]},
           "key_hubs": {}, "fits": fits, "extra_checks": extra, "motion_steps": L["motion_steps"], "motion_label": "단계(벌림 0 → 최대)"}
    mates = [
        {"id": "M1", "pair": "가이드 포스트 ↔ 고정조", "type": "동심(압입) ×2", "detail": f"Ø{POST_D:g} H7/m6, 깊이 20, 삼각 배치 y ±{L['y_g']:g} z {z_g:g}", "ok": True},
        {"id": "M2", "pair": "가이드부시 ↔ 이동조 / 포스트", "type": "압입 + 미끄럼", "detail": f"Ø{POST_D + 2 * BUSH_WALL:g} H7/p6, Ø{POST_D:g} H7/h6", "ok": True},
        {"id": "M3", "pair": "리드나사축 ↔ 이동조", "type": "회전 조인트(칼라 + 멈춤링으로 축 방향 고정)", "detail": f"칼라 Ø{L['collar_od']:g}, 링 {rg.d1:g}", "ok": True},
        {"id": "M4", "pair": "리드나사축 ↔ 너트(고정조)", "type": "나사 조인트", "detail": f"M{ds:g}, 물림 {L['nut_l']:g}", "ok": True},
        {"id": "M5", "pair": "물림판 ↔ 조 면", "type": "면 접촉(닫힘 때 서로 접촉)", "detail": f"{PLATE_T:g} ×2, 최대 벌림 {om:g}", "ok": True},
        {"id": "M6", "pair": "이동조 바닥 ↔ 바닥판", "type": "면 미끄럼", "detail": "직선 안내는 포스트 2 + 나사축 1", "ok": True},
    ]
    asm = Assembly(parts, pub, mates, [{"no": p.no, "item": p.name, "spec": p.spec, "qty": p.qty, "material": p.material} for p in parts])
    moving = ["이동조", "물림판(이동조)", "가이드부시(좌)", "가이드부시(우)", "리드나사축", "멈춤링(C형)", "핸들"]
    mv_parts = [(p.name, p) for p in asm.parts if p.name in moving]

    def motion(g: float) -> dict:
        return {n: Pos(-g, 0, 0) * p.solid for n, p in mv_parts}
    asm.motion = motion
    return asm
